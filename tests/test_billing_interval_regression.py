"""
Regression tests for the post-registration 500: users.py selected
users.billing_interval, a column that only ever existed on the SQLite dev
schema (db.init_db's users ALTER-COLUMN loop) and was never added to
production PostgreSQL (migration 024 explicitly declined to add it, since
no code writes it). Every authenticated request calls get_user_by_id() via
auth.load_logged_in_user(), so production crashed with UndefinedColumn
immediately after a successful registration redirected to /dashboard.

There is no live PostgreSQL available in this test environment, so these
tests reproduce the missing-column condition directly: each fixture drops
users.billing_interval from the SQLite test database after init_db() runs,
exactly matching the production (Postgres) schema shape.

Also covers the companion write-path fix: set_subscription() used to accept
an optional billing_interval kwarg that wrote to this same missing column.
No caller ever passed one, so it never fired in production, but it was a
latent landmine for the next billing change. The kwarg has been removed.
"""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import db as db_module
from users import (create_user, get_user_by_id, get_user_by_stripe_customer,
                    set_subscription)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def prod_shaped_db(tmp_path, monkeypatch):
    """SQLite test DB with users.billing_interval dropped, mirroring the
    production PostgreSQL schema (which never had this column)."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN billing_interval"))
    yield db_path


@pytest.fixture()
def client(prod_shaped_db, monkeypatch):
    import app as flask_app
    monkeypatch.setitem(flask_app.app.config, "TESTING", True)
    monkeypatch.setitem(flask_app.app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setitem(flask_app.app.config, "RATELIMIT_ENABLED", False)
    monkeypatch.setitem(flask_app.app.config, "SECRET_KEY", "test-secret-key")
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


def _register(client, email="user@example.com", password="password123"):
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=None)
    with patch("tasks.send_email_task", mock_task):
        return client.post("/register", data={
            "email": email,
            "password": password,
            "confirm": password,
        })


# ---------------------------------------------------------------------------
# users.py unit tests — direct reproduction of the missing-column condition
# ---------------------------------------------------------------------------

def test_get_user_by_id_works_without_billing_interval_column(prod_shaped_db):
    user = create_user("id-check@example.com", "password123", company_name="Acme")
    result = get_user_by_id(user["id"])
    assert result is not None
    assert "billing_interval" not in result


def test_get_user_by_id_returns_unrelated_fields_correctly(prod_shaped_db):
    user = create_user("fields-check@example.com", "password123", company_name="Acme Co")
    result = get_user_by_id(user["id"])
    assert result["id"] == user["id"]
    assert result["email"] == "fields-check@example.com"
    assert result["company_name"] == "Acme Co"
    assert result["subscription_status"] == "trialing"
    assert "trial_ends_at" in result
    assert "stripe_customer_id" in result


def test_get_user_by_stripe_customer_works_without_billing_interval_column(prod_shaped_db):
    user = create_user("stripe-check@example.com", "password123")
    set_subscription(user["id"], "cus_test123", "active")
    result = get_user_by_stripe_customer("cus_test123")
    assert result is not None
    assert result["id"] == user["id"]
    assert "billing_interval" not in result


def test_old_query_would_have_raised_without_column(prod_shaped_db):
    """Control: proves the missing column, not something else, was the cause
    of the original 500 — the raw pre-fix SELECT still fails on this schema."""
    engine = db_module.get_engine()
    with pytest.raises(OperationalError, match="billing_interval"):
        with engine.connect() as conn:
            conn.execute(text(
                "SELECT id, billing_interval FROM users WHERE id = :id"
            ), {"id": 1})


def test_set_subscription_no_longer_accepts_billing_interval(prod_shaped_db):
    """set_subscription()'s billing_interval kwarg (and its write to the
    dropped column) has been removed — it was a latent path that would have
    raised UndefinedColumn in production the moment any caller passed a
    truthy value. Confirm the kwarg is gone rather than silently reachable."""
    user = create_user("latent-write@example.com", "password123")
    with pytest.raises(TypeError):
        set_subscription(user["id"], "cus_latent", "active", billing_interval="monthly")


def test_set_subscription_works_without_billing_interval_column(prod_shaped_db):
    """The remaining stripe_customer_id/status write path never touches
    billing_interval, so it must succeed on the production-shaped schema."""
    user = create_user("subscription-check@example.com", "password123")
    set_subscription(user["id"], "cus_ok", "active")
    result = get_user_by_stripe_customer("cus_ok")
    assert result is not None
    assert result["id"] == user["id"]
    assert result["subscription_status"] == "active"


# ---------------------------------------------------------------------------
# Full auth-flow regression — registration through the dashboard redirect
# ---------------------------------------------------------------------------

def test_registration_then_dashboard_no_500_without_billing_interval_column(client):
    rv = _register(client)
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/dashboard"

    rv = client.get("/dashboard", follow_redirects=True)
    assert rv.status_code == 200


def test_login_after_registration_no_500_without_billing_interval_column(client):
    _register(client, email="relogin@example.com")
    client.get("/logout")

    rv = client.post("/login", data={
        "email": "relogin@example.com",
        "password": "password123",
    })
    assert rv.status_code == 302

    rv = client.get("/dashboard", follow_redirects=True)
    assert rv.status_code == 200
