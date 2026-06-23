"""
Tests for contract-intelligence-tools lane.

Covers:
- infer_category keyword + NAICS matching
- extract_raw_field JSON parsing
- Multi-contract compare (3 and 4 contracts)
- Backward-compatible 2-contract compare still renders
- Vendor website display and fallback
- Contract detail: location and category rendering
"""

import json
import sqlite3
import pytest
import db as db_module
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    """Fresh DB with five test contracts for compare + vendor + detail tests."""
    db_path = str(tmp_path / "ci_test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()

    raw_with_state = json.dumps({
        "performance_state": "VA",
        "performance_city": "Arlington",
        "sam_naics": "5415",
    })
    raw_with_website = json.dumps({"vendor_website": "https://example-vendor.com"})

    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, "
            " priority, recompete_score, days_remaining, description, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CI001", "AWARD-CI001", "Acme IT Corp", "DOD", 1_000_000, "2025-12-31",
             "HIGH", 85, 180, "Information technology support services", raw_with_state),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, "
            " priority, recompete_score, days_remaining, description, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CI002", "AWARD-CI002", "Beta Cleaning LLC", "DHS", 500_000, "2026-06-30",
             "CRITICAL", 95, 30, "Janitorial and custodial services", "{}"),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, "
            " priority, recompete_score, days_remaining, description, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CI003", "AWARD-CI003", "Gamma Grounds LLC", "GSA", 250_000, "2026-09-01",
             "MEDIUM", 70, 90, "Landscaping and lawn maintenance", "{}"),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, "
            " priority, recompete_score, days_remaining, description, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CI004", "AWARD-CI004", "Delta Security Inc", "VA", 750_000, "2027-01-15",
             "HIGH", 80, 365, "Security guard services", "{}"),
        )
        # Contract for vendor_website test — vendor_website column populated
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, "
            " priority, recompete_score, days_remaining, vendor_website, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("CI005", "AWARD-CI005", "WebVendor Corp", "DOD", 2_000_000, "2026-03-01",
             "CRITICAL", 92, 10, "https://webvendor.example.com", raw_with_website),
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
    flask_app.app.secret_key = "ci-test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            rv = c.post("/register", data={
                "email": "ci_fixture@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        assert rv.status_code in (200, 302)
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


# ---------------------------------------------------------------------------
# infer_category tests
# ---------------------------------------------------------------------------

def test_infer_category_keyword_it():
    from db import infer_category
    assert infer_category(description="information technology support") == "IT"


def test_infer_category_keyword_cleaning():
    from db import infer_category
    assert infer_category(description="Janitorial and custodial services") == "Cleaning"


def test_infer_category_keyword_grounds():
    from db import infer_category
    assert infer_category(description="Landscaping and lawn maintenance") == "Grounds"


def test_infer_category_keyword_security():
    from db import infer_category
    assert infer_category(description="Security guard services for federal building") == "Security"


def test_infer_category_keyword_cybersecurity():
    from db import infer_category
    assert infer_category(description="Cybersecurity operations and monitoring") == "Cybersecurity"


def test_infer_category_keyword_facilities():
    from db import infer_category
    assert infer_category(description="HVAC and building maintenance services") == "Facilities"


def test_infer_category_naics_it():
    from db import infer_category
    assert infer_category(naics_code="541512") == "IT"


def test_infer_category_naics_construction():
    from db import infer_category
    assert infer_category(naics_code="238100") == "Construction"


def test_infer_category_naics_logistics():
    from db import infer_category
    assert infer_category(naics_code="484110") == "Logistics"


def test_infer_category_vendor_fallback():
    from db import infer_category
    assert infer_category(vendor="Acme Cyber Solutions") == "Cybersecurity"


def test_infer_category_other_when_no_match():
    from db import infer_category
    assert infer_category(description="General professional services") == "Other"


def test_infer_category_keyword_beats_naics():
    from db import infer_category
    # "janitorial" in description should win over NAICS IT code
    assert infer_category(description="janitorial services", naics_code="5415") == "Cleaning"


# ---------------------------------------------------------------------------
# extract_raw_field tests
# ---------------------------------------------------------------------------

def test_extract_raw_field_returns_value():
    from db import extract_raw_field
    row = {"raw_json": json.dumps({"performance_state": "VA"})}
    assert extract_raw_field(row, "performance_state") == "VA"


def test_extract_raw_field_missing_key_returns_default():
    from db import extract_raw_field
    row = {"raw_json": json.dumps({"other": "thing"})}
    assert extract_raw_field(row, "performance_state") is None


def test_extract_raw_field_no_raw_json():
    from db import extract_raw_field
    assert extract_raw_field({}, "performance_state") is None


def test_extract_raw_field_invalid_json():
    from db import extract_raw_field
    row = {"raw_json": "NOT JSON{{"}
    assert extract_raw_field(row, "field", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# Multi-contract compare tests
# ---------------------------------------------------------------------------

def test_compare_two_contracts_still_works(client):
    rv = client.get("/compare?a=CI001&b=CI002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme IT Corp" in body
    assert "Beta Cleaning LLC" in body


def test_compare_three_contracts(client):
    rv = client.get("/compare?a=CI001&b=CI002&c=CI003")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme IT Corp" in body
    assert "Beta Cleaning LLC" in body
    assert "Gamma Grounds LLC" in body
    # All three should appear in the table
    assert body.count("AWARD-CI00") >= 3


def test_compare_four_contracts(client):
    rv = client.get("/compare?a=CI001&b=CI002&c=CI003&d=CI004")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme IT Corp" in body
    assert "Beta Cleaning LLC" in body
    assert "Gamma Grounds LLC" in body
    assert "Delta Security Inc" in body


def test_compare_five_contracts(client):
    rv = client.get("/compare?a=CI001&b=CI002&c=CI003&d=CI004&e=CI005")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "WebVendor Corp" in body


def test_compare_partial_missing_shows_error(client):
    rv = client.get("/compare?a=CI001&b=NOTEXIST&c=CI003")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "NOTEXIST" in body
    assert "not found" in body
    # The two found contracts should still render
    assert "Acme IT Corp" in body
    assert "Gamma Grounds LLC" in body


def test_compare_no_params_shows_form(client):
    rv = client.get("/compare")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Compare Contracts" in body
    # Form should have at least two input slots
    assert body.count('name="a"') + body.count("name=a") >= 1
    assert body.count('name="b"') + body.count("name=b") >= 1


def test_compare_table_has_testid(client):
    rv = client.get("/compare?a=CI001&b=CI002")
    assert rv.status_code == 200
    assert b'data-testid="compare-table"' in rv.data


# ---------------------------------------------------------------------------
# Vendor website tests
# ---------------------------------------------------------------------------

def test_vendor_website_displays_when_set(client):
    rv = client.get("/vendor/WebVendor%20Corp")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "webvendor.example.com" in body
    assert 'data-testid="vendor-website-link"' in body


def test_vendor_website_absent_when_not_set(client):
    rv = client.get("/vendor/Acme%20IT%20Corp")
    assert rv.status_code == 200
    body = rv.data.decode()
    # Should not show a spurious website link for a vendor with no website
    assert 'data-testid="vendor-website-link"' not in body


def test_vendor_unknown_vendor_no_website_link(client):
    rv = client.get("/vendor/UnknownVendorXYZ")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert 'data-testid="vendor-website-link"' not in body


# ---------------------------------------------------------------------------
# Contract detail: location and category rendering
# ---------------------------------------------------------------------------

def test_contract_detail_shows_location_from_raw_json(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    body = rv.data.decode()
    # CI001 has performance_state=VA, performance_city=Arlington in raw_json
    assert "VA" in body
    assert "Arlington" in body


def test_contract_detail_location_badge_present(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    assert b'data-testid="location-badge"' in rv.data


def test_contract_detail_no_location_shows_fallback(client):
    rv = client.get("/contract/CI002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Not recorded" in body


def test_contract_detail_shows_category_badge(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    body = rv.data.decode()
    # CI001 description = "information technology support services" → IT
    assert "IT" in body
    assert 'data-testid="category-badge"' in body


def test_contract_detail_cleaning_category(client):
    rv = client.get("/contract/CI002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Cleaning" in body


def test_contract_detail_score_kpi_has_testid(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    assert b'data-testid="score-kpi"' in rv.data


def test_contract_detail_score_explainer_present(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    assert b'data-testid="score-explainer"' in rv.data


def test_contract_detail_score_explains_components(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Competition type" in body
    assert "Contract value" in body
    assert "Time remaining" in body


def test_contract_detail_shows_incumbent_link(client):
    rv = client.get("/contract/CI001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Incumbent" in body
    assert "Acme IT Corp" in body
