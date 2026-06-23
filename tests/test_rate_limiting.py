"""Tests for R-04: rate limiting on /demo and /early-access."""
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
    # Use per-test in-memory storage so rate limits don't bleed between tests
    app_module.limiter.reset()
    with app_module.app.test_client() as c:
        yield c


class TestDemoRateLimit:
    def test_demo_get_always_accessible(self, client):
        for _ in range(10):
            resp = client.get("/demo")
            assert resp.status_code == 200

    def test_demo_post_accepted_within_limit(self, client):
        resp = client.post("/demo", data={
            "email": "test@example.com",
            "name": "Test",
            "company": "ACME",
        })
        # Accepted (even if HubSpot/DB fail gracefully, not rate-limited)
        assert resp.status_code != 429

    def test_demo_post_rate_limited_after_threshold(self, client):
        data = {"email": "spam@example.com", "name": "Bot", "company": "Bot Co"}
        # 5 within limit, 6th should be 429
        for _ in range(5):
            client.post("/demo", data=data)
        resp = client.post("/demo", data=data)
        assert resp.status_code == 429


class TestEarlyAccessRateLimit:
    def test_early_access_get_always_accessible(self, client):
        for _ in range(10):
            resp = client.get("/early-access")
            assert resp.status_code == 200

    def test_early_access_post_accepted_within_limit(self, client):
        resp = client.post("/early-access", data={"email": "ok@example.com"})
        assert resp.status_code != 429

    def test_early_access_post_rate_limited_after_threshold(self, client):
        for _ in range(5):
            client.post("/early-access", data={"email": "bot@example.com"})
        resp = client.post("/early-access", data={"email": "bot@example.com"})
        assert resp.status_code == 429
