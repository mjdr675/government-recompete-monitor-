"""Tests for human-readable view filter labels — Task 059."""

import pytest
import db as db_module
from views import format_filter_summary, format_filter_value


# ---------------------------------------------------------------------------
# format_filter_value
# ---------------------------------------------------------------------------

class TestFormatFilterValue:
    def test_days_adds_suffix(self):
        assert format_filter_value("days", 90) == "90 days"

    def test_priority_title_cases(self):
        assert format_filter_value("priority", "CRITICAL") == "Critical"

    def test_priority_mixed_case(self):
        assert format_filter_value("priority", "HIGH") == "High"

    def test_min_value_currency(self):
        assert format_filter_value("min_value", 1000000) == "$1,000,000"

    def test_min_value_small(self):
        assert format_filter_value("min_value", 500) == "$500"

    def test_min_value_large(self):
        assert format_filter_value("min_value", 10_000_000) == "$10,000,000"

    def test_unknown_key_returns_string(self):
        assert format_filter_value("naics_code", "561720") == "561720"

    def test_agency_returns_string(self):
        assert format_filter_value("agency", "DEFENSE") == "DEFENSE"


# ---------------------------------------------------------------------------
# format_filter_summary
# ---------------------------------------------------------------------------

class TestFormatFilterSummary:
    def test_empty_filters_returns_empty_string(self):
        assert format_filter_summary({}) == ""

    def test_days_label(self):
        result = format_filter_summary({"days": 90})
        assert result == "Expiring within: 90 days"

    def test_priority_label_and_titlecase(self):
        result = format_filter_summary({"priority": "CRITICAL"})
        assert result == "Priority: Critical"

    def test_min_value_label_and_currency(self):
        result = format_filter_summary({"min_value": 1000000})
        assert result == "Min value: $1,000,000"

    def test_agency_label(self):
        result = format_filter_summary({"agency": "DEFENSE"})
        assert result == "Agency: DEFENSE"

    def test_multiple_filters_joined(self):
        result = format_filter_summary({"agency": "DEFENSE", "priority": "CRITICAL"})
        assert "Agency: DEFENSE" in result
        assert "Priority: Critical" in result
        assert ", " in result

    def test_unknown_key_falls_through(self):
        result = format_filter_summary({"naics_code": "561720"})
        assert "NAICS: 561720" in result

    def test_completely_unknown_key_uses_key_name(self):
        result = format_filter_summary({"totally_unknown": "value"})
        assert "totally_unknown: value" in result


# ---------------------------------------------------------------------------
# /views route renders human-readable labels
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


def test_views_page_shows_expiring_within(client):
    rv = client.get("/views")
    assert b"Expiring within" in rv.data


def test_views_page_shows_priority_titlecase(client):
    rv = client.get("/views")
    # Should show "Critical" not "CRITICAL"
    assert b"Critical" in rv.data


def test_views_page_shows_min_value_currency(client):
    rv = client.get("/views")
    assert b"$1,000,000" in rv.data


def test_views_page_no_raw_days_key(client):
    rv = client.get("/views")
    # Raw "days: 90" should not appear
    assert b"days: 90" not in rv.data
    assert b"days:" not in rv.data


def test_views_page_no_raw_priority_key(client):
    rv = client.get("/views")
    assert b"priority:" not in rv.data


def test_views_page_no_raw_min_value_key(client):
    rv = client.get("/views")
    assert b"min_value:" not in rv.data
