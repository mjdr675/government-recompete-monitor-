"""Regression: change detection must run on PostgreSQL, not just SQLite.

The 2026-07-11 06:12 UTC scheduled ingest got past the AUTOINCREMENT fix
(PR #61) and then failed in change detection with
``'psycopg2.extensions.connection' object has no attribute 'execute'``:
``detect_changes()`` (change_detector.py) and ``detect_field_changes()``
(update_detector.py) called ``.execute()`` on the raw DBAPI connection returned
by ``db.get_connection()`` — a sqlite3-only shortcut that psycopg2 connections
lack. Both now use the shared SQLAlchemy engine + ``text()`` + bound params.

These tests preserve the change *semantics* on SQLite, prove the write is atomic
(no partial rows on failure), and statically forbid ingest-reachable detector
modules from acquiring a raw db connection. A PostgreSQL-gated test runs the real
path when DATABASE_URL is set (skipped locally, exercised in a PG CI).
"""

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import text

import change_detector
import db as db_module
import update_detector

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)
    yield
    db_module._cached_engine.cache_clear()


def _snap(run_date, rows):
    db_module.save_snapshot(run_date, rows)


def _changes(run_date):
    with db_module.get_engine().connect() as c:
        return sorted(
            tuple(r)
            for r in c.execute(
                text(
                    "SELECT change_type, internal_id, old_priority, new_priority "
                    "FROM changes WHERE run_date = :d"
                ),
                {"d": run_date},
            )
        )


# ── change semantics (SQLite) ────────────────────────────────────────────────
def test_identical_snapshots_produce_no_change(sqlite_db):
    _snap("2026-07-10", [{"internal_id": "A", "priority": "HIGH"}])
    _snap("2026-07-11", [{"internal_id": "A", "priority": "HIGH"}])
    change_detector.detect_changes("2026-07-11")
    assert _changes("2026-07-11") == []


def test_new_removed_and_priority_changes(sqlite_db):
    _snap(
        "2026-07-10",
        [
            {"internal_id": "A", "priority": "LOW"},
            {"internal_id": "B", "priority": "MEDIUM"},
            {"internal_id": "C", "priority": "HIGH"},
        ],
    )
    _snap(
        "2026-07-11",
        [
            {"internal_id": "A", "priority": "HIGH"},  # UPGRADE
            {"internal_id": "B", "priority": "MEDIUM"},  # unchanged
            {"internal_id": "D", "priority": "LOW"},  # NEW ; C REMOVED
        ],
    )
    change_detector.detect_changes("2026-07-11")
    assert _changes("2026-07-11") == [
        ("NEW", "D", None, None),
        ("REMOVED", "C", None, None),
        ("UPGRADE", "A", "LOW", "HIGH"),
    ]


def test_records_persisted_in_deterministic_id_order(sqlite_db):
    # IDs are deliberately NOT in sorted order in the snapshots, so a pass here
    # cannot come from set iteration accidentally yielding sorted order — the
    # detector must sort internal_ids within each category before persisting.
    _snap(
        "2026-07-10",
        [
            {"internal_id": "keep_z", "priority": "LOW"},
            {"internal_id": "keep_a", "priority": "LOW"},
            {"internal_id": "gone_m", "priority": "HIGH"},
            {"internal_id": "gone_b", "priority": "HIGH"},
        ],
    )
    _snap(
        "2026-07-11",
        [
            {"internal_id": "keep_z", "priority": "HIGH"},  # UPGRADE
            {"internal_id": "keep_a", "priority": "HIGH"},  # UPGRADE
            {"internal_id": "new_y", "priority": "LOW"},  # NEW
            {"internal_id": "new_c", "priority": "LOW"},  # NEW ; gone_* REMOVED
        ],
    )
    change_detector.detect_changes("2026-07-11")
    # `changes.id` is autoincrement, so ORDER BY id reflects insertion order.
    with db_module.get_engine().connect() as c:
        rows = [
            tuple(r)
            for r in c.execute(
                text(
                    "SELECT change_type, internal_id FROM changes "
                    "WHERE run_date = '2026-07-11' ORDER BY id"
                )
            )
        ]
    by_cat = {}
    for change_type, internal_id in rows:
        by_cat.setdefault(change_type, []).append(internal_id)
    # each category's persisted ids are in sorted (deterministic) internal_id order
    assert by_cat["NEW"] == ["new_c", "new_y"]
    assert by_cat["REMOVED"] == ["gone_b", "gone_m"]
    assert by_cat["UPGRADE"] == ["keep_a", "keep_z"]
    for cat, ids in by_cat.items():
        assert ids == sorted(ids), f"{cat} not persisted in sorted id order: {ids}"


def test_downgrade_detected(sqlite_db):
    _snap("2026-07-10", [{"internal_id": "A", "priority": "CRITICAL"}])
    _snap("2026-07-11", [{"internal_id": "A", "priority": "LOW"}])
    change_detector.detect_changes("2026-07-11")
    assert _changes("2026-07-11") == [("DOWNGRADE", "A", "CRITICAL", "LOW")]


def test_null_priority_transitions(sqlite_db):
    # value -> null and null -> value both count as a change (ranks default to 0).
    _snap(
        "2026-07-10", [{"internal_id": "A", "priority": "HIGH"}, {"internal_id": "B"}]
    )
    _snap(
        "2026-07-11", [{"internal_id": "A"}, {"internal_id": "B", "priority": "MEDIUM"}]
    )
    change_detector.detect_changes("2026-07-11")
    got = {(t, i) for (t, i, _o, _n) in _changes("2026-07-11")}
    assert ("DOWNGRADE", "A") in got  # HIGH -> None
    assert ("UPGRADE", "B") in got  # None -> MEDIUM


def test_missing_prior_snapshot_is_noop(sqlite_db):
    _snap("2026-07-11", [{"internal_id": "A", "priority": "HIGH"}])
    change_detector.detect_changes("2026-07-11")  # only one snapshot date
    assert _changes("2026-07-11") == []


def test_rerun_is_idempotent(sqlite_db):
    _snap("2026-07-10", [{"internal_id": "A", "priority": "LOW"}])
    _snap("2026-07-11", [{"internal_id": "A", "priority": "HIGH"}])
    change_detector.detect_changes("2026-07-11")
    first = _changes("2026-07-11")
    change_detector.detect_changes("2026-07-11")  # rerun
    assert _changes("2026-07-11") == first
    with db_module.get_engine().connect() as c:
        n = c.execute(
            text("SELECT COUNT(*) FROM changes WHERE run_date='2026-07-11'")
        ).scalar()
    assert n == len(first)


def test_write_is_atomic_no_partial_rows_on_failure(sqlite_db, monkeypatch):
    # Seed a prior (committed) change set, then make a second run fail mid-write and
    # assert nothing partial is left (the atomic clear+insert rolls back entirely).
    _snap(
        "2026-07-10",
        [
            {"internal_id": "A", "priority": "LOW"},
            {"internal_id": "B", "priority": "LOW"},
        ],
    )
    _snap(
        "2026-07-11",
        [
            {"internal_id": "A", "priority": "HIGH"},
            {"internal_id": "B", "priority": "HIGH"},
        ],
    )
    change_detector.detect_changes("2026-07-11")
    before = _changes("2026-07-11")
    assert before  # non-empty

    real_text = change_detector.text

    def boom(sql):
        # fail the write transaction on the INSERT into `changes`
        if "INSERT INTO changes" in sql:
            raise RuntimeError("injected write failure")
        return real_text(sql)

    monkeypatch.setattr(change_detector, "text", boom)
    with pytest.raises(RuntimeError, match="injected write failure"):
        change_detector.detect_changes("2026-07-11")
    # (Do NOT monkeypatch.undo() here — that would also revert the fixture's DB_PATH.
    # pytest auto-undoes at teardown; _changes() uses its own module-level text().)
    # The failed run's transaction rolled back → the prior committed set is intact,
    # never a half-cleared / half-inserted state.
    assert _changes("2026-07-11") == before


def test_detect_field_changes_runs_on_sqlite(sqlite_db):
    # Regression for the same raw-connection bug in update_detector.py.
    _snap("2026-07-10", [{"internal_id": "A", "vendor": "Acme", "agency": "GSA"}])
    _snap("2026-07-11", [{"internal_id": "A", "vendor": "Acme Corp", "agency": "GSA"}])
    n = update_detector.detect_field_changes("2026-07-11")
    assert isinstance(n, int) and n >= 0  # runs without raw-connection AttributeError


# ── PostgreSQL-gated (skipped without DATABASE_URL; exercised in a PG CI) ─────
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="PostgreSQL runtime test — set DATABASE_URL to a DISPOSABLE test database",
)
def test_detect_changes_runs_on_postgres():
    db_module._cached_engine.cache_clear()
    assert db_module.get_engine().dialect.name == "postgresql"
    # Must not raise the raw-connection AttributeError; a no-op is acceptable.
    change_detector.detect_changes("__pg_probe__")


# ── static guard: ingest-reachable detectors must not acquire a raw db connection
def _raw_connection_acquisitions(path: Path):
    """AST: calls to db.get_connection()/connect() (the raw-DBAPI helpers) — NOT
    engine.connect()/get_engine().connect(), which return a SQLAlchemy Connection
    that legitimately supports .execute()."""
    tree = ast.parse(path.read_text())
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id in ("connect", "get_connection"):
            hits.append(f.id)
        elif (
            isinstance(f, ast.Attribute)
            and f.attr in ("connect", "get_connection")
            and isinstance(f.value, ast.Name)
            and f.value.id == "db"
        ):
            hits.append("db." + f.attr)
    return hits


@pytest.mark.parametrize("module", ["change_detector.py", "update_detector.py"])
def test_detectors_do_not_acquire_raw_db_connection(module):
    """These ingest-reachable modules must go through the shared SQLAlchemy engine
    (get_engine()), never db.get_connection()/connect() (raw psycopg2 has no
    .execute()). Excludes engine.connect(), which is a SQLAlchemy Connection."""
    hits = _raw_connection_acquisitions(ROOT / module)
    assert not hits, f"{module} acquires a raw db connection (use get_engine()): {hits}"
