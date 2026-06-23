import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import sentry_sdk
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_json_logging() -> None:
    formatter = _JsonFormatter()
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))
    for handler in root.handlers:
        handler.setFormatter(formatter)


_configure_json_logging()

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
    "watchlist-alerts-0700-utc": {
        "task": "tasks.check_watchlist_alerts",
        "schedule": crontab(hour=7, minute=0),
    },
    "trial-emails-0900-utc": {
        "task": "tasks.send_trial_emails",
        "schedule": crontab(hour=9, minute=0),
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
_BEAT_ALERT_KEY = "beat:alert_sent"
_BEAT_ALERT_TTL = 3600  # 1 hour dedup window in seconds
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
        sentry_sdk.capture_exception(exc)
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


def _send_beat_alert(r, last_seen_str: str) -> None:
    """Enqueue a beat-stale admin email, deduplicated to once per hour."""
    admin_email = os.environ.get("ADMIN_EMAIL", "")
    if not admin_email:
        return
    if r.get(_BEAT_ALERT_KEY):
        return
    r.set(_BEAT_ALERT_KEY, "1", ex=_BEAT_ALERT_TTL)
    send_email_task.delay(
        to=admin_email,
        subject="[Gov Recompete Monitor] Beat scheduler may be down",
        html_body=(
            f"<p>The Celery beat scheduler has not checked in for over 20 minutes. "
            f"Last seen: {last_seen_str}. Check Railway logs immediately.</p>"
        ),
        text_body=f"Beat scheduler stale. Last seen: {last_seen_str}. Check Railway logs.",
    )


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
            _send_beat_alert(r, "unknown (key missing)")
            return
        ts = datetime.fromisoformat(raw.decode())
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        if age > _BEAT_STALE_THRESHOLD:
            logger.error(
                "Beat health check FAILED: last heartbeat was %s ago (threshold: 15 min)", age
            )
            _send_beat_alert(r, raw.decode())
        else:
            logger.debug("Beat health OK — last heartbeat %s ago", age)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
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
        sentry_sdk.capture_exception(exc)
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


@tasks.task(name="tasks.check_watchlist_alerts")
def check_watchlist_alerts():
    """Send expiry alert emails for watchlisted contracts; deduplicate via alert_log."""
    from db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    app_url = os.environ.get("APP_URL", "https://govrecompete.com")
    now = datetime.now(timezone.utc).isoformat()

    with engine.connect() as conn:
        users = conn.execute(text("""
            SELECT u.id, u.email, COALESCE(ap.expiry_days, 30) AS expiry_days
            FROM users u
            LEFT JOIN alert_preferences ap ON ap.user_id = u.id
            WHERE u.is_active = 1
              AND (ap.enabled IS NULL OR ap.enabled = 1)
        """)).mappings().fetchall()

    for user in users:
        user_id = user["id"]
        user_email = user["email"]
        expiry_days = user["expiry_days"]

        with engine.connect() as conn:
            contracts = conn.execute(text("""
                SELECT c.internal_id, c.vendor, c.agency, c.value, c.days_remaining
                FROM user_watchlist w
                JOIN contracts c ON c.internal_id = w.internal_id
                WHERE w.user_id = :uid
                  AND c.days_remaining IS NOT NULL
                  AND c.days_remaining >= 0
                  AND c.days_remaining <= :days
                  AND c.internal_id NOT IN (
                      SELECT internal_id FROM alert_log
                      WHERE user_id = :uid AND alert_type = 'expiry'
                  )
                ORDER BY c.days_remaining ASC
            """), {"uid": user_id, "days": expiry_days}).mappings().fetchall()

        if not contracts:
            continue

        try:
            from flask import Flask
            _app = Flask(__name__, template_folder="templates")
            with _app.app_context():
                from flask import render_template as _render
                html_body = _render(
                    "email/watchlist_alert.html",
                    user_email=user_email,
                    contracts=contracts,
                    expiry_days=expiry_days,
                    app_url=app_url,
                )
                text_body = _render(
                    "email/watchlist_alert.txt",
                    user_email=user_email,
                    contracts=contracts,
                    expiry_days=expiry_days,
                    app_url=app_url,
                )
            send_email_task.delay(
                to=user_email,
                subject=f"Watchlist Alert: {len(contracts)} contract(s) expiring soon",
                html_body=html_body,
                text_body=text_body,
            )
            with engine.begin() as conn:
                for c in contracts:
                    try:
                        conn.execute(text("""
                            INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)
                            VALUES (:uid, :iid, 'expiry', :now)
                        """), {"uid": user_id, "iid": c["internal_id"], "now": now})
                    except Exception:
                        pass  # already logged (unique constraint)
            logger.info(
                "check_watchlist_alerts: sent %d alerts to %s", len(contracts), user_email
            )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            logger.error(
                "check_watchlist_alerts: failed for user %d (%s): %s", user_id, user_email, exc
            )


@tasks.task(name="tasks.send_trial_emails")
def send_trial_emails():
    """Send day-3, day-10, and day-14 trial cadence emails; deduplicate via alert_log."""
    from db import get_engine
    from sqlalchemy import text

    engine = get_engine()
    app_url = os.environ.get("APP_URL", "https://govrecompete.com")
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    _STAGES = [
        # (alert_type, days_remaining_min, days_remaining_max, template_base, subject)
        ("trial_day3",  10, 12, "trial_day3",  "Making the most of your Gov Recompete Monitor trial"),
        ("trial_day10",  3,  5, "trial_day10", "Your Gov Recompete Monitor trial ends in 4 days"),
        ("trial_day14", -1,  1, "trial_day14", "Your Gov Recompete Monitor trial has ended"),
    ]

    with engine.connect() as conn:
        users = conn.execute(text("""
            SELECT id, email, trial_ends_at
            FROM users
            WHERE is_active = 1
              AND subscription_status != 'active'
              AND trial_ends_at IS NOT NULL
        """)).mappings().fetchall()

    for user in users:
        user_id = user["id"]
        user_email = user["email"]
        trial_end_str = user["trial_ends_at"]
        try:
            trial_end = datetime.fromisoformat(trial_end_str)
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        days_remaining = (trial_end - now).days
        trial_ends_date = trial_end.strftime("%B %d, %Y")

        for alert_type, min_days, max_days, template_base, subject in _STAGES:
            if not (min_days <= days_remaining <= max_days):
                continue
            with engine.connect() as conn:
                already_sent = conn.execute(text("""
                    SELECT 1 FROM alert_log
                    WHERE user_id = :uid AND alert_type = :at
                """), {"uid": user_id, "at": alert_type}).fetchone()
            if already_sent:
                continue
            try:
                from flask import Flask
                _app = Flask(__name__, template_folder="templates")
                with _app.app_context():
                    from flask import render_template as _render
                    html_body = _render(
                        f"email/{template_base}.html",
                        user_email=user_email,
                        trial_ends_date=trial_ends_date,
                        app_url=app_url,
                    )
                    text_body = _render(
                        f"email/{template_base}.txt",
                        user_email=user_email,
                        trial_ends_date=trial_ends_date,
                        app_url=app_url,
                    )
                send_email_task.delay(
                    to=user_email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                )
                with engine.begin() as conn:
                    try:
                        conn.execute(text("""
                            INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)
                            VALUES (:uid, '', :at, :now)
                        """), {"uid": user_id, "at": alert_type, "now": now_iso})
                    except Exception:
                        pass
                logger.info(
                    "send_trial_emails: sent %s to user %d (%s)", alert_type, user_id, user_email
                )
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                logger.error(
                    "send_trial_emails: failed %s for user %d: %s", alert_type, user_id, exc
                )
