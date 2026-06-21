"""Tests for trial expiry gate in require_login (task F-9)."""
import pytest
from datetime import datetime, timedelta, timezone
import db as db_module
import users as users_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(db, monkeypatch):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _set_trial_expired(user_id):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    import db as db_module2
    from sqlalchemy import text
    with db_module2.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET trial_ends_at = :t WHERE id = :id"),
            {"t": past, "id": user_id},
        )


class TestTrialGate:
    def test_active_trial_allows_access(self, client, db):
        user = users_module.create_user("trial@example.com", "pass123")
        users_module.set_trial(user["id"], days=14)
        _login(client, user["id"])
        resp = client.get("/watchlist")
        # Not redirected to /subscribe
        assert "/subscribe" not in (resp.headers.get("Location") or "")

    def test_expired_trial_redirects_to_subscribe(self, client, db):
        user = users_module.create_user("expired@example.com", "pass123")
        _set_trial_expired(user["id"])
        _login(client, user["id"])
        resp = client.get("/contracts")
        assert resp.status_code == 302
        assert "/subscribe" in resp.headers["Location"]
        assert "expired=1" in resp.headers["Location"]

    def test_active_subscription_bypasses_trial_gate(self, client, db):
        user = users_module.create_user("subscribed@example.com", "pass123")
        _set_trial_expired(user["id"])
        users_module.set_subscription(user["id"], "cus_active", "active")
        _login(client, user["id"])
        resp = client.get("/contracts")
        assert "/subscribe" not in (resp.headers.get("Location") or "")

    def test_no_trial_set_does_not_block(self, client, db):
        user = users_module.create_user("notrial@example.com", "pass123")
        # trial_ends_at is NULL — gate should not redirect
        _login(client, user["id"])
        resp = client.get("/watchlist")
        assert "/subscribe" not in (resp.headers.get("Location") or "")

    def test_subscribe_page_accessible_when_expired(self, client, db):
        user = users_module.create_user("gate@example.com", "pass123")
        _set_trial_expired(user["id"])
        _login(client, user["id"])
        resp = client.get("/subscribe")
        assert resp.status_code == 200
