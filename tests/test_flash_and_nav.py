"""Tests for R-08: global flash messages in base.html and Account nav link."""
import pytest
import db as db_module
import users as users_module
from users import set_trial


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


def _login(client, email="flash@example.com"):
    user = users_module.create_user(email, "password123")
    set_trial(user["id"], days=14)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["onboarding_skipped"] = "1"
    return user


class TestGlobalFlashMessages:
    def test_success_flash_shown_in_dashboard(self, db, client):
        _login(client)
        with client.session_transaction() as sess:
            from flask import Flask
            # Inject a flash message via the session directly
            sess["_flashes"] = [("success", "Settings saved!")]
        resp = client.get("/dashboard")
        assert b"Settings saved!" in resp.data

    def test_error_flash_shown_in_dashboard(self, db, client):
        _login(client)
        with client.session_transaction() as sess:
            sess["_flashes"] = [("error", "Something went wrong")]
        resp = client.get("/dashboard")
        assert b"Something went wrong" in resp.data

    def test_success_flash_has_green_style(self, db, client):
        _login(client)
        with client.session_transaction() as sess:
            sess["_flashes"] = [("success", "Done")]
        resp = client.get("/dashboard")
        body = resp.data.decode()
        # Green background present
        assert "d1fae5" in body or "10b981" in body

    def test_error_flash_has_red_style(self, db, client):
        _login(client)
        with client.session_transaction() as sess:
            sess["_flashes"] = [("error", "Failed")]
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "fee2e2" in body or "ef4444" in body

    def test_alert_settings_saved_flash_still_works(self, db, client):
        _login(client)
        # POST to /settings/alerts triggers flash("Alert settings saved.", "success")
        resp = client.post("/settings/alerts", data={
            "expiry_days": "30",
            "enabled": "1",
        }, follow_redirects=True)
        assert b"Alert settings saved" in resp.data


class TestAccountNavLink:
    def test_account_link_in_nav_when_logged_in(self, db, client):
        _login(client)
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "/settings/account" in body

    def test_account_link_not_shown_when_logged_out(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        # The Account link is only for authenticated nav
        assert "Account" not in body or "/settings/account" not in body
