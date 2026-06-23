"""Tests for Auto Updates Commit 1 — field-level change detection.

Covers contract_field_changes table + change_detector field diffing:
- table creation
- a tracked-field change is recorded with old/new/field/contract/snapshot refs
- only the 7 whitelisted fields are tracked (untracked fields ignored)
- multiple simultaneous field changes are each recorded
- no change -> no rows
- idempotent re-run does not duplicate
"""
import sqlite3

import pytest

import db as db_module
from db import save_snapshot, get_field_changes, init_field_changes_table as init_contract_field_changes_table
from change_detector import detect_changes


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


def _base_row(**over):
    row = {
        "internal_id": "C1", "award_id": "A1", "vendor": "Acme Corp",
        "agency": "GSA", "value": 100000, "end_date": "2026-12-31",
        "days_remaining": 90, "competition_type": "FULL AND OPEN",
        "recompete_score": 50, "priority": "MEDIUM",
    }
    row.update(over)
    return row


def _detect_between(yesterday_rows, today_rows, *, yd="2026-06-18", td="2026-06-19"):
    """Write two snapshots and run detection for the later date."""
    save_snapshot(yd, yesterday_rows)
    save_snapshot(td, today_rows)
    detect_changes(td)
    return td


# ---------------------------------------------------------------------------

def test_table_created(db):
    init_contract_field_changes_table()
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='contract_field_changes'"
    ).fetchone()
    con.close()
    assert row is not None


def test_value_change_recorded(db):
    td = _detect_between(
        [_base_row(value=100000)],
        [_base_row(value=150000)],
    )
    changes = get_field_changes(td)
    value_changes = [c for c in changes if c["field_name"] == "value"]
    assert len(value_changes) == 1
    c = value_changes[0]
    assert c["internal_id"] == "C1"
    # save_snapshot stores value as REAL, so str() form is float-like.
    assert c["old_value"] == "100000.0"
    assert c["new_value"] == "150000.0"


def test_all_tracked_fields_detected(db):
    td = _detect_between(
        [_base_row(value=100000, end_date="2026-12-31", days_remaining=90,
                   vendor="Acme Corp", competition_type="FULL AND OPEN",
                   recompete_score=50, priority="MEDIUM")],
        [_base_row(value=200000, end_date="2027-01-31", days_remaining=120,
                   vendor="Beta LLC", competition_type="SET ASIDE",
                   recompete_score=80, priority="HIGH")],
    )
    changed_fields = {c["field_name"] for c in get_field_changes(td)}
    assert changed_fields == {
        "value", "end_date", "days_remaining", "vendor",
        "competition_type", "recompete_score", "priority",
    }


def test_untracked_field_ignored(db):
    # Only agency changes; agency is not a tracked field.
    td = _detect_between(
        [_base_row(agency="GSA")],
        [_base_row(agency="Department of Energy")],
    )
    assert get_field_changes(td) == []


def test_no_change_records_nothing(db):
    td = _detect_between([_base_row()], [_base_row()])
    assert get_field_changes(td) == []


def test_multiple_contracts_each_recorded(db):
    yesterday = [
        _base_row(internal_id="C1", value=100000),
        _base_row(internal_id="C2", value=500000),
    ]
    today = [
        _base_row(internal_id="C1", value=110000),
        _base_row(internal_id="C2", value=500000),  # unchanged
    ]
    td = _detect_between(yesterday, today)
    changes = get_field_changes(td)
    assert {c["internal_id"] for c in changes} == {"C1"}


def test_idempotent_rerun_does_not_duplicate(db):
    save_snapshot("2026-06-18", [_base_row(value=100000)])
    save_snapshot("2026-06-19", [_base_row(value=150000)])
    detect_changes("2026-06-19")
    first = get_field_changes("2026-06-19")
    # Re-run detection for the same date.
    detect_changes("2026-06-19")
    second = get_field_changes("2026-06-19")
    assert len(first) == len(second) == 1


def test_priority_change_recorded_as_field_too(db):
    # Priority lives in both the semantic `changes` table and the field table.
    td = _detect_between(
        [_base_row(priority="MEDIUM")],
        [_base_row(priority="HIGH")],
    )
    priority_changes = [c for c in get_field_changes(td) if c["field_name"] == "priority"]
    assert len(priority_changes) == 1
    assert priority_changes[0]["old_value"] == "MEDIUM"
    assert priority_changes[0]["new_value"] == "HIGH"
