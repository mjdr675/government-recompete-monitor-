"""Regression: PostgreSQL ingest must not execute SQLite-only AUTOINCREMENT DDL.

The first post-cutover scheduled daily-ingest (2026-07-10 06:14 UTC) failed with
``psycopg2.errors.SyntaxError: syntax error at or near "AUTOINCREMENT"`` because
``save_snapshot() -> init_snapshots_table()`` ran a SQLite ``CREATE TABLE ...
id INTEGER PRIMARY KEY AUTOINCREMENT`` unconditionally; Postgres rejects it at
PARSE time even under ``IF NOT EXISTS``. ``init_changes_table()`` (reached via
change tracking) had the same defect.

On PostgreSQL the migrations own these tables, so the runtime helpers must NOT run
the SQLite CREATE. These tests exercise the Postgres branch hermetically (a fake
engine — no live Postgres) and confirm the SQLite path is unchanged.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import text

import db as db_module

ROOT = Path(__file__).resolve().parent.parent


# ── Hermetic Postgres branch: no SQLite CREATE, existence check, loud-if-absent ──
class _FakeResult:
    def __init__(self, val):
        self._val = val

    def scalar(self):
        return self._val


class _FakeConn:
    def __init__(self, exists, log):
        self._exists = exists
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, clause, *a, **k):
        self._log.append(str(clause))
        # to_regclass returns the regclass name when the table exists, else NULL.
        return _FakeResult("public.table" if self._exists else None)


class _FakeDialect:
    name = "postgresql"


class _FakePgEngine:
    """dialect=postgresql. begin() (write txn) must never be opened on the PG path;
    doing so would run the SQLite CREATE — so it raises to catch a regression."""

    def __init__(self, exists, log):
        self.dialect = _FakeDialect()
        self._exists = exists
        self._log = log

    def connect(self):
        return _FakeConn(self._exists, self._log)

    def begin(self):
        raise AssertionError(
            "PostgreSQL path opened a write transaction — it would run the SQLite "
            "AUTOINCREMENT CREATE (the exact ingest regression)"
        )


@pytest.mark.parametrize("fn", ["init_snapshots_table", "init_changes_table"])
def test_pg_branch_does_not_run_sqlite_autoincrement(monkeypatch, fn):
    log = []
    monkeypatch.setattr(
        db_module, "get_engine", lambda: _FakePgEngine(exists=True, log=log)
    )
    getattr(db_module, fn)()  # must not raise; must not open begin()/run CREATE
    joined = "\n".join(log)
    assert "AUTOINCREMENT" not in joined.upper(), f"{fn} ran SQLite AUTOINCREMENT on PG"
    assert "CREATE TABLE" not in joined.upper(), f"{fn} ran a CREATE TABLE on PG"
    assert "to_regclass" in joined, f"{fn} should verify the migrated table exists"


@pytest.mark.parametrize("fn", ["init_snapshots_table", "init_changes_table"])
def test_pg_branch_fails_loud_when_migrated_table_absent(monkeypatch, fn):
    log = []
    monkeypatch.setattr(
        db_module, "get_engine", lambda: _FakePgEngine(exists=False, log=log)
    )
    with pytest.raises(RuntimeError, match="missing on PostgreSQL"):
        getattr(db_module, fn)()


# ── SQLite path unchanged: create + insert + idempotent ──────────────────────
@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)
    yield
    db_module._cached_engine.cache_clear()


def _tables(engine):
    with engine.connect() as c:
        return {
            r[0]
            for r in c.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def test_sqlite_init_snapshots_creates_table_and_is_idempotent(sqlite_db):
    db_module.init_snapshots_table()
    db_module.init_snapshots_table()  # rerun must not raise
    assert "contract_snapshots" in _tables(db_module.get_engine())


def test_sqlite_save_snapshot_inserts_and_dedupes(sqlite_db):
    rows = [
        {"internal_id": "S1", "vendor": "Acme", "agency": "GSA"},
        {"internal_id": "S2", "vendor": "Beta", "agency": "VA"},
    ]
    db_module.save_snapshot("2026-07-10", rows)
    db_module.save_snapshot("2026-07-10", rows)  # rerun same run_date: no duplicates
    with db_module.get_engine().connect() as c:
        n = c.execute(
            text("SELECT COUNT(*) FROM contract_snapshots WHERE run_date='2026-07-10'")
        ).scalar()
    assert n == 2, f"expected 2 deduped snapshot rows, got {n}"


def test_sqlite_init_changes_creates_table_and_insert_works(sqlite_db):
    db_module.init_changes_table()
    db_module.insert_change("2026-07-10", "NEW", "X1", description="added")
    with db_module.get_engine().connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM changes")).scalar()
    assert "changes" in _tables(db_module.get_engine())
    assert n == 1


# ── Static guard: ingest-reachable ensure helpers keep SQLite-only DDL out of the
#    Postgres path. Precise, curated list — no global ban on SQLite support. ────
def _func_body(src: str, name: str) -> str:
    m = re.search(
        rf"^def {re.escape(name)}\(.*?\):\n(.*?)(?=\n def |\ndef |\Z)", src, re.S | re.M
    )
    assert m, f"function {name} not found in db.py"
    return m.group(1)


def test_ingest_reachable_init_helpers_guard_sqlite_autoincrement():
    """Every ensure-table helper reachable on the PostgreSQL ingest path that still
    contains SQLite AUTOINCREMENT must guard it behind a Postgres check that comes
    BEFORE the AUTOINCREMENT (early-return / is_pg branch), so Postgres never parses
    it. db.py's SQLite-only init_db block is reached only via `if database_url:`
    early-return; that guard token is accepted too. Non-ingest helpers (init_demo_
    table, init_early_access_table, init_saved_searches_table) are intentionally out
    of scope for this ingest fix."""
    src = (ROOT / "db.py").read_text()
    ingest_reachable = [
        "init_snapshots_table",
        "init_changes_table",
        "init_field_changes_table",
        "init_lead_intelligence_tables",
        "init_db",
    ]
    guard_tokens = ('dialect.name == "postgresql"', "is_pg", "if database_url")
    offenders = {}
    for name in ingest_reachable:
        body = _func_body(src, name)
        up = body.upper()
        if "AUTOINCREMENT" not in up:
            continue
        first_ai = up.index("AUTOINCREMENT")
        guard_positions = [body.index(t) for t in guard_tokens if t in body]
        if not guard_positions or min(guard_positions) > first_ai:
            offenders[name] = "AUTOINCREMENT not preceded by a Postgres guard"
    assert not offenders, (
        f"unguarded SQLite AUTOINCREMENT on PG ingest path: {offenders}"
    )
