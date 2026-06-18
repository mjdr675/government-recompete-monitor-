import sqlite3
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from db import connect


def create_user(email: str, password: str) -> dict:
    """
    Insert a new user. Returns the new user dict (no password_hash).
    Raises ValueError if the email is already registered.
    """
    password_hash = generate_password_hash(password)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with connect() as con:
            cur = con.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email.lower().strip(), password_hash, now),
            )
            con.commit()
            return {"id": cur.lastrowid, "email": email.lower().strip(), "created_at": now}
    except sqlite3.IntegrityError:
        raise ValueError(f"Email already registered: {email}")


def get_user_by_id(user_id: int) -> dict | None:
    with connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT id, email, created_at FROM users WHERE id=? AND is_active=1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email=? AND is_active=1",
            (email.lower().strip(),),
        ).fetchone()
        return dict(row) if row else None


def verify_password(email: str, password: str) -> dict | None:
    """Return user dict (no password_hash) on valid credentials, None otherwise."""
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}
    return None
