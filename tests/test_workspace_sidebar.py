"""Tests for company workspace display in the authenticated sidebar.

Verifies that:
- Company name appears in the sidebar workspace block when set
- Workspace block is absent when company name is not set
- Company initials avatar character is rendered
- Fallback to email initial in the header avatar when no company name
"""
import pytest
import db as db_module
import users as users_module
from users import set_trial


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "workspace_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(db):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    app_module.app.config["RATELIMIT_ENABLED"] = False
    app_module.app.secret_key = "test-secret"
    with app_module.app.test_client() as c:
        yield c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["onboarding_skipped"] = "1"


def test_workspace_block_shown_when_company_set(db, client):
    user = users_module.create_user("ws@example.com", "Pass1234!", company_name="Omega Inc")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert "sidebar-workspace" in body
    assert "Omega Inc" in body


def test_workspace_avatar_initial(db, client):
    user = users_module.create_user("init@example.com", "Pass1234!", company_name="Zeta Corp")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert "sidebar-workspace-avatar" in body
    assert ">Z<" in body


def test_workspace_block_absent_without_company(db, client):
    user = users_module.create_user("noco@example.com", "Pass1234!")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert "sidebar-workspace" not in body


def test_header_avatar_uses_company_initial_when_set(db, client):
    user = users_module.create_user("hdr@example.com", "Pass1234!", company_name="Kappa Group")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert "header-avatar" in body
    assert ">K<" in body


def test_header_avatar_falls_back_to_email_initial(db, client):
    user = users_module.create_user("xray@example.com", "Pass1234!")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert "header-avatar" in body
    assert ">X<" in body


def test_email_tooltip_preserved_regardless_of_company(db, client):
    user = users_module.create_user("tip@example.com", "Pass1234!", company_name="Alpha LLC")
    set_trial(user["id"], days=14)
    _login(client, user["id"])
    body = client.get("/dashboard").get_data(as_text=True)
    assert 'title="tip@example.com"' in body
