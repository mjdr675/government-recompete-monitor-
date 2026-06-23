"""Tests for R-06: PostgreSQL migration file 002 and _apply_pg_migrations logic."""
import os
import pytest
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


class TestMigrationFileExists:
    def test_002_file_exists(self):
        assert (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").exists()

    def test_002_contains_stripe_customer_id(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text()
        assert "stripe_customer_id" in sql

    def test_002_contains_subscription_status(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text()
        assert "subscription_status" in sql

    def test_002_contains_trial_ends_at(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text()
        assert "trial_ends_at" in sql

    def test_002_contains_alert_preferences_table(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text()
        assert "alert_preferences" in sql

    def test_002_contains_alert_log_table(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text()
        assert "alert_log" in sql

    def test_002_uses_if_not_exists(self):
        sql = (MIGRATIONS_DIR / "002_subscription_and_alerts.sql").read_text().upper()
        assert "IF NOT EXISTS" in sql

    def test_001_and_002_exist(self):
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        names = [f.name for f in files]
        assert "001_initial_pg.sql" in names
        assert "002_subscription_and_alerts.sql" in names
        assert names.index("002_subscription_and_alerts.sql") > names.index("001_initial_pg.sql")


class TestApplyPgMigrationsFunction:
    def test_apply_pg_migrations_is_callable(self):
        import db as db_module
        assert callable(db_module._apply_pg_migrations)

    def test_init_db_calls_migrations_for_pg(self, monkeypatch, tmp_path):
        """Simulate DATABASE_URL set: init_db should invoke the migration runner."""
        called = []

        import db as db_module
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake/testdb")
        # init_db() now calls _apply_migrations() directly; _apply_pg_migrations is
        # kept as a backward-compat alias that also delegates to _apply_migrations().
        monkeypatch.setattr(db_module, "_apply_migrations",
                            lambda migrations_dir=None: called.append(True))
        db_module._cached_engine.cache_clear()

        db_module.init_db()
        assert called == [True]
