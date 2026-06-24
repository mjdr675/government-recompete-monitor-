"""Tests for Dashboard Improvements — all sections visible on first load."""

import pytest

import db as db_module
from app import app as flask_app


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.init_watchlist_table()
    db_module.init_saved_searches_table()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.secret_key = "test-secret-key"
    with flask_app.test_client() as c:
        c.post("/register", data={
            "email": "testuser@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


class TestDashboardAlwaysVisible:
    def test_watchlist_section_shown_when_empty(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Watchlist" in resp.data
        assert b"Nothing watched yet" in resp.data

    def test_saved_searches_section_shown_when_empty(self, client):
        resp = client.get("/dashboard")
        assert b"Saved Searches" in resp.data
        assert b"No saved searches yet" in resp.data

    def test_alerts_section_shown_always(self, client, monkeypatch):
        monkeypatch.delenv("ALERT_TO", raising=False)
        resp = client.get("/dashboard")
        assert b"Email Alerts" in resp.data
        assert b"Set up email alerts" in resp.data

    def test_alerts_section_shows_configured_state(self, client, monkeypatch):
        monkeypatch.setenv("ALERT_TO", "user@example.com")
        resp = client.get("/dashboard")
        assert b"Configured" in resp.data

    def test_total_contracts_shown(self, client, tmp_db):
        db_module.upsert_contract({"internal_id": "C1", "vendor": "V", "agency": "A",
                                   "value": 100, "priority": "HIGH", "recompete_score": 50})
        resp = client.get("/dashboard")
        assert b"1 contract" in resp.data

    def test_watchlist_shows_contracts_when_populated(self, client, tmp_db):
        db_module.upsert_contract({"internal_id": "C1", "vendor": "Acme Corp", "agency": "DoD",
                                   "value": 500_000, "priority": "CRITICAL", "recompete_score": 90})
        db_module.watch_contract("C1")
        resp = client.get("/dashboard")
        assert b"Acme Corp" in resp.data

    def test_saved_searches_shows_names_when_populated(self, client, tmp_db):
        client.post("/searches/save",
                    json={"name": "My DoD Search", "params": {"agency": "DEFENSE"}},
                    content_type="application/json")
        resp = client.get("/dashboard")
        assert b"My DoD Search" in resp.data

    def test_browse_contracts_link_present_when_watchlist_empty(self, client):
        resp = client.get("/dashboard")
        assert b"Browse contracts to watch" in resp.data

    def test_search_contracts_link_present_when_no_saved_searches(self, client):
        resp = client.get("/dashboard")
        assert b"Search contracts to save" in resp.data

    def test_ingest_link_shown_when_no_contracts(self, client):
        resp = client.get("/dashboard")
        assert b"Ingest data" in resp.data


class TestContractImportCTA:
    def test_shows_import_cta_when_no_profile(self, client):
        resp = client.get("/dashboard")
        body = resp.get_data(as_text=True)
        assert "Import" in body
        assert "import-contracts" in body

    def test_import_cta_links_to_profile_anchor(self, client):
        resp = client.get("/dashboard")
        body = resp.get_data(as_text=True)
        assert "/company-profile#import-contracts" in body

    def test_import_cta_when_profile_has_no_identifiers(self, client, tmp_db):
        from db import save_company_profile
        import sqlite3
        con = sqlite3.connect(tmp_db)
        uid = con.execute("SELECT id FROM users WHERE email='testuser@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"company_name": "NoIdentifierCo"})
        resp = client.get("/dashboard")
        body = resp.get_data(as_text=True)
        assert "/company-profile#import-contracts" in body

    def test_no_stale_add_vendor_name_text(self, client):
        resp = client.get("/dashboard")
        body = resp.get_data(as_text=True)
        assert "Add vendor name" not in body

    def test_vendor_name_match_still_shows_contracts_section(self, client, tmp_db):
        from db import save_company_profile
        import sqlite3
        con = sqlite3.connect(tmp_db)
        uid = con.execute("SELECT id FROM users WHERE email='testuser@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"vendor_name": "Acme Test Corp"})
        resp = client.get("/dashboard")
        body = resp.get_data(as_text=True)
        # My Contracts panel always rendered
        assert "panel-my-contracts" in body
