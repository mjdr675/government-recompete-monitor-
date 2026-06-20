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


# ---------------------------------------------------------------------------
# user_watchlist schema
# ---------------------------------------------------------------------------

def test_watchlist_unique_constraint_raises_on_duplicate(db):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('u@x.com', 'h', '2026-01-01')")
    uid = con.execute("SELECT id FROM users WHERE email='u@x.com'").fetchone()[0]
    con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'C1', '2026-01-01')", (uid,))
    con.commit()
    import pytest as _pytest
    with _pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'C1', '2026-01-01')", (uid,))
        con.commit()
    con.close()


def test_watchlist_allows_different_contracts(db):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('u2@x.com', 'h', '2026-01-01')")
    uid = con.execute("SELECT id FROM users WHERE email='u2@x.com'").fetchone()[0]
    con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'C1', '2026-01-01')", (uid,))
    con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'C2', '2026-01-01')", (uid,))
    con.commit()
    count = con.execute("SELECT COUNT(*) FROM user_watchlist WHERE user_id=?", (uid,)).fetchone()[0]
    assert count == 2
    con.close()


# ---------------------------------------------------------------------------
# user_saved_searches table (Task 084)
# ---------------------------------------------------------------------------

def test_user_saved_searches_table_exists(db):
    import sqlite3
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    con.close()
    assert "user_saved_searches" in tables


def test_user_saved_searches_allows_multiple_per_user(db):
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("INSERT INTO users (email, password_hash, created_at) VALUES ('ss@x.com', 'h', '2026-01-01')")
    uid = con.execute("SELECT id FROM users WHERE email='ss@x.com'").fetchone()[0]
    con.execute("INSERT INTO user_saved_searches (user_id, name, query_params_json, created_at) VALUES (?, 'Search A', '{}', '2026-01-01')", (uid,))
    con.execute("INSERT INTO user_saved_searches (user_id, name, query_params_json, created_at) VALUES (?, 'Search B', '{}', '2026-01-01')", (uid,))
    con.commit()
    count = con.execute("SELECT COUNT(*) FROM user_saved_searches WHERE user_id=?", (uid,)).fetchone()[0]
    con.close()
    assert count == 2


# ---------------------------------------------------------------------------
# contract_notes table (Task 088)
# ---------------------------------------------------------------------------

def test_contract_notes_table_exists(db):
    import sqlite3
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    con.close()
    assert "contract_notes" in tables
