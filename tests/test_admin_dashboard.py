"""Tests for R-10: admin dashboard at /admin."""
import pytest
import db as db_module
import users as users_module
from users import set_trial, set_subscription


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


class TestAdminAccess:
    def test_admin_returns_404_when_no_admin_email_set(self, db, client, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        user = users_module.create_user("someone@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/admin")
        assert resp.status_code == 404

    def test_admin_returns_404_for_non_admin_user(self, db, client, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        user = users_module.create_user("regular@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/admin")
        assert resp.status_code == 404

    def test_admin_returns_404_when_unauthenticated(self, db, client, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        resp = client.get("/admin")
        # Unauthenticated → require_login redirects or 404
        assert resp.status_code in (301, 302, 404)

    def test_admin_accessible_to_admin_user(self, db, client, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        user = users_module.create_user("admin@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/admin")
        assert resp.status_code == 200

    def test_admin_email_match_is_case_insensitive(self, db, client, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "Admin@Example.COM")
        user = users_module.create_user("admin@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/admin")
        assert resp.status_code == 200


class TestAdminContent:
    def _setup_admin(self, db, client, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        user = users_module.create_user("admin@example.com", "password123")
        set_trial(user["id"], days=14)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        return user

    def test_shows_total_users(self, db, client, monkeypatch):
        self._setup_admin(db, client, monkeypatch)
        users_module.create_user("a@example.com", "password123")
        users_module.create_user("b@example.com", "password123")
        resp = client.get("/admin")
        body = resp.data.decode()
        assert "Total Users" in body

    def test_shows_user_emails(self, db, client, monkeypatch):
        self._setup_admin(db, client, monkeypatch)
        users_module.create_user("beta@example.com", "password123")
        resp = client.get("/admin")
        assert b"beta@example.com" in resp.data

    def test_shows_subscription_status(self, db, client, monkeypatch):
        self._setup_admin(db, client, monkeypatch)
        resp = client.get("/admin")
        body = resp.data.decode()
        assert "trial" in body.lower() or "active" in body.lower()

    def test_shows_mrr(self, db, client, monkeypatch):
        self._setup_admin(db, client, monkeypatch)
        resp = client.get("/admin")
        body = resp.data.decode()
        assert "MRR" in body

    def test_active_user_increases_mrr(self, db, client, monkeypatch):
        self._setup_admin(db, client, monkeypatch)
        paid = users_module.create_user("paid@example.com", "password123")
        set_subscription(paid["id"], "cus_test123", "active")
        resp = client.get("/admin")
        body = resp.data.decode()
        assert "$49" in body or "49" in body
