"""
Tests for the Flask app routes — uses a temporary SQLite database so the real
contracts.db is never touched.
"""

import logging
import sqlite3
import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    """Spin up a fresh DB with two test contracts and patch the module path."""
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID001", "AWARD-001", "Acme Corp", "DOD", 1_000_000, "2025-12-31", "HIGH", 85),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID002", "AWARD-002", "Beta LLC", "DHS", 2_000_000, "2026-06-30", "CRITICAL", 95),
        )
        con.commit()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        # Register and auto-login a fixture user so route tests bypass the auth gate
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ---------------------------------------------------------------------------
# /compare tests
# ---------------------------------------------------------------------------

def test_compare_no_params_shows_form(client):
    rv = client.get("/compare")
    assert rv.status_code == 200
    assert b"Compare Contracts" in rv.data
    assert b'name="a"' in rv.data
    assert b'name="b"' in rv.data


def test_compare_both_found(client):
    rv = client.get("/compare?a=ID001&b=ID002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme Corp" in body
    assert "Beta LLC" in body
    assert "DOD" in body
    assert "DHS" in body
    assert "1,000,000" in body
    assert "2,000,000" in body
    assert "2025-12-31" in body
    assert "2026-06-30" in body
    assert "HIGH" in body
    assert "CRITICAL" in body
    assert "85" in body
    assert "95" in body


def test_compare_first_missing(client):
    rv = client.get("/compare?a=MISSING&b=ID002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "MISSING" in body
    assert "not found" in body


def test_compare_second_missing(client):
    rv = client.get("/compare?a=ID001&b=NOPE")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "NOPE" in body
    assert "not found" in body


def test_compare_same_contract(client):
    rv = client.get("/compare?a=ID001&b=ID001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme Corp" in body


# ---------------------------------------------------------------------------
# /contracts days-filter tests
# ---------------------------------------------------------------------------

def test_contracts_negative_days_returns_400(client):
    rv = client.get("/contracts?days=-1")
    assert rv.status_code == 400


def test_contracts_zero_days_returns_200(client):
    rv = client.get("/contracts?days=0")
    assert rv.status_code == 200


def test_contracts_positive_days_returns_200(client):
    rv = client.get("/contracts?days=90")
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# Railway ephemeral DB warning tests
# ---------------------------------------------------------------------------

def test_railway_warning_emitted_without_volume(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_VOLUME_NAME", raising=False)
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" in caplog.text


def test_railway_warning_suppressed_with_volume(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("RAILWAY_VOLUME_NAME", "contracts-volume")
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" not in caplog.text


def test_railway_warning_suppressed_outside_railway(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" not in caplog.text


# ---------------------------------------------------------------------------
# /vendor/<name> baseline tests
# ---------------------------------------------------------------------------

def test_vendor_profile_returns_200(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert rv.status_code == 200


def test_vendor_profile_shows_vendor_name(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Acme Corp" in rv.data


def test_vendor_profile_shows_pipeline_value(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"1,000,000" in rv.data


def test_vendor_profile_unknown_vendor_returns_200(client):
    rv = client.get("/vendor/Unknown%20Vendor")
    assert rv.status_code == 200


def test_vendor_profile_has_responsive_table_wrapper(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"overflow-x:auto" in rv.data


def test_vendor_summary_cards_show_active_expired(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Active" in body
    assert "Expired" in body
    assert "Top Score" in body


def test_vendor_active_contracts_section_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Active Contracts" in rv.data


def test_vendor_active_contracts_shows_active_contract(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-ACT", "AWARD-ACT", "Acme Corp", "DOD", 750_000, "2027-06-01", "HIGH", 80, 180),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"AWARD-ACT" in rv.data


def test_vendor_upcoming_shows_competition_column(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Competition" in rv.data


def test_vendor_upcoming_urgency_styling_for_expired(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-EXP", "AWARD-EXP", "Acme Corp", "DOD", 100_000, "2024-01-01", "LOW", 10, -5),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"#b00020" in rv.data


def test_vendor_agency_breakdown_shows_value_and_share(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Pipeline Value" in body or "1,000,000" in body
    assert "Share" in body
    assert "Top Score" in body


def test_vendor_summary_active_count_with_days_remaining(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID003", "AWARD-003", "Acme Corp", "DOD", 500_000, "2027-01-01", "HIGH", 70, 90),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"1" in rv.data  # active_contracts = 1
