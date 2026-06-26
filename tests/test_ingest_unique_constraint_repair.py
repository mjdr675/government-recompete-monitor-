"""Focused tests for ingest-persistence UNIQUE-constraint schema drift.

Legacy SQLite tables created before the UNIQUE(...) table constraints existed
lack them, so ON CONFLICT(...) targets fail with
"ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint".

db.init_field_changes_table() / db.init_snapshots_table() must repair such
tables idempotently: dedupe any conflicting rows, then create the unique index
that backs the ON CONFLICT target.
"""

import pytest
from sqlalchemy import text

import db as db_module


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    yield db_path
    db_module._cached_engine.cache_clear()


def _legacy_field_changes(engine):
    """contract_field_changes without the UNIQUE(run_date, internal_id, field_name)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE contract_field_changes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date    TEXT NOT NULL,
                internal_id TEXT NOT NULL,
                field_name  TEXT NOT NULL,
                old_value   TEXT,
                new_value   TEXT,
                change_kind TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _legacy_snapshots(engine):
    """contract_snapshots without the UNIQUE(run_date, internal_id)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE contract_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                internal_id TEXT NOT NULL,
                award_id TEXT, vendor TEXT, agency TEXT, sub_agency TEXT,
                value REAL, start_date TEXT, end_date TEXT, days_remaining INTEGER,
                competition_type TEXT, solicitation_id TEXT, recompete_score INTEGER,
                priority TEXT, raw_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _has_uq(engine, table, cols):
    with engine.connect() as conn:
        return db_module._has_unique_index(conn, table, cols)


# ---------------------------------------------------------------------------
# contract_field_changes
# ---------------------------------------------------------------------------

class TestFieldChangesUniqueRepair:
    KEY = ("run_date", "internal_id", "field_name")

    def test_legacy_table_gains_unique_index(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_field_changes(engine)
        assert not _has_uq(engine, "contract_field_changes", self.KEY)
        db_module.init_field_changes_table()
        assert _has_uq(engine, "contract_field_changes", self.KEY)

    def test_insert_on_conflict_works_after_repair(self, sqlite_db):
        """Regression: insert_field_changes' ON CONFLICT must resolve on a
        legacy table (was: 'does not match any PRIMARY KEY or UNIQUE')."""
        engine = db_module.get_engine()
        _legacy_field_changes(engine)
        rec = {"internal_id": "C1", "field_name": "value",
               "old_value": "1", "new_value": "2", "change_kind": "MODIFIED"}
        db_module.insert_field_changes("2026-06-26", [rec])
        db_module.insert_field_changes("2026-06-26", [rec])  # DO NOTHING, no error
        with engine.connect() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM contract_field_changes WHERE internal_id='C1'"
            )).scalar()
        assert n == 1

    def test_dedupes_before_creating_unique_index(self, sqlite_db):
        """Duplicate legacy rows must not block unique-index creation."""
        engine = db_module.get_engine()
        _legacy_field_changes(engine)
        with engine.begin() as conn:
            for _ in range(3):
                conn.execute(text(
                    "INSERT INTO contract_field_changes "
                    "(run_date, internal_id, field_name, change_kind) "
                    "VALUES ('2026-06-26', 'D1', 'value', 'MODIFIED')"
                ))
        db_module.init_field_changes_table()  # must dedupe then index, no error
        assert _has_uq(engine, "contract_field_changes", self.KEY)
        with engine.connect() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM contract_field_changes WHERE internal_id='D1'"
            )).scalar()
        assert n == 1

    def test_repair_idempotent(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_field_changes(engine)
        db_module.init_field_changes_table()
        db_module.init_field_changes_table()  # no error, no duplicate index
        with engine.connect() as conn:
            uq = [r for r in conn.execute(text("PRAGMA index_list(contract_field_changes)")) if r[2]]
        # exactly one unique index covering the key
        covering = 0
        with engine.connect() as conn:
            for idx in uq:
                cols = {r[2] for r in conn.execute(text(f"PRAGMA index_info({idx[1]})"))}
                if cols == set(self.KEY):
                    covering += 1
        assert covering == 1

    def test_fresh_table_not_double_indexed(self, sqlite_db):
        """A fresh table already carries the constraint; repair must skip it."""
        db_module.init_field_changes_table()  # fresh create
        engine = db_module.get_engine()
        assert _has_uq(engine, "contract_field_changes", self.KEY)
        # no extra named repair index should have been created
        with engine.connect() as conn:
            names = [r[1] for r in conn.execute(text("PRAGMA index_list(contract_field_changes)"))]
        assert "uq_contract_field_changes_run_internal_field" not in names


# ---------------------------------------------------------------------------
# contract_snapshots (closely related ingest-path table, same pattern)
# ---------------------------------------------------------------------------

class TestSnapshotsUniqueRepair:
    KEY = ("run_date", "internal_id")

    def test_legacy_table_gains_unique_index(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_snapshots(engine)
        assert not _has_uq(engine, "contract_snapshots", self.KEY)
        db_module.init_snapshots_table()
        assert _has_uq(engine, "contract_snapshots", self.KEY)

    def test_on_conflict_works_after_repair(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_snapshots(engine)
        db_module.init_snapshots_table()
        with engine.begin() as conn:
            for _ in range(2):
                conn.execute(text("""
                    INSERT INTO contract_snapshots (run_date, internal_id, vendor)
                    VALUES ('2026-06-26', 'C1', 'Acme')
                    ON CONFLICT(run_date, internal_id) DO UPDATE SET vendor=excluded.vendor
                """))
            n = conn.execute(text(
                "SELECT COUNT(*) FROM contract_snapshots WHERE internal_id='C1'"
            )).scalar()
        assert n == 1

    def test_dedupes_before_creating_unique_index(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_snapshots(engine)
        with engine.begin() as conn:
            for _ in range(2):
                conn.execute(text(
                    "INSERT INTO contract_snapshots (run_date, internal_id, vendor) "
                    "VALUES ('2026-06-26', 'D1', 'Acme')"
                ))
        db_module.init_snapshots_table()
        assert _has_uq(engine, "contract_snapshots", self.KEY)
        with engine.connect() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM contract_snapshots WHERE internal_id='D1'"
            )).scalar()
        assert n == 1
