from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_engine


def create_user(email: str, password: str) -> dict:
    """
    Insert a new user. Returns the new user dict (no password_hash).
    Raises ValueError if the email is already registered.
    """
    password_hash = generate_password_hash(password)
    now = datetime.now(timezone.utc).isoformat()
    email = email.lower().strip()
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    try:
        with engine.begin() as conn:
            if is_pg:
                result = conn.execute(
                    text(
                        "INSERT INTO users (email, password_hash, created_at)"
                        " VALUES (:email, :password_hash, :created_at) RETURNING id"
                    ),
                    {"email": email, "password_hash": password_hash, "created_at": now},
                )
                user_id = result.scalar()
            else:
                result = conn.execute(
                    text(
                        "INSERT INTO users (email, password_hash, created_at)"
                        " VALUES (:email, :password_hash, :created_at)"
                    ),
                    {"email": email, "password_hash": password_hash, "created_at": now},
                )
                user_id = result.lastrowid
        return {"id": user_id, "email": email, "created_at": now}
    except IntegrityError:
        raise ValueError(f"Email already registered: {email}")


def get_user_by_id(user_id: int) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, created_at FROM users WHERE id = :id AND is_active = 1"),
            {"id": user_id},
        ).mappings().fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, email, password_hash, created_at"
                " FROM users WHERE email = :email AND is_active = 1"
            ),
            {"email": email.lower().strip()},
        ).mappings().fetchone()
        return dict(row) if row else None


def verify_password(email: str, password: str) -> dict | None:
    """Return user dict (no password_hash) on valid credentials, None otherwise."""
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}
    return None
