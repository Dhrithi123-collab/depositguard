from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError
from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuthSession, InstitutionMembership, LoginFailure, SecurityAuditEvent, User

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))
SESSION_COOKIE = "depositguard_session"
CSRF_COOKIE = "depositguard_csrf"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def validate_password(password: str) -> None:
    if len(password) < 6 or len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be between 6 and 128 characters.")


def create_user(
    db: Session,
    *,
    email: str,
    display_name: str,
    password: str,
    is_system_admin: bool = False,
    must_change_password: bool = True,
) -> User:
    normalized = normalize_email(email)
    if not EMAIL_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    validate_password(password)
    if not display_name.strip() or len(display_name.strip()) > 120:
        raise HTTPException(status_code=422, detail="Display name must contain 1 to 120 characters.")
    if db.scalar(select(User.id).where(User.email_normalized == normalized)):
        raise HTTPException(status_code=409, detail="An account with that email address already exists.")
    user = User(
        email=email.strip(), email_normalized=normalized, display_name=display_name.strip(),
        password_hash=password_hasher.hash(password), is_system_admin=is_system_admin,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.flush()
    return user


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthContext:
    user: User
    memberships: dict[str, str]
    session: AuthSession


def authenticate(db: Session, request: Request, email: str, password: str) -> tuple[AuthContext, str, str]:
    normalized = normalize_email(email)
    remote = request.client.host if request.client else "unknown"
    remote_key = hash_secret(remote)
    cutoff = now_utc() - timedelta(minutes=15)
    failures = db.scalar(select(func.count(LoginFailure.id)).where(
        LoginFailure.email_normalized == normalized,
        LoginFailure.remote_key == remote_key,
        LoginFailure.attempted_at >= cutoff,
    )) or 0
    if failures >= 10:
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again in 15 minutes.")

    user = db.scalar(select(User).where(User.email_normalized == normalized))
    stored_hash = user.password_hash if user else dummy_password_hash
    try:
        valid = password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        valid = False
    if not user or not valid or not user.is_active:
        db.add(LoginFailure(email_normalized=normalized, remote_key=remote_key))
        db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect, or the account is inactive.")

    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(password)
    db.execute(delete(LoginFailure).where(LoginFailure.email_normalized == normalized, LoginFailure.remote_key == remote_key))
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = AuthSession(
        token_hash=hash_secret(token), csrf_hash=hash_secret(csrf_token), user_id=user.id,
        expires_at=now_utc() + timedelta(minutes=get_settings().auth_session_minutes),
    )
    db.add(session)
    db.add(SecurityAuditEvent(actor_user_id=user.id, event_type="login_succeeded", details={"remote_key": remote_key[:12]}))
    db.commit()
    db.refresh(user)
    memberships = {row.institution_id: row.role for row in db.scalars(select(InstitutionMembership).where(InstitutionMembership.user_id == user.id))}
    return AuthContext(user, memberships, session), token, csrf_token


def get_auth_context(request: Request, db: Session) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    session = db.get(AuthSession, hash_secret(token))
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session is invalid or has expired. Sign in again.")
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if expires_at <= now_utc():
        session.revoked_at = now_utc()
        db.commit()
        raise HTTPException(status_code=401, detail="Session is invalid or has expired. Sign in again.")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        session.revoked_at = now_utc()
        db.commit()
        raise HTTPException(status_code=401, detail="Account is inactive. Contact an administrator.")
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not csrf_cookie or not secrets.compare_digest(hash_secret(csrf_cookie), session.csrf_hash):
            raise HTTPException(status_code=403, detail="CSRF validation failed. Refresh the page and try again.")
        header_token = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(header_token, csrf_cookie):
            raise HTTPException(status_code=403, detail="CSRF validation failed. Refresh the page and try again.")
        origin = request.headers.get("Origin")
        if origin and origin not in get_settings().cors_origins:
            raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    memberships = {row.institution_id: row.role for row in db.scalars(select(InstitutionMembership).where(InstitutionMembership.user_id == user.id))}
    return AuthContext(user, memberships, session)


def require_system_admin(context: AuthContext) -> None:
    if not context.user.is_system_admin:
        raise HTTPException(status_code=403, detail="System administrator permission is required.")


def require_institution(context: AuthContext, institution_id: str) -> str:
    if context.user.is_system_admin:
        return "system_admin"
    role = context.memberships.get(institution_id)
    if role is None:
        # Deliberately conceal whether an unrelated institution exists.
        raise HTTPException(status_code=404, detail="Institution was not found.")
    return role


def record_security_event(db: Session, actor_id: str | None, event_type: str, target_id: str | None = None, details: dict | None = None) -> None:
    db.add(SecurityAuditEvent(actor_user_id=actor_id, event_type=event_type, target_user_id=target_id, details=details or {}))
