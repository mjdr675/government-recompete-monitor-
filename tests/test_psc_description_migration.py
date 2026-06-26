"""Focused tests for the psc_description schema fix (data-pipeline).

Databases created before ``psc_description`` was added to the contracts
CREATE TABLE never gained the column (CREATE TABLE IF NOT EXISTS is a no-op on
an existing table), so ``save_snapshot``/``upsert_contract`` failed with
"table contracts has no column named psc_description".

``db.init_db()`` must repair such pre-existing SQLite databases by adding the
column idempotently, preserving existing rows, and the Postgres-only backfill
migration must never run on the SQLite init path.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text

import db as db_module


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    # CSV writes from any downstream call land in scratch, not the repo.
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


def _cols(engine):
    with engine.connect() as conn:
        return [r[1] for r in conn.execute(text("PRAGMA table_info(contracts)"))]


def _drop_psc_description(engine):
    """Simulate a pre-migration database: full schema minus psc_description."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE contracts DROP COLUMN psc_description"))


class TestPscDescriptionColumnMigration:
    def test_brand_new_db_has_column(self, sqlite_db):
        db_module.init_db()
        assert "psc_description" in _cols(db_module.get_engine())

    def test_existing_table_without_column_gets_it(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        _drop_psc_description(engine)
        assert "psc_description" not in _cols(engine)

        db_module.init_db()  # repair pass
        assert "psc_description" in _cols(engine)

    def test_existing_rows_survive_migration(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        db_module.upsert_contract({
            "internal_id": "KEEP_1",
            "award_id": "AWD-KEEP",
            "vendor": "Acme Janitorial",
            "agency": "GSA",
        })
        _drop_psc_description(engine)

        db_module.init_db()  # repair must not lose the existing row
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT vendor, psc_description FROM contracts WHERE internal_id = 'KEEP_1'"
            )).fetchone()
        assert row[0] == "Acme Janitorial"
        assert row[1] is None  # newly added column defaults NULL

    def test_init_is_idempotent(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        _drop_psc_description(engine)
        db_module.init_db()
        db_module.init_db()  # second repair must not raise or duplicate
        assert _cols(engine).count("psc_description") == 1

    def test_save_snapshot_persists_psc_description_after_repair(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        _drop_psc_description(engine)
        db_module.init_db()

        db_module.upsert_contract({
            "internal_id": "AWD_X",
            "award_id": "AWD-X",
            "vendor": "Globex",
            "agency": "Department of Defense",
            "description": "custodial services",
            "psc_description": "JANITORIAL SERVICES",
        })
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT psc_description FROM contracts WHERE internal_id = 'AWD_X'"
            )).scalar()
        assert val == "JANITORIAL SERVICES"

    def test_sqlite_init_does_not_run_pg_migrations(self, sqlite_db):
        """The SQLite init path uses _ensure_* helpers, not the .sql migration
        runner — so the Postgres-only 016 backfill SQL never executes (and so
        cannot fail) on SQLite."""
        with patch.object(db_module, "_apply_migrations") as mock_apply:
            db_module.init_db()
        mock_apply.assert_not_called()
        assert "psc_description" in _cols(db_module.get_engine())
