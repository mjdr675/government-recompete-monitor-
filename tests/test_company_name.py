"""Tests for optional company name: collected at signup, shown in the header.

Backward compatible — existing users / callers that omit company_name keep working
and the header falls back to the email address.
"""
import pytest

import db as db_module
import users as users_module


@pytest.fixture()
def auth_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


# ── model layer ────────────────────────────────────────────────────────────────
def test_create_user_stores_company_name(auth_db):
    u = users_module.create_user("a@example.com", "password123", company_name="Acme Janitorial")
    full = users_module.get_user_by_id(u["id"])
    assert full["company_name"] == "Acme Janitorial"


def test_create_user_without_company_is_backward_compatible(auth_db):
    # old call signature (no company_name) still works → stored as NULL
    u = users_module.create_user("b@example.com", "password123")
    full = users_module.get_user_by_id(u["id"])
    assert full["company_name"] is None


def test_blank_company_name_is_null(auth_db):
    u = users_module.create_user("c@example.com", "password123", company_name="   ")
    full = users_module.get_user_by_id(u["id"])
    assert full["company_name"] is None


# ── registration + header ──────────────────────────────────────────────────────
def test_registration_collects_company_and_header_shows_it(client):
    rv = client.post("/register", data={
        "email": "ops@acme.com", "password": "password123",
        "confirm": "password123", "company_name": "Acme Facilities",
    }, follow_redirects=True)
    assert rv.status_code == 200
    page = client.get("/dashboard")
    body = page.get_data(as_text=True)
    assert "Acme Facilities" in body          # company name shown in the header
    assert 'title="ops@acme.com"' in body     # email preserved as tooltip


def test_header_falls_back_to_email_without_company(client):
    client.post("/register", data={
        "email": "noco@example.com", "password": "password123",
        "confirm": "password123",
    }, follow_redirects=True)
    body = client.get("/dashboard").get_data(as_text=True)
    assert "noco@example.com" in body
