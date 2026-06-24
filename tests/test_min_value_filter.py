"""Tests for min_value filter in get_contracts() and the /contracts route."""

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


def _seed(values):
    """Insert minimal contract rows with the given dollar values."""
    for i, v in enumerate(values):
        db_module.upsert_contract({
            "internal_id": f"ID{i}",
            "award_id": f"AW{i}",
            "vendor": f"Vendor {i}",
            "agency": "TEST AGENCY",
            "value": v,
            "recompete_score": 50,
            "priority": "MEDIUM",
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
# db layer
# ---------------------------------------------------------------------------

class TestGetContractsMinValue:
    def test_no_filter_returns_all(self, tmp_db):
        _seed([500_000, 1_000_000, 5_000_000])
        result = db_module.get_contracts()
        assert result["total"] == 3

    def test_min_value_excludes_below(self, tmp_db):
        _seed([500_000, 1_000_000, 5_000_000])
        result = db_module.get_contracts(min_value=1_000_000)
        assert result["total"] == 2
        values = [r["value"] for r in result["contracts"]]
        assert all(v >= 1_000_000 for v in values)
        assert 500_000 not in values

    def test_min_value_zero_returns_all(self, tmp_db):
        _seed([0, 100, 999_999])
        result = db_module.get_contracts(min_value=0)
        assert result["total"] == 3

    def test_min_value_above_all_returns_empty(self, tmp_db):
        _seed([100_000, 200_000])
        result = db_module.get_contracts(min_value=999_999_999)
        assert result["total"] == 0
        assert result["contracts"] == []

    def test_min_value_exact_boundary_included(self, tmp_db):
        _seed([999_999, 1_000_000])
        result = db_module.get_contracts(min_value=1_000_000)
        assert result["total"] == 1
        assert result["contracts"][0]["value"] == 1_000_000

    def test_min_value_combines_with_priority_filter(self, tmp_db):
        db_module.upsert_contract({
            "internal_id": "C1", "vendor": "A", "agency": "X",
            "value": 2_000_000, "priority": "CRITICAL", "recompete_score": 90,
        })
        db_module.upsert_contract({
            "internal_id": "C2", "vendor": "B", "agency": "X",
            "value": 2_000_000, "priority": "LOW", "recompete_score": 10,
        })
        db_module.upsert_contract({
            "internal_id": "C3", "vendor": "C", "agency": "X",
            "value": 500_000, "priority": "CRITICAL", "recompete_score": 80,
        })
        result = db_module.get_contracts(min_value=1_000_000, priority="CRITICAL")
        assert result["total"] == 1
        assert result["contracts"][0]["internal_id"] == "C1"

    def test_pagination_respected_with_min_value(self, tmp_db):
        _seed([1_000_000] * 30)
        page1 = db_module.get_contracts(min_value=1_000_000, page=1, limit=10)
        page2 = db_module.get_contracts(min_value=1_000_000, page=2, limit=10)
        assert page1["total"] == 30
        assert page1["count"] == 10
        assert page2["count"] == 10


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------

class TestContractsRouteMinValue:
    def test_min_value_param_accepted(self, client, tmp_db):
        _seed([500_000, 2_000_000])
        resp = client.get("/contracts?min_value=1000000")
        assert resp.status_code == 200

    def test_min_value_filters_results(self, client, tmp_db):
        _seed([500_000, 2_000_000])
        resp = client.get("/contracts?min_value=1000000")
        assert b"Vendor 0" not in resp.data   # 500k — excluded
        assert b"Vendor 1" in resp.data        # 2M — included

    def test_no_min_value_shows_all(self, client, tmp_db):
        _seed([500_000, 2_000_000])
        resp = client.get("/contracts")
        assert b"Vendor 0" in resp.data
        assert b"Vendor 1" in resp.data

    def test_min_value_preserved_in_pagination_links(self, client, tmp_db):
        _seed([1_000_000] * 30)
        resp = client.get("/contracts?min_value=1000000")
        assert resp.status_code == 200
