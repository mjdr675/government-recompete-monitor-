import os

from celery import Celery

tasks = Celery(
    "recompete",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

tasks.conf.task_serializer = "json"
tasks.conf.task_acks_late = True
tasks.conf.task_reject_on_worker_lost = True
