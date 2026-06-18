"""Tests for Opportunity Watchlists — db layer and HTTP routes."""

import pytest

import db as db_module
from app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.init_watchlist_table()
    yield db_path


def _seed_contract(internal_id="C1", priority="HIGH", value=500_000):
    db_module.upsert_contract({
        "internal_id": internal_id,
        "vendor": f"Vendor {internal_id}",
        "agency": "TEST",
        "value": value,
        "priority": priority,
        "recompete_score": 70,
    })


@pytest.fixture()
def client(tmp_db):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# db layer
# ---------------------------------------------------------------------------

class TestWatchlistDb:
    def test_watch_and_is_watched(self, tmp_db):
        _seed_contract("C1")
        db_module.watch_contract("C1")
        assert db_module.is_watched("C1") is True

    def test_unwatch(self, tmp_db):
        _seed_contract("C1")
        db_module.watch_contract("C1")
        db_module.unwatch_contract("C1")
        assert db_module.is_watched("C1") is False

    def test_watch_idempotent(self, tmp_db):
        _seed_contract("C1")
        db_module.watch_contract("C1")
        db_module.watch_contract("C1")
        assert len(db_module.get_watchlist()) == 1

    def test_is_watched_false_for_unknown(self, tmp_db):
        assert db_module.is_watched("NONEXISTENT") is False

    def test_get_watchlist_empty(self, tmp_db):
        assert db_module.get_watchlist() == []

    def test_get_watchlist_returns_contract_rows(self, tmp_db):
        _seed_contract("C1")
        _seed_contract("C2")
        db_module.watch_contract("C1")
        db_module.watch_contract("C2")
        rows = db_module.get_watchlist()
        assert len(rows) == 2
        ids = {r["internal_id"] for r in rows}
        assert ids == {"C1", "C2"}

    def test_get_watchlist_orders_by_score_desc(self, tmp_db):
        db_module.upsert_contract({"internal_id": "LOW", "vendor": "V", "agency": "A",
                                   "value": 100, "priority": "LOW", "recompete_score": 10})
        db_module.upsert_contract({"internal_id": "HIGH", "vendor": "V", "agency": "A",
                                   "value": 100, "priority": "HIGH", "recompete_score": 90})
        db_module.watch_contract("LOW")
        db_module.watch_contract("HIGH")
        rows = db_module.get_watchlist()
        assert rows[0]["internal_id"] == "HIGH"

    def test_unwatch_nonexistent_is_safe(self, tmp_db):
        db_module.unwatch_contract("NONEXISTENT")


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

class TestWatchlistRoutes:
    def test_watchlist_page_empty(self, client):
        resp = client.get("/watchlist")
        assert resp.status_code == 200
        assert b"watchlist is empty" in resp.data

    def test_watch_redirects(self, client, tmp_db):
        _seed_contract("C1")
        resp = client.post("/watch/C1")
        assert resp.status_code == 302

    def test_watch_then_appears_on_watchlist_page(self, client, tmp_db):
        _seed_contract("C1")
        client.post("/watch/C1")
        resp = client.get("/watchlist")
        assert b"Vendor C1" in resp.data

    def test_unwatch_removes_from_watchlist(self, client, tmp_db):
        _seed_contract("C1")
        client.post("/watch/C1")
        client.post("/unwatch/C1", data={"next": "/watchlist"})
        resp = client.get("/watchlist")
        assert b"Vendor C1" not in resp.data

    def test_watch_redirects_to_next_param(self, client, tmp_db):
        _seed_contract("C1")
        resp = client.post("/watch/C1", data={"next": "/watchlist"})
        assert resp.headers["Location"].endswith("/watchlist")

    def test_unwatch_redirects_to_next_param(self, client, tmp_db):
        _seed_contract("C1")
        db_module.watch_contract("C1")
        resp = client.post("/unwatch/C1", data={"next": "/watchlist"})
        assert resp.headers["Location"].endswith("/watchlist")

    def test_contract_detail_shows_watch_button(self, client, tmp_db):
        _seed_contract("C1")
        resp = client.get("/contract/C1")
        assert resp.status_code == 200
        assert b"Watch this contract" in resp.data

    def test_contract_detail_shows_unwatch_after_watching(self, client, tmp_db):
        _seed_contract("C1")
        client.post("/watch/C1")
        resp = client.get("/contract/C1")
        assert b"Watching" in resp.data
        assert b"Watch this contract" not in resp.data

    def test_dashboard_shows_watchlist_when_populated(self, client, tmp_db):
        _seed_contract("C1")
        client.post("/watch/C1")
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Watchlist" in resp.data

    def test_watchlist_nav_link_present(self, client):
        resp = client.get("/watchlist")
        assert b'href="/watchlist"' in resp.data
