import os
import sys
import subprocess
from pathlib import Path
from importlib import reload

import pytest

# Helper to run the bootstrap command in a subprocess with the given environment
def run_bootstrap(args, env):
    return subprocess.run([sys.executable, "-m", "app.bootstrap_admin"] + args,
                          capture_output=True, text=True, env=env)

@pytest.fixture
def temp_db_engine(monkeypatch, tmp_path: Path):
    # Point the application to a temporary SQLite database
    db_url = f"sqlite:///{tmp_path / 'test_bootstrap.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # Reload configuration and database session so they pick up the new URL
    import app.core.config as config_mod
    reload(config_mod)
    import app.database.session as session_mod
    reload(session_mod)
    # Ensure tables are created
    session_mod.Base.metadata.create_all(bind=session_mod.engine)
    return session_mod

def test_bootstrap_admin_success(monkeypatch, tmp_path: Path, temp_db_engine):
    env = os.environ.copy()
    # Run bootstrap with valid inputs (non‑interactive mode)
    result = run_bootstrap([
        "admin@example.test",
        "--display-name", "Test Admin",
        "--password", "StrongPass123!",
        "--confirm-password", "StrongPass123!",
    ], env)
    assert result.returncode == 0, f"Bootstrap failed: {result.stderr}\n{result.stdout}"
    assert "Created system administrator account" in result.stdout

    # Verify the admin user was created with the correct flags
    from app.models import User
    from sqlalchemy import select
    SessionLocal = temp_db_engine.SessionLocal
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.test"))
        assert admin is not None
        assert admin.is_system_admin
        assert admin.must_change_password

def test_bootstrap_admin_duplicate(monkeypatch, tmp_path: Path, temp_db_engine):
    env = os.environ.copy()
    # First creation should succeed
    first = run_bootstrap([
        "admin2@example.test",
        "--display-name", "Admin Two",
        "--password", "AnotherStrong123!",
        "--confirm-password", "AnotherStrong123!",
    ], env)
    assert first.returncode == 0

    # Second attempt should fail because an admin already exists
    second = run_bootstrap([
        "admin3@example.test",
        "--display-name", "Admin Three",
        "--password", "YetAnotherStrong123!",
        "--confirm-password", "YetAnotherStrong123!",
    ], env)
    assert second.returncode != 0
    assert "already exists" in second.stderr.lower()

def test_bootstrap_admin_weak_password(monkeypatch, tmp_path: Path, temp_db_engine):
    env = os.environ.copy()
    # Attempt with a password that does not meet the policy (too short)
    result = run_bootstrap([
        "weak@example.test",
        "--display-name", "Weak Admin",
        "--password", "short",
        "--confirm-password", "short",
    ], env)
    assert result.returncode != 0
    assert "password validation failed" in result.stderr.lower() or "password must be" in result.stderr.lower()
