"""
Tests for the Auto Contract Updates field-level change detector (Commit 1).

Covers:
- diff_snapshot_fields pure logic (numeric + text, all change kinds)
- days_remaining clock-drift suppression
- detect_field_changes end-to-end over contract_snapshots
- idempotency (re-run produces no duplicates)
- preservation of existing change_detector / changes table behavior
"""

import pytest
import db as db_module
from update_detector import diff_snapshot_fields, detect_field_changes, TRACKED_FIELDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fresh_db(tmp_path):
    db_path = str(tmp_path / "upd_test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


def _insert_snapshot(run_date, internal_id, **fields):
    """Insert a contract_snapshots row with the given field overrides."""
    db_module.init_snapshots_table()
    cols = {
        "run_date": run_date,
        "internal_id": internal_id,
        "award_id": fields.get("award_id", f"AWARD-{internal_id}"),
        "vendor": fields.get("vendor"),
        "agency": fields.get("agency"),
        "sub_agency": fields.get("sub_agency"),
        "value": fields.get("value"),
        "start_date": fields.get("start_date"),
        "end_date": fields.get("end_date"),
        "days_remaining": fields.get("days_remaining"),
        "competition_type": fields.get("competition_type"),
        "solicitation_id": fields.get("solicitation_id"),
        "recompete_score": fields.get("recompete_score"),
        "priority": fields.get("priority"),
        "raw_json": fields.get("raw_json", "{}"),
    }
    from sqlalchemy import text
    with db_module.get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO contract_snapshots
                (run_date, internal_id, award_id, vendor, agency, sub_agency,
                 value, start_date, end_date, days_remaining, competition_type,
                 solicitation_id, recompete_score, priority, raw_json)
            VALUES (:run_date, :internal_id, :award_id, :vendor, :agency, :sub_agency,
                    :value, :start_date, :end_date, :days_remaining, :competition_type,
                    :solicitation_id, :recompete_score, :priority, :raw_json)
        """), cols)


# ---------------------------------------------------------------------------
# Pure diff_snapshot_fields tests
# ---------------------------------------------------------------------------

def test_diff_no_change_returns_empty():
    row = {"value": 100, "vendor": "Acme", "priority": "HIGH"}
    assert diff_snapshot_fields(row, dict(row)) == []


def test_diff_value_increase():
    prev = {"value": 1_000_000}
    curr = {"value": 1_500_000}
    changes = diff_snapshot_fields(prev, curr)
    assert len(changes) == 1
    c = changes[0]
    assert c["field_name"] == "value"
    assert c["change_kind"] == "INCREASE"
    assert c["old_value"] == "1000000"
    assert c["new_value"] == "1500000"


def test_diff_value_decrease():
    changes = diff_snapshot_fields({"value": 2_000_000}, {"value": 900_000})
    assert changes[0]["change_kind"] == "DECREASE"


def test_diff_value_cent_noise_suppressed():
    # 100.001 vs 100.004 round to the same cent → no change
    assert diff_snapshot_fields({"value": 100.001}, {"value": 100.004}) == []


def test_diff_recompete_score_change():
    changes = diff_snapshot_fields({"recompete_score": 70}, {"recompete_score": 85})
    assert len(changes) == 1
    assert changes[0]["field_name"] == "recompete_score"
    assert changes[0]["change_kind"] == "INCREASE"


def test_diff_vendor_modified():
    changes = diff_snapshot_fields({"vendor": "Acme Corp"}, {"vendor": "Beta LLC"})
    assert len(changes) == 1
    assert changes[0]["field_name"] == "vendor"
    assert changes[0]["change_kind"] == "MODIFIED"
    assert changes[0]["old_value"] == "Acme Corp"
    assert changes[0]["new_value"] == "Beta LLC"


def test_diff_vendor_set_from_blank():
    changes = diff_snapshot_fields({"vendor": None}, {"vendor": "New Vendor"})
    assert changes[0]["change_kind"] == "SET"


def test_diff_vendor_cleared():
    changes = diff_snapshot_fields({"vendor": "Acme"}, {"vendor": ""})
    assert changes[0]["change_kind"] == "CLEARED"


def test_diff_priority_change():
    changes = diff_snapshot_fields({"priority": "MEDIUM"}, {"priority": "CRITICAL"})
    assert changes[0]["field_name"] == "priority"
    assert changes[0]["change_kind"] == "MODIFIED"


def test_diff_competition_type_change():
    changes = diff_snapshot_fields(
        {"competition_type": "Full and Open"},
        {"competition_type": "Sole Source"},
    )
    assert changes[0]["field_name"] == "competition_type"


def test_diff_end_date_change_with_days_remaining():
    # When end_date moves, days_remaining is also reported (both meaningful).
    prev = {"end_date": "2026-12-31", "days_remaining": 200}
    curr = {"end_date": "2026-10-01", "days_remaining": 100}
    fields = {c["field_name"] for c in diff_snapshot_fields(prev, curr)}
    assert "end_date" in fields
    assert "days_remaining" in fields


def test_diff_days_remaining_drift_suppressed():
    # end_date unchanged, only days_remaining decremented → suppressed as clock drift
    prev = {"end_date": "2026-12-31", "days_remaining": 200}
    curr = {"end_date": "2026-12-31", "days_remaining": 199}
    assert diff_snapshot_fields(prev, curr) == []


def test_diff_multiple_fields_at_once():
    prev = {"value": 1_000_000, "priority": "HIGH", "vendor": "Acme"}
    curr = {"value": 1_200_000, "priority": "CRITICAL", "vendor": "Acme"}
    fields = {c["field_name"] for c in diff_snapshot_fields(prev, curr)}
    assert fields == {"value", "priority"}


def test_tracked_fields_complete():
    # The plan-specified field set must be exactly what we track.
    assert set(TRACKED_FIELDS) == {
        "value", "end_date", "days_remaining", "vendor",
        "competition_type", "recompete_score", "priority",
    }


# ---------------------------------------------------------------------------
# detect_field_changes end-to-end tests
# ---------------------------------------------------------------------------

def test_detect_no_snapshots_returns_zero(fresh_db):
    assert detect_field_changes("2026-06-23") == 0


def test_detect_single_snapshot_returns_zero(fresh_db):
    _insert_snapshot("2026-06-22", "C1", value=1_000_000, priority="HIGH")
    assert detect_field_changes("2026-06-22") == 0


def test_detect_records_value_change(fresh_db):
    _insert_snapshot("2026-06-21", "C1", value=1_000_000, end_date="2026-12-31",
                     days_remaining=180, priority="HIGH", vendor="Acme")
    _insert_snapshot("2026-06-22", "C1", value=1_500_000, end_date="2026-12-31",
                     days_remaining=179, priority="HIGH", vendor="Acme")
    n = detect_field_changes("2026-06-22")
    assert n == 1
    rows = db_module.get_field_changes_for_contracts(["C1"])
    assert len(rows) == 1
    assert rows[0]["field_name"] == "value"
    assert rows[0]["change_kind"] == "INCREASE"
    assert rows[0]["new_value"] == "1500000"


def test_detect_records_multiple_contracts(fresh_db):
    _insert_snapshot("2026-06-21", "C1", value=1_000_000, priority="HIGH")
    _insert_snapshot("2026-06-22", "C1", value=2_000_000, priority="CRITICAL")
    _insert_snapshot("2026-06-21", "C2", vendor="Acme")
    _insert_snapshot("2026-06-22", "C2", vendor="Beta")
    n = detect_field_changes("2026-06-22")
    # C1: value + priority (2), C2: vendor (1)
    assert n == 3


def test_detect_idempotent_rerun(fresh_db):
    _insert_snapshot("2026-06-21", "C1", value=1_000_000)
    _insert_snapshot("2026-06-22", "C1", value=1_500_000)
    first = detect_field_changes("2026-06-22")
    second = detect_field_changes("2026-06-22")
    assert first == second == 1
    rows = db_module.get_field_changes_for_contracts(["C1"])
    assert len(rows) == 1  # no duplicate


def test_detect_new_contract_not_diffed(fresh_db):
    # A contract only present in the latest snapshot has nothing to diff against.
    _insert_snapshot("2026-06-21", "C1", value=1_000_000)
    _insert_snapshot("2026-06-22", "C1", value=1_000_000)
    _insert_snapshot("2026-06-22", "C2", value=500_000)  # new, no prior
    n = detect_field_changes("2026-06-22")
    assert n == 0


def test_detect_days_remaining_drift_not_recorded(fresh_db):
    _insert_snapshot("2026-06-21", "C1", end_date="2026-12-31", days_remaining=180,
                     value=1_000_000)
    _insert_snapshot("2026-06-22", "C1", end_date="2026-12-31", days_remaining=179,
                     value=1_000_000)
    assert detect_field_changes("2026-06-22") == 0


# ---------------------------------------------------------------------------
# Preservation of existing change_detector / changes table behavior
# ---------------------------------------------------------------------------

def test_field_changes_table_is_separate_from_changes(fresh_db):
    # The two tables coexist and the field detector does not touch `changes`.
    from change_detector import detect_changes
    _insert_snapshot("2026-06-21", "C1", priority="HIGH", value=1_000_000)
    _insert_snapshot("2026-06-22", "C1", priority="CRITICAL", value=1_500_000)
    detect_changes("2026-06-22")        # writes to `changes`
    detect_field_changes("2026-06-22")  # writes to `contract_field_changes`

    summary = db_module.change_summary("2026-06-22")
    # change_detector still records the priority UPGRADE in the old table
    assert summary.get("UPGRADE", 0) == 1
    # and the new table has the value + priority field changes
    rows = db_module.get_field_changes_for_contracts(["C1"])
    field_names = {r["field_name"] for r in rows}
    assert "value" in field_names
    assert "priority" in field_names


def test_get_field_changes_empty_ids_returns_empty(fresh_db):
    assert db_module.get_field_changes_for_contracts([]) == []
