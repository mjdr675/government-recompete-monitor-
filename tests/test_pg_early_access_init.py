"""Regression: init_early_access_table() must be PostgreSQL-safe.

save_early_access() (reached from the early-access web route, app.py:1559) calls
init_early_access_table(), which ran a SQLite `CREATE TABLE IF NOT EXISTS
early_access (id INTEGER PRIMARY KEY AUTOINCREMENT, ...)` unconditionally.
AUTOINCREMENT is SQLite-only and Postgres rejects it at PARSE time (even under
IF NOT EXISTS). On Postgres the migrations own early_access (001_initial_pg.sql),
so the runtime helper must NOT run the SQLite CREATE — it does a read-only
to_regclass check (bound param) and raises if the migrated relation is absent.

Only init_early_access_table() is in scope; the dead-code demo / saved-search /
legacy-watchlist initializers are intentionally left untouched (asserted below).
"""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text

import db as db_module

ROOT = Path(__file__).resolve().parent.parent


def _is_postgres_url(url):
    """True only for a PostgreSQL SQLAlchemy URL (canonical or driver-qualified) —
    e.g. postgresql://, postgres://, postgresql+psycopg2://. Blank/unset/malformed
    or non-Postgres schemes (sqlite://, mysql://) are False. Parses the scheme
    rather than substring-matching."""
    if not url or not url.strip():
        return False
    try:
        scheme = urlsplit(url.strip()).scheme.lower()
    except ValueError:
        return False
    return scheme.split("+", 1)[0] in ("postgresql", "postgres")


# ── Hermetic Postgres branch: no SQLite CREATE, bound to_regclass, loud-if-absent ─
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

    def execute(self, clause, params=None):
        self._log.append((str(clause), params))
        return _FakeResult("public.early_access" if self._exists else None)


class _FakeDialect:
    name = "postgresql"


class _FakePgEngine:
    """dialect=postgresql. begin() (write txn) must never open on the PG path —
    that would run the SQLite AUTOINCREMENT CREATE — so it raises to catch a regression."""

    def __init__(self, exists, log):
        self.dialect = _FakeDialect()
        self._exists = exists
        self._log = log

    def connect(self):
        return _FakeConn(self._exists, self._log)

    def begin(self):
        raise AssertionError(
            "PostgreSQL path opened a write transaction (would run the SQLite CREATE)"
        )


def test_pg_branch_checks_early_access_and_runs_no_sqlite_ddl(monkeypatch):
    log = []
    monkeypatch.setattr(
        db_module, "get_engine", lambda: _FakePgEngine(exists=True, log=log)
    )
    db_module.init_early_access_table()  # must not raise / open begin()
    sql = "\n".join(s for s, _p in log)
    params = [p for _s, p in log]
    assert "AUTOINCREMENT" not in sql.upper()
    assert "CREATE TABLE" not in sql.upper()
    assert "to_regclass" in sql
    # checks exactly the early_access relation, via a bound parameter
    assert {"relname": "public.early_access"} in params


def test_pg_branch_raises_clear_error_when_early_access_absent(monkeypatch):
    monkeypatch.setattr(
        db_module, "get_engine", lambda: _FakePgEngine(exists=False, log=[])
    )
    with pytest.raises(RuntimeError, match="early_access is missing on PostgreSQL"):
        db_module.init_early_access_table()


# ── SQLite path unchanged ─────────────────────────────────────────────────────
@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)
    yield
    db_module._cached_engine.cache_clear()


def test_sqlite_init_creates_early_access_and_is_idempotent(sqlite_db):
    db_module.init_early_access_table()
    db_module.init_early_access_table()  # rerun must not raise
    with db_module.get_engine().connect() as c:
        assert (
            c.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='early_access'"
                )
            ).scalar()
            == "early_access"
        )


def test_sqlite_save_early_access_persists_and_upserts(sqlite_db):
    db_module.save_early_access("a@b.com", hubspot_contact_id="X1")
    db_module.save_early_access(
        "a@b.com", hubspot_contact_id="X2"
    )  # ON CONFLICT(email)
    with db_module.get_engine().connect() as c:
        rows = c.execute(
            text("SELECT email, hubspot_contact_id FROM early_access")
        ).fetchall()
    assert [tuple(r) for r in rows] == [("a@b.com", "X2")]  # single upserted row


# ── PostgreSQL-gated (skipped without DATABASE_URL) ──────────────────────────
@pytest.mark.parametrize(
    "url,expected",
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("postgresql://u:p@h:5432/d", True),
        ("postgres://u:p@h:5432/d", True),
        ("postgresql+psycopg2://u:p@h:5432/d", True),
        ("sqlite:///tmp/x.db", False),
        ("mysql://u:p@h/d", False),
        ("not-a-url", False),
    ],
)
def test_is_postgres_url_gate(url, expected):
    assert _is_postgres_url(url) is expected


@pytest.mark.skipif(
    not _is_postgres_url(os.environ.get("DATABASE_URL")),
    reason="PostgreSQL runtime test — set DATABASE_URL to a DISPOSABLE PostgreSQL database",
)
def test_init_early_access_runs_on_postgres():
    db_module._cached_engine.cache_clear()
    assert db_module.get_engine().dialect.name == "postgresql"
    db_module.init_early_access_table()  # must not raise the AUTOINCREMENT/DDL error


# ── static guard + scope confinement ─────────────────────────────────────────
def _func_body(src, name):
    m = re.search(
        rf"^def {re.escape(name)}\(.*?\):\n(.*?)(?=\n def |\ndef |\Z)", src, re.S | re.M
    )
    assert m, f"{name} not found in db.py"
    return m.group(1)


def test_init_early_access_guards_sqlite_ddl_behind_postgres_check():
    body = _func_body((ROOT / "db.py").read_text(), "init_early_access_table")
    assert "AUTOINCREMENT" in body.upper(), "SQLite branch DDL should still exist"
    guard = body.index('dialect.name == "postgresql"')
    assert guard < body.upper().index("AUTOINCREMENT"), (
        "AUTOINCREMENT not guarded behind the Postgres check"
    )
    # no improvised Postgres schema
    assert "SERIAL" not in body.upper()
    assert "IDENTITY" not in body.upper()


def test_out_of_scope_initializers_left_untouched():
    """The dead-code demo / saved-search / legacy-watchlist initializers must stay
    unguarded: each still runs its SQLite CREATE and did NOT gain the early_access
    Postgres guard. Asserted via to_regclass/dialect-guard absence (robust; note
    init_watchlist_table uses a TEXT primary key, not AUTOINCREMENT)."""
    src = (ROOT / "db.py").read_text()
    out_of_scope = (
        "init_demo_table",
        "init_saved_searches_table",
        "init_watchlist_table",
    )
    for name in out_of_scope:
        body = _func_body(src, name)
        assert "CREATE TABLE" in body.upper(), f"{name} SQLite DDL unexpectedly changed"
        assert "to_regclass" not in body, f"{name} gained the guard (out of scope)"
        assert 'dialect.name == "postgresql"' not in body, f"{name} gained a PG guard"
    # init_early_access_table is the ONLY one of these four with the Postgres guard
    guarded = [
        name
        for name in out_of_scope + ("init_early_access_table",)
        if "to_regclass" in _func_body(src, name)
    ]
    assert guarded == ["init_early_access_table"], f"unexpected guarded set: {guarded}"
