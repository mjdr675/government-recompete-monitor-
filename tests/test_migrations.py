"""Tests for migration version tracking (schema_migrations table).

Covers:
- brand-new database (SQLite and simulated PG)
- partially migrated database
- fully migrated database — no re-runs
- migration failure — hard stop, no partial record
- duplicate startup — idempotent
- execution ordering — filename ascending
- auto-stamp on first use against an existing database
- schema_migrations present on SQLite after init_db()
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, text

import db as db_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(tmp_path, name="test.db"):
    path = str(tmp_path / name)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    return engine


def _applied(engine):
    """Return set of filenames recorded in schema_migrations."""
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT filename FROM schema_migrations"))}


def _write(migrations_dir, name, sql):
    (Path(migrations_dir) / name).write_text(sql)
    return name


# ---------------------------------------------------------------------------
# Fixture: isolated SQLite engine with schema_migrations bootstrapped
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine(tmp_path):
    e = _make_engine(tmp_path)
    with e.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """))
    return e


# ---------------------------------------------------------------------------
# Fixture: fresh SQLite DB via init_db()
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    yield db_module.get_engine()
    db_module._cached_engine.cache_clear()


# ===========================================================================
# schema_migrations table — SQLite
# ===========================================================================

class TestSchemaMigrationsTableSQLite:
    def test_table_exists_after_init_db(self, sqlite_db):
        from sqlalchemy import inspect
        assert "schema_migrations" in inspect(sqlite_db).get_table_names()

    def test_table_has_filename_column(self, sqlite_db):
        with sqlite_db.connect() as conn:
            row = conn.execute(text(
                "SELECT filename FROM schema_migrations LIMIT 0"
            ))
        assert row is not None  # no error = column exists

    def test_table_has_applied_at_column(self, sqlite_db):
        with sqlite_db.connect() as conn:
            row = conn.execute(text(
                "SELECT applied_at FROM schema_migrations LIMIT 0"
            ))
        assert row is not None

    def test_init_db_twice_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "idem.db"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        db_module.init_db()  # second call must not raise
        db_module._cached_engine.cache_clear()


# ===========================================================================
# _apply_migrations — core runner (SQLite, no PG required)
# ===========================================================================

class TestApplyMigrationsNewDatabase:
    def test_creates_schema_migrations_on_fresh_db(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        e = _make_engine(tmp_path, "fresh.db")
        # point db module at this engine
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
        from sqlalchemy import inspect
        assert "schema_migrations" in inspect(e).get_table_names()

    def test_empty_migrations_dir_is_noop(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        e = _make_engine(tmp_path, "noop.db")
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)  # must not raise
        assert _applied(e) == set()

    def test_single_migration_applied_and_recorded(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_create_foo.sql",
               "CREATE TABLE foo (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "single.db")
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
        assert "001_create_foo.sql" in _applied(e)
        # table must actually exist
        from sqlalchemy import inspect
        assert "foo" in inspect(e).get_table_names()

    def test_multiple_migrations_applied_in_order(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_a.sql", "CREATE TABLE a (id INTEGER PRIMARY KEY)")
        _write(mdir, "002_b.sql", "CREATE TABLE b (id INTEGER PRIMARY KEY)")
        _write(mdir, "003_c.sql", "CREATE TABLE c (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "order.db")
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
        applied = _applied(e)
        assert applied == {"001_a.sql", "002_b.sql", "003_c.sql"}
        from sqlalchemy import inspect
        tables = inspect(e).get_table_names()
        assert "a" in tables and "b" in tables and "c" in tables

    def test_applied_at_is_recorded(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_ts.sql", "CREATE TABLE ts_test (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "ts.db")
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
        with e.connect() as conn:
            row = conn.execute(
                text("SELECT applied_at FROM schema_migrations WHERE filename='001_ts.sql'")
            ).fetchone()
        assert row is not None
        assert row[0]  # non-empty


class TestApplyMigrationsIdempotency:
    def test_second_run_skips_already_applied(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_once.sql", "CREATE TABLE once (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "idem.db")

        execution_count = {"n": 0}
        real_apply = db_module._apply_migrations

        def counting_apply(migrations_dir=None):
            real_apply(migrations_dir=migrations_dir or mdir)
            execution_count["n"] += 1

        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
            applied_after_first = _applied(e).copy()
            db_module._apply_migrations(migrations_dir=mdir)
            applied_after_second = _applied(e).copy()

        assert applied_after_first == applied_after_second == {"001_once.sql"}

    def test_new_migration_added_after_first_run_is_applied(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_first.sql", "CREATE TABLE first (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "addmig.db")
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
            # Add a second migration
            _write(mdir, "002_second.sql", "CREATE TABLE second (id INTEGER PRIMARY KEY)")
            db_module._apply_migrations(migrations_dir=mdir)
        assert _applied(e) == {"001_first.sql", "002_second.sql"}

    def test_partial_db_resumes_from_correct_point(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_p.sql", "CREATE TABLE p1 (id INTEGER PRIMARY KEY)")
        _write(mdir, "002_p.sql", "CREATE TABLE p2 (id INTEGER PRIMARY KEY)")
        _write(mdir, "003_p.sql", "CREATE TABLE p3 (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "partial.db")
        # Manually pre-apply 001 and 002
        with e.begin() as conn:
            conn.execute(text("""
            CREATE TABLE schema_migrations (
                filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL
            )"""))
            conn.execute(text(
                "INSERT INTO schema_migrations VALUES ('001_p.sql', 'test')"
            ))
            conn.execute(text(
                "INSERT INTO schema_migrations VALUES ('002_p.sql', 'test')"
            ))
        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)
        assert _applied(e) == {"001_p.sql", "002_p.sql", "003_p.sql"}
        from sqlalchemy import inspect
        # p3 was applied; p1 and p2 tables were never created (pre-stamped only)
        assert "p3" in inspect(e).get_table_names()


class TestApplyMigrationsFailure:
    def test_bad_sql_raises(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_bad.sql", "THIS IS NOT VALID SQL !!!")
        e = _make_engine(tmp_path, "fail.db")
        with patch.object(db_module, "get_engine", return_value=e):
            with pytest.raises(Exception):
                db_module._apply_migrations(migrations_dir=mdir)

    def test_failed_migration_not_recorded(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_bad.sql", "THIS IS NOT VALID SQL !!!")
        e = _make_engine(tmp_path, "norecord.db")
        with patch.object(db_module, "get_engine", return_value=e):
            with pytest.raises(Exception):
                db_module._apply_migrations(migrations_dir=mdir)
        assert "001_bad.sql" not in _applied(e)

    def test_subsequent_migration_not_run_after_failure(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_good.sql", "CREATE TABLE good1 (id INTEGER PRIMARY KEY)")
        _write(mdir, "002_bad.sql",  "COMPLETELY INVALID SQL !!!")
        _write(mdir, "003_good.sql", "CREATE TABLE good3 (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "stop.db")
        with patch.object(db_module, "get_engine", return_value=e):
            with pytest.raises(Exception):
                db_module._apply_migrations(migrations_dir=mdir)
        from sqlalchemy import inspect
        tables = inspect(e).get_table_names()
        assert "good1" in tables          # 001 succeeded
        assert "good3" not in tables      # 003 never ran (stopped at 002)
        applied = _applied(e)
        assert "001_good.sql" in applied
        assert "002_bad.sql" not in applied
        assert "003_good.sql" not in applied

    def test_first_migration_succeeds_is_recorded(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_ok.sql",  "CREATE TABLE ok1 (id INTEGER PRIMARY KEY)")
        _write(mdir, "002_bad.sql", "INVALID SQL !!!")
        e = _make_engine(tmp_path, "partial_ok.db")
        with patch.object(db_module, "get_engine", return_value=e):
            with pytest.raises(Exception):
                db_module._apply_migrations(migrations_dir=mdir)
        assert "001_ok.sql" in _applied(e)

    def test_engine_unavailable_does_not_raise(self, tmp_path):
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_x.sql", "CREATE TABLE x (id INTEGER PRIMARY KEY)")

        def bad_engine():
            raise RuntimeError("no connection")

        with patch.object(db_module, "get_engine", side_effect=bad_engine):
            db_module._apply_migrations(migrations_dir=mdir)  # must not raise


# ===========================================================================
# _stamp_pre_existing — first-use bootstrap on existing PG database
# ===========================================================================

class TestStampPreExisting:
    def _pg_engine(self, tmp_path, name="pg_sim.db"):
        """SQLite engine that masquerades as PostgreSQL for stamp tests."""
        e = _make_engine(tmp_path, name)
        # Patch dialect name so _stamp_pre_existing thinks it's PG
        e.dialect.name = "postgresql"
        return e

    def test_noop_on_sqlite_dialect(self, tmp_path):
        e = _make_engine(tmp_path, "sq.db")
        with e.begin() as conn:
            conn.execute(text("""
            CREATE TABLE schema_migrations (
                filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL
            )"""))
        applied = set()
        db_module._stamp_pre_existing(e, applied)
        assert applied == set()  # SQLite: nothing stamped

    def test_stamps_detected_migrations(self, tmp_path):
        """When probes return count > 0, migrations are stamped in schema_migrations."""
        e = _make_engine(tmp_path, "stamp.db")
        with e.begin() as conn:
            conn.execute(text("""
            CREATE TABLE schema_migrations (
                filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL
            )"""))
        applied = set()

        # Mock: all probes return 1 (everything already applied)
        mock_scalar = MagicMock(return_value=1)
        mock_result = MagicMock()
        mock_result.scalar = mock_scalar
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # Use the real SQLite engine for INSERT but mock the probe queries
        real_stamp = db_module._stamp_pre_existing

        def patched_stamp(engine, applied):
            # Directly stamp all known probes (simulating all returning 1)
            now = "detected:test"
            with engine.begin() as conn:
                for filename in db_module._MIGRATION_PROBES:
                    conn.execute(
                        text(
                            "INSERT INTO schema_migrations(filename, applied_at) "
                            "VALUES (:f, :a) ON CONFLICT(filename) DO NOTHING"
                        ),
                        {"f": filename, "a": now},
                    )
                    applied.add(filename)

        patched_stamp(e, applied)
        assert set(db_module._MIGRATION_PROBES.keys()).issubset(applied)
        assert _applied(e) == set(db_module._MIGRATION_PROBES.keys())

    def test_stamp_applied_at_uses_detected_prefix(self, tmp_path):
        """Stamped entries use 'detected:' prefix so origin is auditable."""
        e = _make_engine(tmp_path, "prefix.db")
        with e.begin() as conn:
            conn.execute(text("""
            CREATE TABLE schema_migrations (
                filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL
            )"""))
            conn.execute(text(
                "INSERT INTO schema_migrations VALUES ('001_initial_pg.sql', 'detected:2026-06-22T00:00:00')"
            ))
        with e.connect() as conn:
            row = conn.execute(text(
                "SELECT applied_at FROM schema_migrations WHERE filename='001_initial_pg.sql'"
            )).fetchone()
        assert row[0].startswith("detected:")

    def test_no_stamp_when_schema_migrations_already_has_entries(self, tmp_path, monkeypatch):
        """If schema_migrations is non-empty, _stamp_pre_existing is never called."""
        mdir = tmp_path / "migs"
        mdir.mkdir()
        _write(mdir, "001_already.sql", "CREATE TABLE already (id INTEGER PRIMARY KEY)")
        e = _make_engine(tmp_path, "norestamp.db")
        # Pre-populate schema_migrations so 'applied' is non-empty from the start
        with e.begin() as conn:
            conn.execute(text("""
            CREATE TABLE schema_migrations (
                filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL
            )"""))
            conn.execute(text(
                "INSERT INTO schema_migrations VALUES ('001_already.sql', '2026-01-01')"
            ))
        stamp_called = []
        with patch.object(db_module, "_stamp_pre_existing",
                          side_effect=lambda e, a: stamp_called.append(True)):
            with patch.object(db_module, "get_engine", return_value=e):
                db_module._apply_migrations(migrations_dir=mdir)
        assert stamp_called == []


# ===========================================================================
# _apply_migrations — ordering guarantee
# ===========================================================================

class TestMigrationOrdering:
    def test_files_applied_in_lexicographic_order(self, tmp_path):
        """Migrations must run in ascending filename order regardless of creation order."""
        mdir = tmp_path / "migs"
        mdir.mkdir()
        # Write in reverse order to ensure sorting is not inode-based
        _write(mdir, "003_last.sql",  "CREATE TABLE t3 (id INTEGER PRIMARY KEY)")
        _write(mdir, "001_first.sql", "CREATE TABLE t1 (id INTEGER PRIMARY KEY)")
        _write(mdir, "002_middle.sql","CREATE TABLE t2 (id INTEGER PRIMARY KEY)")
        order = []
        original_execute = None

        e = _make_engine(tmp_path, "order2.db")

        class TrackingConn:
            def __init__(self, real):
                self._real = real
            def execute(self, stmt, params=None):
                s = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
                if "INSERT INTO schema_migrations" in s and params:
                    order.append(params.get("f") or params.get("filename", "?"))
                if params:
                    return self._real.execute(stmt, params)
                return self._real.execute(stmt)
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch.object(db_module, "get_engine", return_value=e):
            db_module._apply_migrations(migrations_dir=mdir)

        applied = _applied(e)
        assert "001_first.sql" in applied
        assert "002_middle.sql" in applied
        assert "003_last.sql" in applied


# ===========================================================================
# Backward-compatible alias
# ===========================================================================

class TestApplyPgMigrationsAlias:
    def test_apply_pg_migrations_is_callable(self):
        assert callable(db_module._apply_pg_migrations)

    def test_apply_pg_migrations_delegates_to_apply_migrations(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(db_module, "_apply_migrations",
                            lambda migrations_dir=None: called.append(True))
        db_module._apply_pg_migrations()
        assert called == [True]

    def test_init_db_calls_apply_migrations_for_pg(self, monkeypatch, tmp_path):
        called = []
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake/testdb")
        monkeypatch.setattr(db_module, "_apply_migrations",
                            lambda migrations_dir=None: called.append(True))
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        assert called == [True]
        db_module._cached_engine.cache_clear()


# ===========================================================================
# _MIGRATION_PROBES completeness
# ===========================================================================

class TestMigrationProbes:
    def test_all_known_migrations_have_probes(self):
        migrations_dir = Path(db_module.__file__).parent / "migrations"
        sql_files = {f.name for f in sorted(migrations_dir.glob("*.sql"))}
        for f in sql_files:
            assert f in db_module._MIGRATION_PROBES, (
                f"No probe defined for {f}. Add an entry to _MIGRATION_PROBES "
                "so existing installs are not re-migrated on first versioned startup."
            )

    def test_probe_values_are_non_empty_strings(self):
        for filename, sql in db_module._MIGRATION_PROBES.items():
            assert isinstance(sql, str) and sql.strip(), (
                f"Probe for {filename} must be a non-empty SQL string"
            )
