"""Tests for R-09: rate limiting on POST /register."""
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
    app_module.limiter.reset()
    with app_module.app.test_client() as c:
        yield c


class TestRegisterRateLimit:
    def test_register_get_always_accessible(self, client):
        for _ in range(15):
            resp = client.get("/register")
            assert resp.status_code == 200

    def test_register_post_accepted_within_limit(self, client):
        resp = client.post("/register", data={
            "email": "user1@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        # Redirect on success or 200 on validation error — never 429 within limit
        assert resp.status_code != 429

    def test_register_post_rate_limited_after_threshold(self, client):
        for i in range(10):
            client.post("/register", data={
                "email": f"user{i}@example.com",
                "password": "password123",
                "confirm": "password123",
            })
        resp = client.post("/register", data={
            "email": "overflow@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        assert resp.status_code == 429
