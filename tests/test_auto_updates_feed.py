"""Tests for Auto Updates Commit 2 — dashboard Recent Updates feed.

The feed surfaces contract_field_changes (Commit 1) but only for contracts in
the user's watchlist or pipeline. No notifications/email/AI/settings involved.
"""
import sqlite3
from datetime import datetime

import pytest

import db as db_module
import users as users_module
from db import insert_field_changes
from analytics import recent_updates_for_user


@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.init_field_changes_table()
    users_module.create_user("feed@example.com", "password123")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email='feed@example.com'").fetchone()[0]
    con.close()
    return uid


def _add_contract(db_path, internal_id, award_id="AW", vendor="Acme", agency="GSA"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO contracts (internal_id, award_id, vendor, agency) VALUES (?,?,?,?)",
        (internal_id, award_id, vendor, agency),
    )
    con.commit()
    con.close()


def _watch(db_path, uid, internal_id):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?,?,?)",
        (uid, internal_id, datetime.now().isoformat()),
    )
    con.commit()
    con.close()


def _add_pipeline(db_path, uid, internal_id, stage="researching"):
    con = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    con.execute(
        "INSERT INTO opportunities (user_id, internal_id, stage, created_by_user_id, "
        "last_updated_by_user_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (uid, internal_id, stage, uid, uid, now, now),
    )
    con.commit()
    con.close()


@pytest.fixture()
def authed_client(pdb):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "feed@example.com", "password": "password123"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


# ---------------------------------------------------------------------------
# recent_updates_for_user
# ---------------------------------------------------------------------------

def test_returns_empty_when_no_user(pdb):
    assert recent_updates_for_user(None) == []


def _fc(run_date, internal_id, field, old, new, kind="MODIFIED"):
    insert_field_changes(run_date, [{"internal_id": internal_id, "field_name": field,
                                      "old_value": old, "new_value": new, "change_kind": kind}])


def test_returns_empty_when_nothing_tracked(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1")
    _fc("2026-06-19", "C1", "value", "100000.0", "150000.0")
    # C1 not watched/in pipeline → not surfaced.
    assert recent_updates_for_user(uid) == []


def test_returns_update_for_watchlisted_contract(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1", award_id="AW-1")
    _watch(pdb, uid, "C1")
    _fc("2026-06-19", "C1", "value", "100000.0", "150000.0")
    result = recent_updates_for_user(uid)
    assert len(result) == 1
    assert result[0]["internal_id"] == "C1"
    assert result[0]["field_name"] == "value"
    assert result[0]["old_value"] == "100000.0"
    assert result[0]["new_value"] == "150000.0"
    assert result[0]["award_id"] == "AW-1"


def test_includes_pipeline_contract(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "P1")
    _add_pipeline(pdb, uid, "P1")
    _fc("2026-06-19", "P1", "priority", "MEDIUM", "HIGH")
    result = recent_updates_for_user(uid)
    assert [r["internal_id"] for r in result] == ["P1"]


def test_excludes_untracked_contract(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1")
    _add_contract(pdb, "C2")
    _watch(pdb, uid, "C1")
    _fc("2026-06-19", "C1", "value", "1", "2")
    _fc("2026-06-19", "C2", "value", "3", "4")
    ids = {r["internal_id"] for r in recent_updates_for_user(uid)}
    assert ids == {"C1"}


def test_ordering_most_recent_first(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1")
    _watch(pdb, uid, "C1")
    # Inserted oldest-first; feed should return newest-first (run_date desc).
    _fc("2026-06-18", "C1", "value", "1", "2")
    _fc("2026-06-19", "C1", "priority", "LOW", "HIGH")
    result = recent_updates_for_user(uid)
    assert result[0]["field_name"] == "priority"
    assert result[-1]["field_name"] == "value"


def test_respects_limit(pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1")
    _watch(pdb, uid, "C1")
    # Different run_dates to avoid UNIQUE(run_date, internal_id, field_name) conflicts.
    for i in range(15):
        _fc(f"2026-06-{i + 1:02d}", "C1", "value", str(i), str(i + 1))
    assert len(recent_updates_for_user(uid, limit=5)) == 5


# ---------------------------------------------------------------------------
# Dashboard rendering
# ---------------------------------------------------------------------------

def test_dashboard_renders_recent_updates(authed_client, pdb):
    uid = _uid(pdb)
    _add_contract(pdb, "C1", award_id="AW-1")
    _watch(pdb, uid, "C1")
    _fc("2026-06-19", "C1", "value", "100000", "150000", kind="INCREASE")
    body = authed_client.get("/dashboard").get_data(as_text=True)
    assert "Recent Updates" in body
    assert "AW-1" in body
    assert "$150,000" in body


def test_dashboard_no_section_when_no_updates(authed_client, pdb):
    # Section always shows for logged-in users; empty state message appears when no changes.
    uid = _uid(pdb)
    _add_contract(pdb, "C1")
    _watch(pdb, uid, "C1")
    body = authed_client.get("/dashboard").get_data(as_text=True)
    assert "Recent Updates" in body
    assert "No recent updates on your watchlist or pipeline contracts yet." in body
