"""Provision DepositGuard's first local system administrator.

This module can be executed as a script via:
    python -m app.bootstrap_admin <email>

It supports interactive prompts (default) or non‑interactive usage by providing
`--display-name`, `--password` and `--confirm-password` arguments.  All inputs are
validated against the existing password policy.

The created user is forced to change the password on first login (`must_change_password=True`).
If a system administrator already exists the command aborts with a clear error.
"""

import argparse
import sys
from getpass import getpass

from sqlalchemy import select

from app.database.session import Base, SessionLocal, engine
from app.models import User
from app.models import auth as _auth_models  # noqa: F401 - registers auth tables
from app.services.auth import create_user, record_security_event, validate_password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision DepositGuard's first local system administrator."
    )
    parser.add_argument("email", help="Administrator email address")
    parser.add_argument(
        "--display-name",
        help="Display name; prompted when omitted",
    )
    parser.add_argument(
        "--password",
        help="Initial password (6–128 characters). If omitted, interactive prompt is used.",
    )
    parser.add_argument(
        "--confirm-password",
        help="Confirmation of the initial password (required when --password is provided).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    display_name = args.display_name or input("Administrator display name: ").strip()
    if args.password is not None:
        password = args.password
        confirmation = args.confirm_password
        if confirmation is None:
            sys.stderr.write("--confirm-password is required when --password is supplied\n")
            sys.exit(1)
    else:
        password = getpass("Initial password (6–128 characters): ")
        confirmation = getpass("Confirm initial password: ")
    if password != confirmation:
        sys.stderr.write("Passwords do not match.\n")
        sys.exit(1)
    try:
        validate_password(password)
    except Exception as exc:
        sys.stderr.write(f"Password validation failed: {exc}\n")
        sys.exit(1)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.scalar(select(User.id).where(User.is_system_admin.is_(True)))
        if existing is not None:
            sys.stderr.write(
                "A system administrator already exists; bootstrap cannot be repeated.\n"
            )
            sys.exit(1)
        user = create_user(
            db,
            email=args.email,
            display_name=display_name,
            password=password,
            is_system_admin=True,
            must_change_password=True,
        )
        record_security_event(db, user.id, "initial_system_admin_bootstrapped", user.id)
        db.commit()
        print(f"Created system administrator account for {user.email} ({user.id}).")


if __name__ == "__main__":
    main()
