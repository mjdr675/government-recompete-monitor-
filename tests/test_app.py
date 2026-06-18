"""
Tests for the Flask app routes — uses a temporary SQLite database so the real
contracts.db is never touched.
"""

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
    with flask_app.app.test_client() as c:
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
