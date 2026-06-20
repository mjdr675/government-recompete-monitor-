# Task 064 — Add Celery worker to Procfile and wire first background task

**Epic:** E02
**Milestone:** M2
**Complexity:** M
**Status:** QUEUED

## Objective
Add the Celery worker and beat scheduler to the Railway `Procfile` and prove the task queue
works end-to-end by registering a no-op heartbeat task. This unblocks all background job
features (nightly ingest, email alerts, AI enrichment). Implement beat health monitoring
(Task 281) in the same session to detect silent scheduler failures from day one.

## Requirements
- Add to `Procfile`:
  - `worker: celery -A tasks worker --loglevel=info`
  - `beat: celery -A tasks beat --loglevel=info --scheduler celery.beat.PersistentScheduler`
- Create `tasks/noop_task.py` (or register directly in `tasks.py`) with a `heartbeat()` task:
  - Logs `"Celery beat heartbeat"` at INFO level
  - Writes the current UTC timestamp to a `beat:health` Redis key with a 15-minute TTL
- Register `heartbeat` in Celery beat schedule: every 5 minutes
- Create a `check_beat_health()` task scheduled every 10 minutes:
  - Reads `beat:health` from Redis; if key is missing or timestamp is > 15 minutes old,
    logs an ERROR-level alert (Sentry integration comes in Task 219 — for now, log only)
- Create `celery_task_log` table in `db.py`: `(id, task_name TEXT, status TEXT, started_at TEXT, finished_at TEXT, result_json TEXT)`
- Web process must be unaffected by worker crashes (independent Railway services)

## Acceptance Criteria
- [ ] `Procfile` contains `worker` and `beat` entries
- [ ] `heartbeat` task executes every 5 minutes (visible in worker logs)
- [ ] `check_beat_health` task executes every 10 minutes
- [ ] `beat:health` Redis key written by each heartbeat execution
- [ ] `celery_task_log` table created by `init_db()`
- [ ] Web process starts normally without a running worker
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- Task 063: Redis provision and Celery skeleton — must be DONE before this task starts

## DB Changes
- Table: `celery_task_log` — new table: `(id INTEGER PRIMARY KEY, task_name TEXT, status TEXT, started_at TEXT, finished_at TEXT, result_json TEXT)`

## API Changes
- None

## Frontend Changes
- None

## New Dependencies (requirements.txt)
- None (Celery and Redis already added in Task 063)

## Suggested Commit Message
`feat: add Celery worker and beat scheduler to Railway deployment (Task 064)`
