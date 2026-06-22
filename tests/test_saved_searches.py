"""Tests for POST /searches/save and DELETE /searches/:id routes."""

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
            "email": "ss@example.com",
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
# POST /searches/save
# ---------------------------------------------------------------------------

def test_save_returns_ok_and_id(client):
    rv = client.post("/searches/save", json={"name": "My Search", "params": {"q": "janitorial"}})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert isinstance(data["id"], int)


def test_save_missing_name_returns_400(client):
    rv = client.post("/searches/save", json={"params": {"q": "test"}})
    assert rv.status_code == 400
    assert rv.get_json()["ok"] is False


def test_save_empty_name_returns_400(client):
    rv = client.post("/searches/save", json={"name": "  ", "params": {}})
    assert rv.status_code == 400


def test_save_unauthenticated_returns_401(anon_client):
    rv = anon_client.post("/searches/save", json={"name": "X", "params": {}})
    assert rv.status_code == 401


def test_save_multiple_searches_get_distinct_ids(client):
    rv1 = client.post("/searches/save", json={"name": "A", "params": {}})
    rv2 = client.post("/searches/save", json={"name": "B", "params": {}})
    assert rv1.get_json()["id"] != rv2.get_json()["id"]


# ---------------------------------------------------------------------------
# DELETE /searches/<id>
# ---------------------------------------------------------------------------

def test_delete_own_search_returns_ok(client):
    rv = client.post("/searches/save", json={"name": "To delete", "params": {}})
    search_id = rv.get_json()["id"]
    rv2 = client.delete(f"/searches/{search_id}")
    assert rv2.status_code == 200
    assert rv2.get_json()["ok"] is True


def test_delete_nonexistent_is_idempotent(client):
    rv = client.delete("/searches/99999")
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_delete_unauthenticated_returns_401(anon_client):
    rv = anon_client.delete("/searches/1")
    assert rv.status_code == 401


# ---------------------------------------------------------------------------
# GET /searches page
# ---------------------------------------------------------------------------

def test_searches_page_returns_200(client):
    rv = client.get("/searches")
    assert rv.status_code == 200
    assert b"Saved Searches" in rv.data


def test_searches_page_redirects_when_not_logged_in(anon_client):
    rv = anon_client.get("/searches")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_delete_removes_row_from_db(client, auth_db):
    import sqlite3
    rv = client.post("/searches/save", json={"name": "Gone", "params": {}})
    search_id = rv.get_json()["id"]
    client.delete(f"/searches/{search_id}")
    con = sqlite3.connect(auth_db)
    count = con.execute("SELECT COUNT(*) FROM user_saved_searches WHERE id=?", (search_id,)).fetchone()[0]
    con.close()
    assert count == 0


# ---------------------------------------------------------------------------
# Reload round-trip (incl. the new status filter) + contracts-page quick links
# ---------------------------------------------------------------------------

def test_saved_search_roundtrips_status_and_query(client):
    # save a filter combo that includes the new Open/Active status filter
    client.post("/searches/save", json={
        "name": "Open big contracts",
        "params": {"q": "janitorial", "status": "open", "min_value": "1000000"},
    })
    body = client.get("/searches").get_data(as_text=True)
    assert "Open big contracts" in body
    # the Run link reloads /contracts with the saved params, status included
    assert "/contracts?" in body
    assert "status=open" in body
    assert "q=janitorial" in body


def test_contracts_page_shows_saved_search_links(client):
    client.post("/searches/save", json={
        "name": "Open DoD", "params": {"status": "open", "agency": "DEFENSE"},
    })
    body = client.get("/contracts").get_data(as_text=True)
    assert "Saved searches:" in body            # the quick-links section renders
    assert "Open DoD" in body                    # the saved search appears as a chip
    assert "status=open" in body                 # links back to the filtered list


def test_contracts_page_no_saved_searches_section_when_empty(client):
    body = client.get("/contracts").get_data(as_text=True)
    assert "Saved searches:" not in body         # nothing shown until the user saves one


def test_empty_params_search_links_to_plain_contracts(client):
    client.post("/searches/save", json={"name": "Everything", "params": {}})
    body = client.get("/searches").get_data(as_text=True)
    assert "Everything" in body


def test_list_saved_searches_helper_parses_params(client, auth_db):
    import db as db_module
    from users import get_user_by_email
    client.post("/searches/save", json={"name": "H", "params": {"status": "expired"}})
    uid = get_user_by_email("ss@example.com")["id"]
    items = db_module.list_saved_searches(uid)
    assert len(items) == 1
    assert items[0]["name"] == "H"
    assert items[0]["params"] == {"status": "expired"}
