"""Tests for Saved Searches feature (db layer + HTTP routes)."""

import json
import os
import tempfile

import pytest

import db as db_module
from app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Redirect all db operations to a fresh temp database."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.init_saved_searches_table()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# db layer
# ---------------------------------------------------------------------------

class TestDbLayer:
    def test_create_and_list(self, tmp_db):
        sid = db_module.create_saved_search("DoD Critical", {"agency": "DEFENSE", "priority": "CRITICAL"})
        assert isinstance(sid, int)
        searches = db_module.get_saved_searches()
        assert len(searches) == 1
        assert searches[0]["name"] == "DoD Critical"
        assert searches[0]["filters"]["agency"] == "DEFENSE"

    def test_get_by_id(self, tmp_db):
        sid = db_module.create_saved_search("Expiring Soon", {"days": "90"})
        result = db_module.get_saved_search(sid)
        assert result is not None
        assert result["id"] == sid
        assert result["filters"]["days"] == "90"

    def test_get_missing_returns_none(self, tmp_db):
        assert db_module.get_saved_search(9999) is None

    def test_rename(self, tmp_db):
        sid = db_module.create_saved_search("Old Name", {"q": "defense"})
        assert db_module.rename_saved_search(sid, "New Name") is True
        assert db_module.get_saved_search(sid)["name"] == "New Name"

    def test_rename_missing_returns_false(self, tmp_db):
        assert db_module.rename_saved_search(9999, "X") is False

    def test_delete(self, tmp_db):
        sid = db_module.create_saved_search("To Delete", {"q": "test"})
        assert db_module.delete_saved_search(sid) is True
        assert db_module.get_saved_search(sid) is None

    def test_delete_missing_returns_false(self, tmp_db):
        assert db_module.delete_saved_search(9999) is False

    def test_multiple_searches_ordered_newest_first(self, tmp_db):
        db_module.create_saved_search("First", {"q": "a"})
        db_module.create_saved_search("Second", {"q": "b"})
        searches = db_module.get_saved_searches()
        assert searches[0]["name"] == "Second"
        assert searches[1]["name"] == "First"


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

class TestRoutes:
    def test_list_page_empty(self, client):
        resp = client.get("/saved-searches")
        assert resp.status_code == 200
        assert b"No saved searches yet" in resp.data

    def test_save_redirects_to_list(self, client):
        resp = client.post("/saved-searches/save", data={
            "name": "My Search",
            "q": "janitorial",
            "priority": "CRITICAL",
        })
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/saved-searches")

    def test_save_appears_in_list(self, client):
        client.post("/saved-searches/save", data={"name": "Test Search", "q": "test"})
        resp = client.get("/saved-searches")
        assert b"Test Search" in resp.data

    def test_save_without_name_redirects_back(self, client):
        resp = client.post("/saved-searches/save", data={"name": "", "q": "x"})
        assert resp.status_code == 302

    def test_load_redirects_to_contracts(self, client):
        client.post("/saved-searches/save", data={
            "name": "CRIT", "priority": "CRITICAL"
        })
        searches = db_module.get_saved_searches()
        sid = searches[0]["id"]
        resp = client.get(f"/saved-searches/{sid}/load")
        assert resp.status_code == 302
        assert "priority=CRITICAL" in resp.headers["Location"]

    def test_load_missing_redirects_to_list(self, client):
        resp = client.get("/saved-searches/9999/load")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/saved-searches")

    def test_rename(self, client):
        client.post("/saved-searches/save", data={"name": "Original", "q": "x"})
        searches = db_module.get_saved_searches()
        sid = searches[0]["id"]
        resp = client.post(f"/saved-searches/{sid}/rename", data={"name": "Renamed"})
        assert resp.status_code == 302
        page = client.get("/saved-searches").data
        assert b"Renamed" in page
        assert b"Original" not in page

    def test_rename_empty_name_no_change(self, client):
        client.post("/saved-searches/save", data={"name": "Keep Me", "q": "x"})
        searches = db_module.get_saved_searches()
        sid = searches[0]["id"]
        client.post(f"/saved-searches/{sid}/rename", data={"name": ""})
        page = client.get("/saved-searches").data
        assert b"Keep Me" in page

    def test_delete(self, client):
        client.post("/saved-searches/save", data={"name": "Delete Me", "q": "x"})
        searches = db_module.get_saved_searches()
        sid = searches[0]["id"]
        resp = client.post(f"/saved-searches/{sid}/delete")
        assert resp.status_code == 302
        page = client.get("/saved-searches").data
        assert b"Delete Me" not in page

    def test_delete_missing_still_redirects(self, client):
        resp = client.post("/saved-searches/9999/delete")
        assert resp.status_code == 302

    def test_dashboard_shows_saved_searches(self, client):
        client.post("/saved-searches/save", data={"name": "My Fav", "q": "test"})
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"My Fav" in resp.data

    def test_contracts_page_has_save_form(self, client):
        resp = client.get("/contracts")
        assert resp.status_code == 200
        assert b"saved-searches/save" in resp.data
        assert b"Manage saved searches" in resp.data
