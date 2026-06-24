"""Tests for /contracts.csv export route and all_rows db flag."""

import csv
import io
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
    yield db_path


def _seed(n=30):
    for i in range(n):
        db_module.upsert_contract({
            "internal_id": f"C{i}",
            "vendor": f"Vendor {i}",
            "agency": "DEFENSE" if i % 2 == 0 else "NASA",
            "value": (i + 1) * 100_000,
            "priority": "CRITICAL" if i < 5 else "HIGH",
            "recompete_score": 100 - i,
        })


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
        yield c


# ---------------------------------------------------------------------------
# db layer — all_rows flag
# ---------------------------------------------------------------------------

class TestAllRows:
    def test_all_rows_returns_all_without_pagination(self, tmp_db):
        _seed(30)
        result = db_module.get_contracts(all_rows=True)
        assert result["count"] == 30

    def test_default_still_paginates(self, tmp_db):
        _seed(30)
        result = db_module.get_contracts(limit=10)
        assert result["count"] == 10
        assert result["total"] == 30

    def test_all_rows_with_filter(self, tmp_db):
        _seed(30)
        result = db_module.get_contracts(priority="CRITICAL", all_rows=True)
        assert result["count"] == 5
        assert all(r["priority"] == "CRITICAL" for r in result["contracts"])


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------

class TestContractsCsv:
    def test_returns_csv_content_type(self, client, tmp_db):
        _seed(5)
        resp = client.get("/contracts/export.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_content_disposition_attachment(self, client, tmp_db):
        _seed(5)
        resp = client.get("/contracts/export.csv")
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "contracts.csv" in resp.headers["Content-Disposition"]

    def test_csv_has_header_row(self, client, tmp_db):
        _seed(3)
        resp = client.get("/contracts/export.csv")
        reader = csv.DictReader(io.StringIO(resp.data.decode()))
        assert "vendor" in reader.fieldnames
        assert "agency" in reader.fieldnames
        assert "value" in reader.fieldnames
        assert "priority" in reader.fieldnames

    def test_csv_exports_all_matching_rows(self, client, tmp_db):
        _seed(30)
        resp = client.get("/contracts/export.csv")
        reader = csv.DictReader(io.StringIO(resp.data.decode()))
        rows = list(reader)
        assert len(rows) == 30

    def test_csv_respects_priority_filter(self, client, tmp_db):
        _seed(30)
        resp = client.get("/contracts/export.csv?priority=CRITICAL")
        reader = csv.DictReader(io.StringIO(resp.data.decode()))
        rows = list(reader)
        assert len(rows) == 5
        assert all(r["priority"] == "CRITICAL" for r in rows)

    def test_csv_respects_agency_filter(self, client, tmp_db):
        _seed(10)
        resp = client.get("/contracts/export.csv?agency=NASA")
        reader = csv.DictReader(io.StringIO(resp.data.decode()))
        rows = list(reader)
        assert all("NASA" in r["agency"] for r in rows)

    def test_csv_empty_when_no_matches(self, client, tmp_db):
        _seed(5)
        resp = client.get("/contracts/export.csv?priority=LOW")
        reader = csv.DictReader(io.StringIO(resp.data.decode()))
        rows = list(reader)
        assert len(rows) == 0

    def test_export_link_on_contracts_page(self, client, tmp_db):
        resp = client.get("/contracts")
        assert b"export.csv" in resp.data
        assert b"Export" in resp.data
