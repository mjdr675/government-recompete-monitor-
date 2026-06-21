"""Tests for min_value filter — Task 056."""

import sqlite3
import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_app.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID001", "AWARD-001", "Acme Corp", "DOD", 500_000, "2025-12-31", "HIGH", 80),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID002", "AWARD-002", "Beta LLC", "DHS", 1_000_000, "2026-06-30", "CRITICAL", 90),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID003", "AWARD-003", "Gamma Inc", "DOE", 5_000_000, "2027-01-01", "CRITICAL", 95),
        )
        con.commit()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ---------------------------------------------------------------------------
# db.get_contracts min_value tests
# ---------------------------------------------------------------------------

class TestGetContractsMinValue:
    def test_no_min_value_returns_all(self, test_db):
        result = db_module.get_contracts()
        assert result["total"] == 3

    def test_min_value_filters_below_threshold(self, test_db):
        result = db_module.get_contracts(min_value=1_000_000)
        assert result["total"] == 2
        values = [r["value"] for r in result["contracts"]]
        assert all(v >= 1_000_000 for v in values)

    def test_min_value_exact_match_included(self, test_db):
        result = db_module.get_contracts(min_value=1_000_000)
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "ID002" in ids

    def test_min_value_excludes_below(self, test_db):
        result = db_module.get_contracts(min_value=1_000_000)
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "ID001" not in ids

    def test_min_value_high_returns_one(self, test_db):
        result = db_module.get_contracts(min_value=2_000_000)
        assert result["total"] == 1
        assert result["contracts"][0]["internal_id"] == "ID003"

    def test_min_value_above_all_returns_empty(self, test_db):
        result = db_module.get_contracts(min_value=10_000_000)
        assert result["total"] == 0
        assert result["contracts"] == []

    def test_min_value_zero_returns_all(self, test_db):
        result = db_module.get_contracts(min_value=0)
        assert result["total"] == 3

    def test_min_value_combined_with_agency(self, test_db):
        result = db_module.get_contracts(min_value=1_000_000, agency="DOE")
        assert result["total"] == 1
        assert result["contracts"][0]["internal_id"] == "ID003"

    def test_min_value_combined_with_priority(self, test_db):
        result = db_module.get_contracts(min_value=1_000_000, priority="CRITICAL")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "ID003" in ids
        assert "ID001" not in ids

    def test_none_min_value_returns_all(self, test_db):
        result = db_module.get_contracts(min_value=None)
        assert result["total"] == 3


# ---------------------------------------------------------------------------
# /contracts route min_value tests
# ---------------------------------------------------------------------------

class TestContractsRouteMinValue:
    def test_no_min_value_returns_200(self, client):
        rv = client.get("/contracts")
        assert rv.status_code == 200

    def test_positive_min_value_returns_200(self, client):
        rv = client.get("/contracts?min_value=1000000")
        assert rv.status_code == 200

    def test_negative_min_value_returns_400(self, client):
        rv = client.get("/contracts?min_value=-1")
        assert rv.status_code == 400

    def test_negative_float_min_value_returns_400(self, client):
        rv = client.get("/contracts?min_value=-0.01")
        assert rv.status_code == 400

    def test_zero_min_value_returns_200(self, client):
        rv = client.get("/contracts?min_value=0")
        assert rv.status_code == 200

    def test_min_value_filters_results(self, client):
        rv = client.get("/contracts?min_value=2000000")
        assert rv.status_code == 200
        assert b"Gamma Inc" in rv.data
        assert b"Acme Corp" not in rv.data

    def test_min_value_high_value_view(self, client):
        rv = client.get("/contracts?min_value=1000000")
        assert rv.status_code == 200
        assert b"Acme Corp" not in rv.data

    def test_non_numeric_min_value_ignored(self, client):
        rv = client.get("/contracts?min_value=abc")
        assert rv.status_code == 200


# ---------------------------------------------------------------------------
# min_value dropdown renders correctly (P-02)
# ---------------------------------------------------------------------------

class TestMinValueDropdown:
    def test_dropdown_select_rendered_not_text_input(self, client):
        rv = client.get("/contracts")
        assert b'select name="min_value"' in rv.data

    def test_dropdown_shows_any_size_option(self, client):
        rv = client.get("/contracts")
        assert b"Any size" in rv.data

    def test_dropdown_shows_1m_option(self, client):
        rv = client.get("/contracts")
        assert b"$1M+" in rv.data

    def test_dropdown_selects_matching_threshold(self, client):
        rv = client.get("/contracts?min_value=1000000")
        assert b'value="1000000" selected' in rv.data or b'value="1000000"  selected' in rv.data or b"selected" in rv.data

    def test_sort_link_preserves_min_value(self, client):
        rv = client.get("/contracts?min_value=1000000&sort=value&dir=asc")
        assert b"min_value=1000000" in rv.data

    def test_sort_link_vendor_includes_min_value(self, client):
        rv = client.get("/contracts?min_value=5000000")
        assert b"min_value=5000000" in rv.data
