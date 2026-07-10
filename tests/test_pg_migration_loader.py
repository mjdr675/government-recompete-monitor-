"""Tests for scripts/migrate_sqlite_to_pg.py.

The full load path is exercised SQLite→SQLite (no external Postgres needed);
Postgres-specific SQL (TRUNCATE ... RESTART IDENTITY, setval sequence reset) is
covered by unit tests on the pure SQL builders. No tests are skipped.
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

# Load the script module by path (it lives in scripts/, not an importable package).
_SPEC = importlib.util.spec_from_file_location(
    "migrate_sqlite_to_pg",
    Path(__file__).resolve().parent.parent / "scripts" / "migrate_sqlite_to_pg.py",
)
loader = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = loader  # required so @dataclass can resolve the module
_SPEC.loader.exec_module(loader)


# --------------------------------------------------------------------------- #
# Unit tests — pure helpers (no DB)
# --------------------------------------------------------------------------- #
def test_topo_sort_orders_parents_before_children():
    edges = {"child": {"parent"}, "parent": set(), "grandchild": {"child"}}
    order = loader.topo_sort(["grandchild", "child", "parent"], edges)
    assert order.index("parent") < order.index("child") < order.index("grandchild")


def test_topo_sort_handles_cycle_without_hanging():
    edges = {"a": {"b"}, "b": {"a"}}
    order = loader.topo_sort(["a", "b"], edges)
    assert set(order) == {"a", "b"}  # both emitted, no infinite loop


def test_is_excluded_covers_ledger_and_fts_and_internal():
    exc = loader.DEFAULT_EXCLUDE
    assert loader.is_excluded("schema_migrations", exc)
    assert loader.is_excluded("sqlite_sequence", exc)
    assert loader.is_excluded("contracts_fts", exc)
    assert loader.is_excluded("contracts_fts_data", exc)
    assert not loader.is_excluded("contracts", exc)


def test_truncate_sql_dialect_specific():
    pg = loader.build_truncate_sql("postgresql", "users")
    assert pg == 'TRUNCATE TABLE "users" RESTART IDENTITY CASCADE'
    lite = loader.build_truncate_sql("sqlite", "users")
    assert lite == 'DELETE FROM "users"'


def test_seq_reset_sql_uses_setval_and_guard():
    sql = loader.build_seq_reset_sql("users", "id")
    assert "setval(" in sql
    assert "pg_get_serial_sequence('users', 'id')" in sql
    assert "IS NOT NULL" in sql  # guard: no-op when the column owns no sequence
    # MAX is deferred inside EXECUTE format() so it is only planned for a
    # sequence-owning (integer) column, never at top level.
    assert "EXECUTE format(" in sql
    assert "MAX(%I)" in sql


def test_seq_reset_text_pk_defers_max_behind_guard():
    """A TEXT primary key (contracts.internal_id) must NOT produce a top-level
    COALESCE(text, integer): the MAX() is deferred behind the
    pg_get_serial_sequence guard via EXECUTE format(), so Postgres never plans
    the text/integer mismatch. Regression for the fresh-load abort
    (`COALESCE types text and integer cannot be matched`)."""
    sql = loader.build_seq_reset_sql("contracts", "internal_id")
    assert "pg_get_serial_sequence('contracts', 'internal_id')" in sql
    assert "IS NOT NULL" in sql
    assert "EXECUTE format(" in sql
    # the deferred, identifier-agnostic form only — never a concrete
    # COALESCE(MAX("internal_id"), 1) that would be planned up front
    assert "COALESCE((SELECT MAX(%I) FROM %I), 1)" in sql
    assert 'MAX("internal_id")' not in sql


def test_seq_reset_integer_pk_still_generates_setval():
    sql = loader.build_seq_reset_sql("lead_companies", "id")
    assert "setval(" in sql
    assert "pg_get_serial_sequence('lead_companies', 'id')" in sql
    assert "EXECUTE format(" in sql
    assert "MAX(%I)" in sql


def test_seq_reset_is_type_safe_do_block():
    """The statement is a guarded DO block for any PK type, so no concrete
    (planned) COALESCE over a text column is ever emitted."""
    for table, pk in (("contracts", "internal_id"), ("users", "id")):
        sql = loader.build_seq_reset_sql(table, pk).strip()
        assert sql.startswith("DO $$")
        assert sql.endswith("$$;")
        assert 'COALESCE((SELECT MAX("' not in sql  # no up-front text/int COALESCE


def test_quote_ident_escapes_quotes():
    assert loader.quote_ident("a") == '"a"'
    assert loader.quote_ident('we"ird') == '"we""ird"'


# --------------------------------------------------------------------------- #
# Integration — SQLite source snapshot → SQLite target
# --------------------------------------------------------------------------- #
def _make_source(path, *, child_val="ok"):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id),
            val TEXT
        );
        CREATE TABLE widget (id INTEGER PRIMARY KEY, a TEXT, b TEXT);
        CREATE TABLE schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT);
        """
    )
    con.execute("INSERT INTO parent VALUES (1, 'p1'), (2, 'p2')")
    con.execute("INSERT INTO child VALUES (10, 1, ?), (11, 2, ?)", (child_val, "ok"))
    con.execute("INSERT INTO widget VALUES (1, 'aa', 'bb')")
    con.execute("INSERT INTO schema_migrations VALUES ('001', 'x')")
    con.commit()
    con.close()


def _make_target(path, *, widget_has_b=False, child_val_notnull=False):
    con = sqlite3.connect(path)
    child_val = "val TEXT NOT NULL" if child_val_notnull else "val TEXT"
    widget_cols = "id INTEGER PRIMARY KEY, a TEXT, b TEXT" if widget_has_b else (
        "id INTEGER PRIMARY KEY, a TEXT"
    )
    con.executescript(
        f"""
        CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id),
            {child_val}
        );
        CREATE TABLE widget ({widget_cols});
        CREATE TABLE schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT);
        """
    )
    con.commit()
    con.close()


def _count(path, table):
    con = sqlite3.connect(path)
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        con.close()


@pytest.fixture()
def src(tmp_path):
    p = tmp_path / "snapshot.db"
    _make_source(str(p))
    return str(p)


def _target_url(path):
    return f"sqlite:///{path}"


def test_full_load_copies_rows_and_verifies(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    plans = loader.load(src, _target_url(str(tgt)))
    names = [p.name for p in plans]
    assert "schema_migrations" not in names  # excluded
    assert _count(str(tgt), "parent") == 2
    assert _count(str(tgt), "child") == 2
    assert _count(str(tgt), "widget") == 1
    # schema_migrations on target left as-is (owned by _apply_migrations).
    assert _count(str(tgt), "schema_migrations") == 0


def test_load_order_is_parents_before_children(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    plans = loader.load(src, _target_url(str(tgt)), dry_run=True)
    order = [p.name for p in plans]
    assert order.index("parent") < order.index("child")


def test_column_intersection_drops_target_missing_columns(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt), widget_has_b=False)  # target widget lacks column b
    plans = loader.load(src, _target_url(str(tgt)))
    widget = next(p for p in plans if p.name == "widget")
    assert widget.columns == ["id", "a"]
    assert widget.dropped_source_only == ["b"]


def _make_company_profiles_db(path, *, has_uei, uei_value=None):
    con = sqlite3.connect(path)
    cols = "id INTEGER PRIMARY KEY, user_id INTEGER, uei TEXT" if has_uei else (
        "id INTEGER PRIMARY KEY, user_id INTEGER"
    )
    con.executescript(
        f"""
        CREATE TABLE company_profiles ({cols});
        CREATE TABLE schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT);
        """
    )
    if uei_value is not None:
        con.execute("INSERT INTO company_profiles VALUES (1, 1, ?)", (uei_value,))
    else:
        con.execute("INSERT INTO company_profiles (id, user_id) VALUES (1, 1)")
    con.commit()
    con.close()


def test_company_profiles_uei_preserved_when_target_has_column(tmp_path):
    """Regression for pre-load drift: once the Postgres schema has
    company_profiles.uei (migration 024) the loader must map it — not drop it —
    so the real SAM UEI in the source is preserved on fresh-load."""
    src = tmp_path / "src.db"
    _make_company_profiles_db(str(src), has_uei=True, uei_value="ABC123DEF456")
    tgt = tmp_path / "tgt.db"
    _make_company_profiles_db(str(tgt), has_uei=True)
    # target row must be empty for a non-fresh load; recreate target with no row
    con = sqlite3.connect(str(tgt))
    con.execute("DELETE FROM company_profiles")
    con.commit()
    con.close()

    plans = loader.load(str(src), _target_url(str(tgt)))
    cp = next(p for p in plans if p.name == "company_profiles")
    assert "uei" in cp.columns
    assert "uei" not in cp.dropped_source_only
    con = sqlite3.connect(str(tgt))
    try:
        assert con.execute("SELECT uei FROM company_profiles WHERE id=1").fetchone()[0] == "ABC123DEF456"
    finally:
        con.close()


def test_company_profiles_uei_dropped_when_target_lacks_column(tmp_path):
    """Pre-fix behavior this migration prevents: without company_profiles.uei in
    the target schema the loader drops it as source-only (identifier lost)."""
    src = tmp_path / "src.db"
    _make_company_profiles_db(str(src), has_uei=True, uei_value="ABC123DEF456")
    tgt = tmp_path / "tgt.db"
    _make_company_profiles_db(str(tgt), has_uei=False)
    con = sqlite3.connect(str(tgt))
    con.execute("DELETE FROM company_profiles")
    con.commit()
    con.close()

    plans = loader.load(str(src), _target_url(str(tgt)))
    cp = next(p for p in plans if p.name == "company_profiles")
    assert "uei" not in cp.columns
    assert cp.dropped_source_only == ["uei"]


def test_dry_run_writes_nothing(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    loader.load(src, _target_url(str(tgt)), dry_run=True)
    assert _count(str(tgt), "parent") == 0
    assert _count(str(tgt), "child") == 0


def test_nonempty_target_refused_without_fresh(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    loader.load(src, _target_url(str(tgt)))  # first load populates target
    with pytest.raises(loader.LoaderError, match="already contain rows"):
        loader.load(src, _target_url(str(tgt)))  # second load without --fresh


def test_fresh_reload_is_idempotent(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    loader.load(src, _target_url(str(tgt)))
    loader.load(src, _target_url(str(tgt)), fresh=True)  # re-run cleanly
    assert _count(str(tgt), "parent") == 2
    assert _count(str(tgt), "child") == 2


def test_row_count_mismatch_rolls_back(src, tmp_path, monkeypatch):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    real_build_plan = loader.build_plan

    def _inflate(*a, **k):
        plans = real_build_plan(*a, **k)
        plans[0].source_rows += 1  # force a verify mismatch
        return plans

    monkeypatch.setattr(loader, "build_plan", _inflate)
    with pytest.raises(loader.LoaderError, match="row-count verification failed"):
        loader.load(src, _target_url(str(tgt)))
    # Transaction rolled back: nothing committed.
    assert _count(str(tgt), "parent") == 0
    assert _count(str(tgt), "child") == 0


def test_insert_failure_rolls_back_all_tables(tmp_path):
    src = tmp_path / "snapshot.db"
    _make_source(str(src), child_val=None)  # NULL val will violate target NOT NULL
    tgt = tmp_path / "target.db"
    _make_target(str(tgt), child_val_notnull=True)
    with pytest.raises(Exception):  # noqa: B017 - DB IntegrityError bubbles up
        loader.load(str(src), _target_url(str(tgt)))
    # parent loaded earlier in the same tx must also be rolled back.
    assert _count(str(tgt), "parent") == 0


def test_source_snapshot_is_not_mutated(src, tmp_path):
    before = (_count(src, "parent"), _count(src, "child"), _count(src, "widget"))
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    loader.load(src, _target_url(str(tgt)))
    after = (_count(src, "parent"), _count(src, "child"), _count(src, "widget"))
    assert before == after == (2, 2, 1)


def test_missing_source_raises(tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    with pytest.raises(loader.LoaderError, match="source snapshot not found"):
        loader.load(str(tmp_path / "nope.db"), _target_url(str(tgt)))


def test_unknown_requested_table_raises(src, tmp_path):
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    with pytest.raises(loader.LoaderError, match="not present on both sides"):
        loader.load(src, _target_url(str(tgt)), only_tables={"nonexistent"})


def test_fresh_with_tables_is_rejected(src, tmp_path):
    # --fresh + --tables would CASCADE-truncate referencing tables outside the
    # subset that then never get reloaded (silent data loss) — must be refused
    # before touching either database.
    tgt = tmp_path / "target.db"
    _make_target(str(tgt))
    with pytest.raises(loader.LoaderError, match="cannot be combined with --tables"):
        loader.load(src, _target_url(str(tgt)), fresh=True, only_tables={"parent"})
    assert _count(str(tgt), "parent") == 0  # nothing mutated
