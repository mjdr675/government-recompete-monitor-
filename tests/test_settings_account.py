"""Tests for R-02: /settings/account — password change and subscription status."""
import pytest
import db as db_module
import users as users_module
from users import set_trial, verify_password


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(db):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def logged_in_client(db, client):
    user = users_module.create_user("acct@example.com", "OldPass99!")
    set_trial(user["id"], days=14)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    return client, user


class TestSettingsAccountPage:
    def test_requires_auth(self, client):
        resp = client.get("/settings/account")
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers["Location"]

    def test_shows_account_page_when_logged_in(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        assert resp.status_code == 200
        assert b"Account Settings" in resp.data

    def test_shows_user_email(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        assert user["email"].encode() in resp.data

    def test_shows_subscription_status(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        body = resp.data.decode()
        assert "trialing" in body.lower() or "Trial" in body

    def test_shows_trial_expiry_date(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        body = resp.data.decode()
        assert "expires" in body.lower() or "trial_ends_at" not in body


class TestPasswordChange:
    def test_wrong_current_password_returns_error(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "WrongPass!",
            "new_password": "NewPass99!",
            "confirm_password": "NewPass99!",
        })
        assert resp.status_code == 200
        assert b"incorrect" in resp.data.lower() or b"Current password" in resp.data

    def test_short_new_password_rejected(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "short",
            "confirm_password": "short",
        })
        assert resp.status_code == 200
        assert b"8 characters" in resp.data

    def test_mismatched_confirm_rejected(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "NewPass99!",
            "confirm_password": "DifferentPass99!",
        })
        assert resp.status_code == 200
        assert b"do not match" in resp.data

    def test_valid_password_change_succeeds(self, db, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "BrandNew99!",
            "confirm_password": "BrandNew99!",
        })
        assert resp.status_code == 200
        assert b"updated" in resp.data.lower()

    def test_password_actually_changed_in_db(self, db, logged_in_client):
        client, user = logged_in_client
        client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "BrandNew99!",
            "confirm_password": "BrandNew99!",
        })
        assert verify_password(user["email"], "BrandNew99!") is not None
        assert verify_password(user["email"], "OldPass99!") is None
