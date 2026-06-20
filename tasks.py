import logging
import os
from datetime import datetime, timedelta, timezone

from celery import Celery

logger = logging.getLogger(__name__)

tasks = Celery(
    "recompete",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
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
}

_BEAT_HEALTH_KEY = "beat:health"
_BEAT_HEALTH_TTL = 900  # 15 minutes in seconds
_BEAT_STALE_THRESHOLD = timedelta(minutes=15)


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
