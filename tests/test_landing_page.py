"""Tests for R-01: public landing page and nav overhaul."""
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


class TestPublicLandingPage:
    def test_root_returns_landing_for_unauthenticated(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_landing_page_contains_product_name(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "Recompete" in body

    def test_landing_page_contains_register_cta(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "/register" in body

    def test_landing_page_contains_login_link(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "/login" in body

    def test_landing_page_shows_pricing(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "49" in body  # $49/month

    def test_landing_page_no_authenticated_nav(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "/contracts" not in body
        assert "/watchlist" not in body


class TestRootRedirectsAuthenticated:
    def test_authenticated_root_redirects_to_dashboard(self, db, client):
        user = users_module.create_user("nav@example.com", "password123")
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/")
        assert resp.status_code in (301, 302)
        assert "/dashboard" in resp.headers["Location"]


class TestDashboardRoute:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers["Location"]

    def test_dashboard_accessible_when_logged_in(self, db, client):
        user = users_module.create_user("dash@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_shows_trial_banner(self, db, client):
        user = users_module.create_user("trial@example.com", "password123")
        set_trial(user["id"], days=10)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "trial" in body.lower() or "Trial" in body


class TestNavConditional:
    def test_nav_shows_signin_when_logged_out(self, client):
        resp = client.get("/")
        body = resp.data.decode()
        assert "Sign in" in body or "signin" in body.lower()

    def test_nav_shows_app_links_when_logged_in(self, db, client):
        user = users_module.create_user("navtest@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "/contracts" in body
        assert "/watchlist" in body
        assert "Sign out" in body or "/logout" in body

    def test_nav_shows_alerts_link_when_logged_in(self, db, client):
        user = users_module.create_user("alertsnav@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "/settings/alerts" in body
