"""Tests for R-11: login page forgot-password link and subtitle text."""
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


class TestLoginPage:
    def test_login_page_accessible(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_login_page_has_forgot_password_link(self, client):
        resp = client.get("/login")
        assert b"/forgot-password" in resp.data

    def test_login_page_has_register_link(self, client):
        resp = client.get("/login")
        assert b"/register" in resp.data

    def test_forgot_password_page_accessible(self, client):
        resp = client.get("/forgot-password")
        assert resp.status_code == 200
