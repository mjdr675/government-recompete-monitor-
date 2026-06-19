"""Tests for db.py — save_snapshot() and FTS search consistency."""

import pytest
import db as db_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


def test_save_snapshot_fts_searchable_by_vendor(db):
    db_module.save_snapshot("2026-06-19", [
        {"internal_id": "FTS-001", "vendor": "Findable Corp", "agency": "DOD",
         "award_id": "AW-001", "value": 500_000, "recompete_score": 70, "priority": "HIGH"},
    ])
    result = db_module.get_contracts(q="Findable")
    assert result["total"] == 1
    assert result["contracts"][0]["vendor"] == "Findable Corp"


def test_save_snapshot_fts_searchable_by_agency(db):
    db_module.save_snapshot("2026-06-19", [
        {"internal_id": "FTS-002", "vendor": "Alpha LLC", "agency": "SearchableAgency",
         "award_id": "AW-002", "value": 250_000, "recompete_score": 60, "priority": "MEDIUM"},
    ])
    result = db_module.get_contracts(q="SearchableAgency")
    assert result["total"] == 1


def test_save_snapshot_fts_reflects_updated_vendor_name(db):
    """After an upsert updates an existing row, FTS must index the NEW vendor name."""
    db_module.save_snapshot("2026-06-19", [
        {"internal_id": "FTS-003", "vendor": "OldVendorName", "agency": "GSA",
         "award_id": "AW-003", "value": 100_000, "recompete_score": 50, "priority": "LOW"},
    ])
    db_module.save_snapshot("2026-06-20", [
        {"internal_id": "FTS-003", "vendor": "UpdatedVendorName", "agency": "GSA",
         "award_id": "AW-003", "value": 150_000, "recompete_score": 55, "priority": "LOW"},
    ])

    assert db_module.get_contracts(q="OldVendorName")["total"] == 0
    assert db_module.get_contracts(q="UpdatedVendorName")["total"] == 1


def test_save_snapshot_skips_rows_missing_internal_id(db):
    db_module.save_snapshot("2026-06-19", [
        {"vendor": "Ghost Corp", "agency": "DOD", "value": 1_000},
        {"internal_id": "VALID-001", "vendor": "Real Corp", "agency": "DOD",
         "value": 1_000, "recompete_score": 40, "priority": "LOW"},
    ])
    result = db_module.get_contracts(q="Real")
    assert result["total"] == 1


def test_save_snapshot_multiple_rows_all_searchable(db):
    rows = [
        {"internal_id": f"MULTI-{i}", "vendor": f"Vendor{i}", "agency": "NASA",
         "award_id": f"AW-{i}", "value": i * 1_000, "recompete_score": 50, "priority": "LOW"}
        for i in range(5)
    ]
    db_module.save_snapshot("2026-06-19", rows)
    for i in range(5):
        assert db_module.get_contracts(q=f"Vendor{i}")["total"] == 1
