"""Tests for R-05: onboarding banner for new users."""
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


def _login(client, db):
    user = users_module.create_user("onboard@example.com", "password123")
    set_trial(user["id"], days=14)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    return user


class TestOnboardingBanner:
    def test_banner_shown_to_new_user(self, db, client):
        _login(client, db)
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "get started" in body.lower() or "Welcome" in body

    def test_banner_hidden_after_dismiss(self, db, client):
        _login(client, db)
        # Dismiss the banner
        client.post("/onboarding/dismiss")
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "get started" not in body.lower() or "onboarding" not in body.lower()

    def test_dismiss_redirects_to_dashboard(self, db, client):
        _login(client, db)
        resp = client.post("/onboarding/dismiss")
        assert resp.status_code in (301, 302)
        assert "/dashboard" in resp.headers["Location"]

    def test_dismiss_sets_session_flag(self, db, client):
        _login(client, db)
        client.post("/onboarding/dismiss")
        with client.session_transaction() as sess:
            assert sess.get("onboarding_dismissed") == "1"

    def test_banner_not_shown_when_dismissed(self, db, client):
        _login(client, db)
        with client.session_transaction() as sess:
            sess["onboarding_dismissed"] = "1"
        resp = client.get("/dashboard")
        body = resp.data.decode()
        # The specific onboarding div should not be present
        assert "here's how to get started" not in body.lower()

    def test_dismiss_requires_post(self, db, client):
        _login(client, db)
        resp = client.get("/onboarding/dismiss")
        assert resp.status_code == 405
