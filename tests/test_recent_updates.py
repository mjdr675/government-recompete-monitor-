"""
Tests for the dashboard Recent Updates feed (Auto Contract Updates, Commit 2).

Covers:
- format_contract_update pure formatting for each change kind/field
- get_recent_updates_for_user scoping (watchlist ∪ pipeline only)
- dashboard route renders the Recent Updates card with a tracked-contract change
"""

import json
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import text

import db as db_module
from contract_summary import format_contract_update


# ---------------------------------------------------------------------------
# format_contract_update — pure formatting
# ---------------------------------------------------------------------------

def test_format_value_increase():
    out = format_contract_update({
        "field_name": "value", "change_kind": "INCREASE",
        "old_value": "1000000", "new_value": "1500000",
        "award_id": "AW-1", "internal_id": "C1", "run_date": "2026-06-22",
    })
    assert out["headline"] == "Value increased"
    assert out["old_value"] == "$1,000,000"
    assert out["new_value"] == "$1,500,000"
    assert out["contract"] == "AW-1"


def test_format_value_decrease():
    out = format_contract_update({
        "field_name": "value", "change_kind": "DECREASE",
        "old_value": "2000000", "new_value": "900000",
        "internal_id": "C1",
    })
    assert out["headline"] == "Value decreased"
    assert out["contract"] == "C1"  # falls back to internal_id when no award_id


def test_format_recompete_date_changed():
    out = format_contract_update({
        "field_name": "end_date", "change_kind": "MODIFIED",
        "old_value": "2026-12-31", "new_value": "2026-10-01",
    })
    assert out["headline"] == "Recompete date changed"
    assert out["old_value"] == "2026-12-31"


def test_format_priority_changed():
    out = format_contract_update({
        "field_name": "priority", "change_kind": "MODIFIED",
        "old_value": "MEDIUM", "new_value": "CRITICAL",
    })
    assert out["headline"] == "Priority changed"


def test_format_vendor_changed():
    out = format_contract_update({
        "field_name": "vendor", "change_kind": "MODIFIED",
        "old_value": "Acme", "new_value": "Beta",
    })
    assert out["headline"] == "Vendor changed"


def test_format_competition_type_changed():
    out = format_contract_update({
        "field_name": "competition_type", "change_kind": "MODIFIED",
        "old_value": "Full and Open", "new_value": "Sole Source",
    })
    assert out["headline"] == "Competition type changed"


def test_format_score_increase():
    out = format_contract_update({
        "field_name": "recompete_score", "change_kind": "INCREASE",
        "old_value": "70", "new_value": "85",
    })
    assert out["headline"] == "Recompete score increased"


def test_format_blank_value_renders_dash():
    out = format_contract_update({
        "field_name": "vendor", "change_kind": "SET",
        "old_value": None, "new_value": "New Vendor",
    })
    assert out["headline"] == "Vendor set"
    assert out["old_value"] == "—"


# ---------------------------------------------------------------------------
# get_recent_updates_for_user — scoping
# ---------------------------------------------------------------------------

@pytest.fixture()
def fresh_db(tmp_path):
    db_path = str(tmp_path / "feed_test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


def _add_contract(internal_id, award_id="AW", vendor="Acme"):
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts (internal_id, award_id, vendor) VALUES (?, ?, ?)",
            (internal_id, award_id, vendor),
        )
        con.commit()


def _add_field_change(run_date, internal_id, field, old, new, kind):
    db_module.insert_field_changes(run_date, [{
        "internal_id": internal_id, "field_name": field,
        "old_value": old, "new_value": new, "change_kind": kind,
    }])


def _create_user(email="feed@example.com"):
    from sqlalchemy import text
    with db_module.get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO users (email, password_hash, created_at, is_active)"
            " VALUES (:e, 'x', '2026-01-01', 1)"
        ), {"e": email})
        row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).fetchone()
    return row[0]


def test_anon_user_gets_empty(fresh_db):
    assert db_module.get_recent_updates_for_user(None) == []


def test_user_with_no_tracked_contracts_empty(fresh_db):
    uid = _create_user()
    _add_contract("C1")
    _add_field_change("2026-06-22", "C1", "value", "1000000", "1500000", "INCREASE")
    # User tracks nothing → no updates even though a change exists
    assert db_module.get_recent_updates_for_user(uid) == []


def test_watchlist_contract_change_surfaced(fresh_db):
    uid = _create_user()
    _add_contract("C1", award_id="AW-1")
    _add_field_change("2026-06-22", "C1", "value", "1000000", "1500000", "INCREASE")
    with db_module.get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO user_watchlist (user_id, internal_id, added_at)"
            " VALUES (:u, 'C1', '2026-06-01')"
        ), {"u": uid})
    updates = db_module.get_recent_updates_for_user(uid)
    assert len(updates) == 1
    assert updates[0]["internal_id"] == "C1"
    assert updates[0]["field_name"] == "value"


def test_pipeline_contract_change_surfaced(fresh_db):
    uid = _create_user()
    _add_contract("C2", award_id="AW-2")
    _add_field_change("2026-06-22", "C2", "priority", "HIGH", "CRITICAL", "MODIFIED")
    db_module.add_opportunity(uid, "C2", stage="new")
    updates = db_module.get_recent_updates_for_user(uid)
    assert len(updates) == 1
    assert updates[0]["internal_id"] == "C2"


def test_untracked_contract_change_not_surfaced(fresh_db):
    uid = _create_user()
    _add_contract("C1")
    _add_contract("C9")  # not tracked
    _add_field_change("2026-06-22", "C9", "value", "1", "2", "INCREASE")
    with db_module.get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO user_watchlist (user_id, internal_id, added_at)"
            " VALUES (:u, 'C1', '2026-06-01')"
        ), {"u": uid})
    # The change is on C9 (untracked); C1 has no changes → empty feed
    assert db_module.get_recent_updates_for_user(uid) == []


# ---------------------------------------------------------------------------
# Dashboard route rendering
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(fresh_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "feed-test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            rv = c.post("/register", data={
                "email": "dashfeed@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        assert rv.status_code in (200, 302)
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


def test_dashboard_shows_recent_updates_card(client):
    rv = client.get("/dashboard")
    assert rv.status_code == 200
    assert b'data-testid="recent-updates"' in rv.data
    assert b"Recent Updates" in rv.data


def test_dashboard_recent_updates_shows_tracked_change(client):
    # Find the registered user id
    uid = db_module.get_engine().connect().execute(
        text("SELECT id FROM users WHERE email = 'dashfeed@example.com'")
    ).fetchone()[0]
    _add_contract("CX", award_id="AW-CX")
    _add_field_change("2026-06-22", "CX", "value", "1000000", "1500000", "INCREASE")
    with db_module.get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO user_watchlist (user_id, internal_id, added_at)"
            " VALUES (:u, 'CX', '2026-06-01')"
        ), {"u": uid})

    rv = client.get("/dashboard")
    body = rv.data.decode()
    assert "Value increased" in body
    assert "$1,000,000" in body
    assert "$1,500,000" in body
    assert "AW-CX" in body


def test_dashboard_empty_updates_message(client):
    rv = client.get("/dashboard")
    body = rv.data.decode()
    assert "No recent updates on your watchlist or pipeline contracts yet." in body
