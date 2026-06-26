"""Focused tests for the contract_field_changes.change_kind schema repair.

Databases whose contract_field_changes table predates the change_kind column
never gained it (CREATE TABLE IF NOT EXISTS is a no-op on an existing table),
so insert_field_changes() failed in production with
"table contract_field_changes has no column named change_kind".

db.init_field_changes_table() must repair such pre-existing SQLite tables by
adding the column idempotently, preserving existing rows.
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


def _cols(engine):
    with engine.connect() as conn:
        return [r[1] for r in conn.execute(text("PRAGMA table_info(contract_field_changes)"))]


def _legacy_table(engine):
    """Create a pre-change_kind contract_field_changes table (older shape)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE contract_field_changes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date    TEXT NOT NULL,
                internal_id TEXT NOT NULL,
                field_name  TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_date, internal_id, field_name)
            )
        """))


class TestChangeKindColumnRepair:
    def test_fresh_table_has_change_kind(self, sqlite_db):
        db_module.init_field_changes_table()
        assert "change_kind" in _cols(db_module.get_engine())

    def test_legacy_table_gets_change_kind(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_table(engine)
        assert "change_kind" not in _cols(engine)

        db_module.init_field_changes_table()
        assert "change_kind" in _cols(engine)

    def test_existing_rows_survive_repair(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_table(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO contract_field_changes (run_date, internal_id, field_name) "
                "VALUES ('2026-06-26', 'C1', 'value')"
            ))
        db_module.init_field_changes_table()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT internal_id, field_name FROM contract_field_changes WHERE internal_id='C1'"
            )).fetchone()
        assert row == ("C1", "value")

    def test_repair_is_idempotent(self, sqlite_db):
        engine = db_module.get_engine()
        _legacy_table(engine)
        db_module.init_field_changes_table()
        db_module.init_field_changes_table()  # must not raise or duplicate
        assert _cols(engine).count("change_kind") == 1

    def test_insert_field_changes_works_after_repair(self, sqlite_db):
        """Regression: insert_field_changes must succeed on a legacy table."""
        engine = db_module.get_engine()
        _legacy_table(engine)
        written = db_module.insert_field_changes("2026-06-26", [
            {
                "internal_id": "AWD_1",
                "field_name": "value",
                "old_value": "100",
                "new_value": "200",
                "change_kind": "MODIFIED",
            },
        ])
        assert written == 1
        with engine.connect() as conn:
            kind = conn.execute(text(
                "SELECT change_kind FROM contract_field_changes WHERE internal_id='AWD_1'"
            )).scalar()
        assert kind == "MODIFIED"
