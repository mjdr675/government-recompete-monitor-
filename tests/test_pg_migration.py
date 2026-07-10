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


class TestMigrationsArePostgresCompatible:
    """The SQL migration files run against PostgreSQL in production (the SQLite
    dev path skips them entirely). Guard against SQLite-only syntax that Postgres
    rejects. Regression for 008_notification_preferences.sql, which used
    `INTEGER PRIMARY KEY AUTOINCREMENT` and aborted the Postgres schema build
    with `syntax error at or near "AUTOINCREMENT"`."""

    # Tokens SQLite accepts but PostgreSQL does not.
    _SQLITE_ONLY = ("AUTOINCREMENT", "WITHOUT ROWID")

    def _sql_files(self):
        return sorted(MIGRATIONS_DIR.glob("*.sql"))

    def test_no_autoincrement_in_any_migration(self):
        offenders = [f.name for f in self._sql_files() if "AUTOINCREMENT" in f.read_text().upper()]
        assert not offenders, (
            f"SQLite-only AUTOINCREMENT found in Postgres migration(s): {offenders}; "
            "use SERIAL PRIMARY KEY instead"
        )

    def test_no_sqlite_only_syntax_in_any_migration(self):
        offenders = {}
        for f in self._sql_files():
            up = f.read_text().upper()
            hits = [tok for tok in self._SQLITE_ONLY if tok in up]
            if hits:
                offenders[f.name] = hits
        assert not offenders, f"SQLite-only syntax in Postgres migration(s): {offenders}"

    def test_008_uses_serial_primary_key(self):
        sql = (MIGRATIONS_DIR / "008_notification_preferences.sql").read_text().upper()
        assert "SERIAL PRIMARY KEY" in sql
        assert "AUTOINCREMENT" not in sql

    def test_no_set_returning_regexp_matches_in_migrations(self):
        """``regexp_matches()`` is a set-returning function. PostgreSQL forbids
        set-returning functions in ``UPDATE ... SET`` and aborts the migration
        with `set-returning functions are not allowed in UPDATE`. The scalar
        ``regexp_match()`` (returns text[]) must be used instead. Regression for
        016_backfill_psc_description.sql, which halted the Postgres schema build
        at cutover. Checks the comment-stripped SQL (via the real migration
        runner's splitter) so documentation mentioning the antipattern does not
        trip the guard."""
        import re
        import db as db_module
        pat = re.compile(r"\bregexp_matches\s*\(", re.IGNORECASE)
        offenders = set()
        for f in self._sql_files():
            for stmt in db_module._split_sql_statements(f.read_text()):
                if pat.search(stmt):
                    offenders.add(f.name)
        assert not offenders, (
            "set-returning regexp_matches() found in Postgres migration(s): "
            f"{sorted(offenders)}; use the scalar regexp_match() instead"
        )

    def test_016_backfill_uses_scalar_regexp_match(self):
        """The 016 backfill must extract psc_description with the scalar
        regexp_match()[1] form so it is valid inside UPDATE ... SET on Postgres.
        Asserts against the executable SQL (comments stripped)."""
        import db as db_module
        stmts = db_module._split_sql_statements(
            (MIGRATIONS_DIR / "016_backfill_psc_description.sql").read_text()
        )
        sql = " ".join(stmts)
        assert "regexp_match(" in sql, "expected scalar regexp_match() in 016 backfill"
        assert "regexp_matches(" not in sql, (
            "016 backfill still uses set-returning regexp_matches() in UPDATE ... SET"
        )


class TestCompanyProfilesUeiPreserved:
    """Pre-load drift found a real SAM UEI in the SQLite snapshot's
    company_profiles.uei that the Postgres schema lacked, so a fresh-load would
    drop it as source-only. Beyond preservation, db.save_company_profile() upserts
    company_profiles.{uei, vendor_name, cage_code} against the shared engine
    (Postgres when DATABASE_URL is set), so those three columns must exist on
    Postgres or the live app raises UndefinedColumn. A migration must add all
    three. users.billing_interval is a vestigial column no code writes (the app's
    billing_interval lives on workspaces) and is all-NULL in the snapshot — it
    stays a consciously accepted drop."""

    def _sql_files(self):
        return sorted(MIGRATIONS_DIR.glob("*.sql"))

    def _adds_column(self, table, col):
        import re
        pat = re.compile(
            rf"ALTER\s+TABLE\s+{table}\s+ADD\s+COLUMN\s+(IF\s+NOT\s+EXISTS\s+)?{col}\b",
            re.IGNORECASE,
        )
        return [f.name for f in self._sql_files() if pat.search(f.read_text())]

    def test_company_profiles_uei_added_by_migration(self):
        assert self._adds_column("company_profiles", "uei"), (
            "no migration adds company_profiles.uei; fresh-load would drop the "
            "SAM UEI as source-only"
        )

    def test_company_profiles_app_written_columns_added(self):
        # save_company_profile() writes all three on the Postgres path.
        for col in ("uei", "vendor_name", "cage_code"):
            assert self._adds_column("company_profiles", col), (
                f"no migration adds company_profiles.{col}; the app upsert writes "
                "it and would fail on Postgres"
            )

    def test_users_billing_interval_remains_accepted_drop(self):
        assert not self._adds_column("users", "billing_interval"), (
            "users.billing_interval was added; it is a vestigial all-NULL column "
            "that stays an accepted source-only drop"
        )


class TestSqlStatementSplitter:
    """db._split_sql_statements must strip line comments BEFORE splitting on ';'
    so a semicolon inside a comment cannot leak comment text into the SQL.
    Regression for 009_contracts_ci_columns.sql ('...ready; display logic ...')."""

    def _split(self, sql):
        import db as db_module
        return db_module._split_sql_statements(sql)

    def test_semicolon_inside_comment_does_not_split_or_leak(self):
        sql = (
            "-- Column is added now so the schema is ready; display logic shows nothing\n"
            "-- when NULL.\n"
            "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS vendor_website TEXT;\n"
        )
        stmts = self._split(sql)
        assert stmts == ["ALTER TABLE contracts ADD COLUMN IF NOT EXISTS vendor_website TEXT"]
        assert not any("display" in s for s in stmts)

    def test_full_line_and_inline_comments_removed(self):
        sql = (
            "-- a full-line comment;\n"
            "CREATE TABLE t (id SERIAL PRIMARY KEY);  -- trailing; comment\n"
        )
        stmts = self._split(sql)
        assert stmts == ["CREATE TABLE t (id SERIAL PRIMARY KEY)"]

    def test_multiple_statements_split(self):
        sql = "CREATE TABLE a (id INT);\nALTER TABLE a ADD COLUMN x TEXT;\n"
        assert self._split(sql) == [
            "CREATE TABLE a (id INT)",
            "ALTER TABLE a ADD COLUMN x TEXT",
        ]

    def test_empty_and_comment_only_input_yields_no_statements(self):
        assert self._split("-- just a comment;\n\n  \n") == []


class TestAllMigrationsParseToKeywordStatements:
    """Parsing every migration with the real runner splitter must yield only
    statements that begin with a SQL keyword — i.e. no leaked comment fragment
    (before the fix, 009 produced a statement starting with 'display')."""

    _KEYWORDS = {
        "CREATE", "ALTER", "INSERT", "UPDATE", "DELETE", "DROP",
        "COMMENT", "WITH", "SELECT", "DO", "GRANT", "BEGIN", "SET",
    }

    def test_no_migration_leaks_comment_text_into_sql(self):
        import db as db_module
        offenders = {}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            for stmt in db_module._split_sql_statements(f.read_text()):
                first = stmt.split(None, 1)[0].upper()
                if first not in self._KEYWORDS:
                    offenders.setdefault(f.name, []).append(stmt[:60])
        assert not offenders, f"non-keyword (leaked/comment) statements: {offenders}"
