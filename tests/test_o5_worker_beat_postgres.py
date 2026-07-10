"""O5 / Gate 3 — Postgres engine selection, Celery/beat wiring, and the worker/beat
railway.toml config-as-code (post-cutover: web is live on PostgreSQL).

All hermetic: no live Postgres, Redis, or Railway. Engine tests assert dialect
selection without connecting; the psycopg2 path is exercised with a fake module;
the railway.toml tests are static parses. These lock in that the app runs on a
shared Postgres, that worker/beat are wired to it (but only *created* via the
human-only activation runbook), that run_ingest stays off the beat schedule, and
that the task paths are Postgres-safe.
"""

import sqlite3
import sys
import tomllib
import types
from pathlib import Path

import db
import tasks as tasks_mod

ROOT = Path(__file__).resolve().parent.parent
RAILWAY_TOML = ROOT / "railway.toml"


# ── DB engine selection (DATABASE_URL → Postgres, else SQLite) ────────────────
def test_get_engine_selects_postgres_when_database_url_set(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/testdb"
    )
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
    assert set(required) <= set(sched), (
        f"missing beat jobs: {set(required) - set(sched)}"
    )
    for key, task_name in required.items():
        assert sched[key]["task"] == task_name


# ── railway.toml: worker/beat ACTIVE and wired to shared Postgres + Redis ─────
def test_railway_worker_beat_active_and_wired_to_shared_postgres():
    with open(RAILWAY_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    services = {s.get("name"): s for s in cfg.get("services", [])}
    # worker + beat are now activated alongside web + daily-ingest.
    assert {"web", "daily-ingest", "worker", "beat"} <= set(services)
    # They run the Procfile commands.
    assert "celery -A tasks worker" in services["worker"]["deploy"]["startCommand"]
    assert "celery -A tasks beat" in services["beat"]["deploy"]["startCommand"]
    # web/worker/beat reference the SHARED Postgres + Redis (not per-service state).
    for name in ("web", "worker", "beat"):
        vars_ = services[name].get("variables", {})
        assert vars_.get("DATABASE_URL") == "${{Postgres.DATABASE_URL}}", name
        assert vars_.get("REDIS_URL") == "${{Redis.REDIS_URL}}", name

    raw = RAILWAY_TOML.read_text()
    # The activation runbook must remain referenced, and the (post-cutover)
    # ACTIVATION GATE must be present — but the obsolete pre-cutover
    # "DO NOT MERGE OR DEPLOY" prohibition (which assumed web was still on SQLite)
    # must be gone now that web is live on PostgreSQL.
    assert "DEPLOYMENT.md" in raw or "O5_POSTGRES_MIGRATION_PLAN.md" in raw
    assert "ACTIVATION GATE" in raw
    assert "DO NOT MERGE OR DEPLOY" not in raw


def test_beat_is_single_replica_and_run_ingest_excluded():
    """Beat uses a file-based PersistentScheduler, so exactly ONE beat replica may
    run or crontab jobs fire multiple times. railway.toml must not scale beat >1,
    and the single-replica requirement must be documented. run_ingest must never be
    on the beat schedule (the daily-ingest cron is the sole ingest owner)."""
    with open(RAILWAY_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    services = {s.get("name"): s for s in cfg.get("services", [])}
    beat = services["beat"]
    # No replica scaling on beat (Railway defaults to 1; >1 duplicates schedules).
    replicas = beat.get("deploy", {}).get("numReplicas")
    assert replicas in (None, 1), f"beat must run exactly one replica, got {replicas}"
    # Single-replica requirement is documented somewhere in the config/runbook.
    combined = (
        RAILWAY_TOML.read_text() + (ROOT / "docs" / "DEPLOYMENT.md").read_text()
    ).lower()
    assert (
        "one replica" in combined
        or "single replica" in combined
        or "exactly one" in combined
    )
    # run_ingest is registered but NOT scheduled by beat.
    scheduled = {v["task"] for v in tasks_mod.tasks.conf.beat_schedule.values()}
    assert "tasks.run_ingest" not in scheduled, (
        "run_ingest must not be on the beat schedule"
    )
    assert "tasks.run_ingest" in tasks_mod.tasks.tasks  # registered for admin trigger


def test_worker_beat_task_paths_have_no_sqlite_only_sql():
    """Every task reachable via worker/beat must be Postgres-safe: no ? placeholders,
    no INSERT OR IGNORE/REPLACE, no fts5 MATCH — they must go through the shared
    dialect-safe db engine (text() + :named params)."""
    import re

    src = (ROOT / "tasks.py").read_text()
    offenders = []
    if re.search(r"INSERT\s+OR\s+(IGNORE|REPLACE)", src, re.I):
        offenders.append("INSERT OR IGNORE/REPLACE")
    if re.search(r"execute\([^)]*\?[,)]|VALUES\s*\(\s*\?", src):
        offenders.append("raw ? placeholder")
    if re.search(r"\bMATCH\s+:|contracts_fts\b", src):
        offenders.append("fts5 MATCH")
    assert not offenders, f"SQLite-only SQL in worker/beat task paths: {offenders}"


def test_worker_beat_tasks_are_discoverable():
    """Task discovery: worker/beat resolve the intended tasks by name."""
    registered = tasks_mod.tasks.tasks
    for name in (
        "tasks.send_email_task",
        "tasks.heartbeat",
        "tasks.check_beat_health",
        "tasks.check_watchlist_alerts",
        "tasks.send_trial_emails",
        "tasks.run_ingest",
    ):
        assert name in registered, f"task not registered/discoverable: {name}"


def test_production_status_docs_identify_postgres():
    """Status docs must reflect the completed cutover — web on PostgreSQL, not the
    stale 'web still runs SQLite'."""
    plan = (ROOT / "docs" / "O5_POSTGRES_MIGRATION_PLAN.md").read_text()
    assert "web still runs SQLite" not in plan
    assert "PostgreSQL" in plan


def test_config_performs_no_automatic_railway_action():
    """The repo config must not shell out to the Railway CLI/API to create or enable
    services — activation stays a human dashboard step."""
    raw = RAILWAY_TOML.read_text()
    assert "railway up" not in raw
    assert "railway service" not in raw
    assert "railway variables" not in raw
