"""O5 / Gate 3 groundwork — Postgres engine selection, Celery/beat wiring, and
the (intentionally inactive) worker/beat railway.toml draft.

All hermetic: no live Postgres, Redis, or Railway. Engine tests assert dialect
selection without connecting; the psycopg2 path is exercised with a fake module;
the railway.toml test is a static parse. These lock in that the app already
supports a shared Postgres and that worker/beat are drafted but NOT yet active
(so current SQLite prod behavior is preserved).
"""
import sqlite3
import sys
import tomllib
import types
from pathlib import Path

import pytest

import db
import tasks as tasks_mod

ROOT = Path(__file__).resolve().parent.parent
RAILWAY_TOML = ROOT / "railway.toml"


# ── DB engine selection (DATABASE_URL → Postgres, else SQLite) ────────────────
def test_get_engine_selects_postgres_when_database_url_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/testdb")
    assert db.get_engine().dialect.name == "postgresql"


def test_get_engine_defaults_to_sqlite_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.get_engine().dialect.name == "sqlite"


def test_get_connection_uses_sqlite_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    conn = db.get_connection()
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_get_connection_selects_psycopg2_when_database_url_set(monkeypatch):
    # Exercise the Postgres branch without a real server: inject a fake psycopg2.
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/d")
    sentinel = object()
    calls = {}
    fake = types.ModuleType("psycopg2")
    fake.connect = lambda url: (calls.__setitem__("url", url), sentinel)[1]
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    got = db.get_connection()
    assert got is sentinel
    assert calls["url"].startswith("postgresql://")


# ── Celery / beat wiring (broker from REDIS_URL, required jobs scheduled) ──────
def test_celery_broker_and_backend_use_redis_url():
    app = tasks_mod.tasks
    assert app.conf.broker_url == tasks_mod._redis_url
    assert app.conf.result_backend == tasks_mod._redis_url
    assert app.conf.broker_url.startswith("redis://")


def test_beat_schedule_has_required_automation_jobs():
    sched = tasks_mod.tasks.conf.beat_schedule
    required = {
        "watchlist-alerts-0700-utc": "tasks.check_watchlist_alerts",
        "trial-emails-0900-utc": "tasks.send_trial_emails",
        "heartbeat-every-5-minutes": "tasks.heartbeat",
        "check-beat-health-every-10-minutes": "tasks.check_beat_health",
    }
    assert set(required) <= set(sched), f"missing beat jobs: {set(required) - set(sched)}"
    for key, task_name in required.items():
        assert sched[key]["task"] == task_name


# ── railway.toml: worker/beat drafted but INACTIVE (SQLite behavior preserved) ─
def test_railway_worker_beat_are_drafted_but_not_active():
    with open(RAILWAY_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    active = {s.get("name") for s in cfg.get("services", [])}
    # Must NOT be active yet — activating before Postgres is provisioned would run
    # scheduled jobs against empty per-service volumes.
    assert "worker" not in active and "beat" not in active
    assert {"web", "daily-ingest"} <= active

    raw = RAILWAY_TOML.read_text()
    # …but the cutover draft (commented) must be present and clearly gated.
    assert "celery -A tasks worker" in raw
    assert "celery -A tasks beat" in raw
    assert "DO NOT UNCOMMENT" in raw
    assert "O5_POSTGRES_MIGRATION_PLAN.md" in raw
