"""Tests for R-03: security headers on all responses."""
import pytest
import db as db_module


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


class TestSecurityHeaders:
    def test_x_frame_options_on_landing(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_x_content_type_options_on_landing(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy_on_landing(self, client):
        resp = client.get("/")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_csp_header_present(self, client):
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp

    def test_csp_allows_stripe(self, client):
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "stripe.com" in csp

    def test_x_frame_options_on_login(self, client):
        resp = client.get("/login")
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_x_frame_options_on_health(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_session_cookie_samesite_configured(self, db):
        import app as app_module
        assert app_module.app.config.get("SESSION_COOKIE_SAMESITE") == "Lax"

    def test_session_cookie_httponly_configured(self, db):
        import app as app_module
        assert app_module.app.config.get("SESSION_COOKIE_HTTPONLY") is True
