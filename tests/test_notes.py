"""Tests for POST /contract/:id/note route."""

import pytest
import db as db_module


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "notes@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        yield c


@pytest.fixture()
def anon_client(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        yield c


def test_add_note_returns_ok_and_id(client):
    rv = client.post("/contract/C001/note", json={"body": "Follow up next quarter"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert isinstance(data["id"], int)
    assert "created_at" in data


def test_add_note_empty_body_returns_400(client):
    rv = client.post("/contract/C001/note", json={"body": "   "})
    assert rv.status_code == 400
    assert rv.get_json()["ok"] is False


def test_add_note_missing_body_returns_400(client):
    rv = client.post("/contract/C001/note", json={})
    assert rv.status_code == 400


def test_add_note_unauthenticated_redirects_to_login(anon_client):
    # Hardened (Gate 1): rejected by require_login (302 -> /login) before the handler.
    rv = anon_client.post("/contract/C001/note", json={"body": "test"})
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_add_note_persisted_in_db(client, auth_db):
    import sqlite3
    client.post("/contract/C001/note", json={"body": "Stored note"})
    con = sqlite3.connect(auth_db)
    row = con.execute("SELECT body FROM contract_notes WHERE internal_id='C001'").fetchone()
    con.close()
    assert row is not None
    assert row[0] == "Stored note"
