import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
tasks = Celery(
    "recompete",
    broker=_redis_url,
    backend=_redis_url,
)

tasks.conf.task_serializer = "json"
tasks.conf.task_acks_late = True
tasks.conf.task_reject_on_worker_lost = True

tasks.conf.beat_schedule = {
    "heartbeat-every-5-minutes": {
        "task": "tasks.heartbeat",
        "schedule": 300.0,
    },
    "check-beat-health-every-10-minutes": {
        "task": "tasks.check_beat_health",
        "schedule": 600.0,
    },
    "nightly-ingest-0200-utc": {
        "task": "tasks.run_ingest",
        "schedule": crontab(hour=2, minute=0),
    },
}

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    sentry_sdk.init(dsn=_sentry_dsn, integrations=[CeleryIntegration()], traces_sample_rate=0.0)

_BEAT_HEALTH_KEY = "beat:health"
_BEAT_HEALTH_TTL = 900  # 15 minutes in seconds
_BEAT_STALE_THRESHOLD = timedelta(minutes=15)
_QUALITY_THRESHOLD = 10


@tasks.task(name="tasks.send_email_task", bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to: str, subject: str, html_body: str, text_body: str = ""):
    from email_service import send_email
    try:
        result = send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
        if result is None:
            logger.warning("send_email_task: EMAIL_API_KEY not set, skipping send to %s", to)
        return result
    except Exception as exc:
        logger.error("send_email_task failed (to=%s): %s", to, exc)
        raise self.retry(exc=exc)


@tasks.task(name="tasks.heartbeat")
def heartbeat():
    """Write current UTC timestamp to beat:health Redis key with 15-min TTL."""
    import redis

    logger.info("Celery beat heartbeat")
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = redis.from_url(url)
        r.set(_BEAT_HEALTH_KEY, datetime.now(timezone.utc).isoformat(), ex=_BEAT_HEALTH_TTL)
    except Exception as exc:
        logger.error("Heartbeat failed to write beat:health to Redis: %s", exc)


@tasks.task(name="tasks.check_beat_health")
def check_beat_health():
    """Log ERROR if beat:health is missing or older than 15 minutes."""
    import redis

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = redis.from_url(url)
        raw = r.get(_BEAT_HEALTH_KEY)
        if raw is None:
            logger.error("Beat health check FAILED: beat:health key is missing from Redis")
            return
        ts = datetime.fromisoformat(raw.decode())
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        if age > _BEAT_STALE_THRESHOLD:
            logger.error(
                "Beat health check FAILED: last heartbeat was %s ago (threshold: 15 min)", age
            )
        else:
            logger.debug("Beat health OK — last heartbeat %s ago", age)
    except Exception as exc:
        logger.error("Beat health check error: %s", exc)


@tasks.task(name="tasks.run_ingest", bind=True)
def run_ingest(self):
    """Run SAM.gov ingest pipeline and log to celery_task_log."""
    from db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    task_id = self.request.id or "unknown"
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()

    with engine.begin() as conn:
        if is_pg:
            log_id = conn.execute(text("""
                INSERT INTO celery_task_log (task_name, status, started_at, result_json)
                VALUES (:task_name, :status, :started_at, :result_json)
                RETURNING id
            """), {
                "task_name": "run_ingest",
                "status": "RUNNING",
                "started_at": started_at,
                "result_json": json.dumps({"task_id": task_id}),
            }).scalar()
        else:
            result = conn.execute(text("""
                INSERT INTO celery_task_log (task_name, status, started_at, result_json)
                VALUES (:task_name, :status, :started_at, :result_json)
            """), {
                "task_name": "run_ingest",
                "status": "RUNNING",
                "started_at": started_at,
                "result_json": json.dumps({"task_id": task_id}),
            })
            log_id = result.lastrowid

    try:
        from janitorial_recompete_report import main
        main()
        duration = time.monotonic() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        with engine.connect() as conn:
            record_count = conn.execute(text("SELECT COUNT(*) FROM contracts")).scalar() or 0
        if record_count < _QUALITY_THRESHOLD:
            logger.error(
                "run_ingest: suspiciously low record count (%d) — possible silent failure or empty API response",
                record_count,
            )
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE celery_task_log
                SET status=:status, finished_at=:finished_at, result_json=:result_json
                WHERE id=:id
            """), {
                "status": "SUCCESS",
                "finished_at": finished_at,
                "result_json": json.dumps({"task_id": task_id, "result": "ok"}),
                "id": log_id,
            })
            conn.execute(text("""
                INSERT INTO ingest_log
                    (run_date, source, record_count, duration_seconds, status, error_message, created_at)
                VALUES (:run_date, :source, :record_count, :duration_seconds, :status, NULL, :created_at)
            """), {
                "run_date": finished_at[:10],
                "source": "usaspending",
                "record_count": record_count,
                "duration_seconds": duration,
                "status": "success",
                "created_at": finished_at,
            })
        return {"status": "SUCCESS", "task_id": task_id}
    except Exception as exc:
        logger.exception("run_ingest failed (task_id=%s)", task_id)
        duration = time.monotonic() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE celery_task_log
                SET status=:status, finished_at=:finished_at, result_json=:result_json
                WHERE id=:id
            """), {
                "status": "FAILURE",
                "finished_at": finished_at,
                "result_json": json.dumps({"task_id": task_id, "error": str(exc)}),
                "id": log_id,
            })
            conn.execute(text("""
                INSERT INTO ingest_log
                    (run_date, source, record_count, duration_seconds, status, error_message, created_at)
                VALUES (:run_date, :source, 0, :duration_seconds, :status, :error_message, :created_at)
            """), {
                "run_date": finished_at[:10],
                "source": "usaspending",
                "duration_seconds": duration,
                "status": "failure",
                "error_message": str(exc),
                "created_at": finished_at,
            })
        raise
