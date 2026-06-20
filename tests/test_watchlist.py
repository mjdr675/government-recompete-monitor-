"""Tests for POST /watchlist/add and POST /watchlist/remove routes."""

import pytest
import db as db_module


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield db_path


@pytest.fixture()
def client(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "wl@example.com",
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


# ---------------------------------------------------------------------------
# /watchlist/add
# ---------------------------------------------------------------------------

def test_add_returns_ok(client):
    rv = client.post("/watchlist/add", json={"internal_id": "C001"})
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_add_duplicate_is_idempotent(client):
    client.post("/watchlist/add", json={"internal_id": "C001"})
    rv = client.post("/watchlist/add", json={"internal_id": "C001"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data.get("already") is True


def test_add_missing_internal_id_returns_400(client):
    rv = client.post("/watchlist/add", json={})
    assert rv.status_code == 400
    assert rv.get_json()["ok"] is False


def test_add_unauthenticated_returns_401(anon_client):
    rv = anon_client.post("/watchlist/add", json={"internal_id": "C001"})
    assert rv.status_code == 401


# ---------------------------------------------------------------------------
# /watchlist/remove
# ---------------------------------------------------------------------------

def test_remove_returns_ok(client):
    client.post("/watchlist/add", json={"internal_id": "C001"})
    rv = client.post("/watchlist/remove", json={"internal_id": "C001"})
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_remove_nonexistent_is_idempotent(client):
    rv = client.post("/watchlist/remove", json={"internal_id": "DOES_NOT_EXIST"})
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_remove_unauthenticated_returns_401(anon_client):
    rv = anon_client.post("/watchlist/remove", json={"internal_id": "C001"})
    assert rv.status_code == 401


def test_add_then_remove_clears_bookmark(client, auth_db):
    import sqlite3
    client.post("/watchlist/add", json={"internal_id": "C001"})
    client.post("/watchlist/remove", json={"internal_id": "C001"})
    con = sqlite3.connect(auth_db)
    count = con.execute("SELECT COUNT(*) FROM user_watchlist WHERE internal_id='C001'").fetchone()[0]
    con.close()
    assert count == 0


# ---------------------------------------------------------------------------
# GET /watchlist page
# ---------------------------------------------------------------------------

def test_watchlist_page_returns_200(client):
    rv = client.get("/watchlist")
    assert rv.status_code == 200
    assert b"Watchlist" in rv.data


def test_watchlist_page_redirects_when_not_logged_in(anon_client):
    rv = anon_client.get("/watchlist")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]
