import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_engine


def create_user(email: str, password: str, company_name: str = "") -> dict:
    """
    Insert a new user. Returns the new user dict (no password_hash).
    Raises ValueError if the email is already registered.

    ``company_name`` is optional; stored as NULL when blank so existing callers
    and existing users stay backward compatible.
    """
    password_hash = generate_password_hash(password)
    now = datetime.now(timezone.utc).isoformat()
    email = email.lower().strip()
    company_name = (company_name or "").strip() or None
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    params = {"email": email, "password_hash": password_hash,
              "created_at": now, "company_name": company_name}
    try:
        with engine.begin() as conn:
            if is_pg:
                result = conn.execute(
                    text(
                        "INSERT INTO users (email, password_hash, created_at, company_name)"
                        " VALUES (:email, :password_hash, :created_at, :company_name) RETURNING id"
                    ),
                    params,
                )
                user_id = result.scalar()
            else:
                result = conn.execute(
                    text(
                        "INSERT INTO users (email, password_hash, created_at, company_name)"
                        " VALUES (:email, :password_hash, :created_at, :company_name)"
                    ),
                    params,
                )
                user_id = result.lastrowid
        return {"id": user_id, "email": email, "created_at": now,
                "company_name": company_name}
    except IntegrityError:
        raise ValueError(f"Email already registered: {email}")


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


def set_reset_token(email: str) -> str | None:
    """Generate a reset token for the user and persist it. Returns the token or None."""
    user = get_user_by_email(email)
    if not user:
        return None
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET reset_token = :token, reset_token_expires_at = :expires_at"
                " WHERE email = :email"
            ),
            {"token": token, "expires_at": expires_at, "email": email.lower().strip()},
        )
    return token


def get_user_by_reset_token(token: str) -> dict | None:
    """Return the user row for a valid, unexpired reset token, or None."""
    now = datetime.now(timezone.utc).isoformat()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, email, created_at FROM users"
                " WHERE reset_token = :token AND reset_token_expires_at > :now AND is_active = 1"
            ),
            {"token": token, "now": now},
        ).mappings().fetchone()
    return dict(row) if row else None


def update_password(user_id: int, new_password: str) -> None:
    password_hash = generate_password_hash(new_password)
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :hash WHERE id = :id"),
            {"hash": password_hash, "id": user_id},
        )


def update_company_name(user_id: int, company_name: str) -> None:
    """Set or clear the company name for an existing user."""
    value = (company_name or "").strip() or None
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET company_name = :name WHERE id = :id"),
            {"name": value, "id": user_id},
        )


def clear_reset_token(user_id: int) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET reset_token = NULL, reset_token_expires_at = NULL"
                " WHERE id = :id"
            ),
            {"id": user_id},
        )


def set_trial(user_id: int, days: int = 14) -> str:
    """Set trial_ends_at to now + days. Returns the ISO timestamp."""
    ends_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET trial_ends_at = :ends_at WHERE id = :id"),
            {"ends_at": ends_at, "id": user_id},
        )
    return ends_at


def set_subscription(
    user_id: int,
    stripe_customer_id: str,
    status: str,
    billing_interval: str | None = None,
) -> None:
    """Update stripe_customer_id, subscription_status, and optionally billing_interval."""
    with get_engine().begin() as conn:
        if billing_interval:
            conn.execute(
                text(
                    "UPDATE users SET stripe_customer_id = :cid, subscription_status = :status,"
                    " billing_interval = :interval WHERE id = :id"
                ),
                {"cid": stripe_customer_id, "status": status,
                 "interval": billing_interval, "id": user_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE users SET stripe_customer_id = :cid, subscription_status = :status"
                    " WHERE id = :id"
                ),
                {"cid": stripe_customer_id, "status": status, "id": user_id},
            )


def get_user_by_stripe_customer(stripe_customer_id: str) -> dict | None:
    """Return user dict for a given Stripe customer ID, or None."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, email, created_at, stripe_customer_id,"
                " subscription_status, trial_ends_at, billing_interval"
                " FROM users WHERE stripe_customer_id = :cid AND is_active = 1"
            ),
            {"cid": stripe_customer_id},
        ).mappings().fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    """Return full user dict including subscription fields."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, email, created_at, stripe_customer_id,"
                " subscription_status, trial_ends_at, company_name, billing_interval"
                " FROM users WHERE id = :id AND is_active = 1"
            ),
            {"id": user_id},
        ).mappings().fetchone()
        return dict(row) if row else None
