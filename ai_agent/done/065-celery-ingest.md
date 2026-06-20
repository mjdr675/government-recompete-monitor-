# Task 065 — Move SAM.gov ingest to Celery background task

**Epic:** E02
**Milestone:** M2
**Complexity:** M
**Status:** QUEUED

## Objective
Replace the `subprocess.Popen` approach for SAM.gov data ingestion with a proper Celery
background task. The UI enqueues the task and polls for status. Add a nightly Celery beat
schedule so ingest runs automatically at 02:00 UTC without manual triggering. This resolves
the "subprocess.Popen for ingest" technical debt item.

## Requirements
- Create `tasks/ingest_task.py` with a `run_ingest()` Celery task:
  - Calls the ingestion logic from `janitorial_recompete_report.py` directly (import the
    function — no subprocess)
  - Writes a row to `celery_task_log` on start and completion
  - On success: updates `celery_task_log` status to `SUCCESS` with result JSON
  - On exception: updates status to `FAILURE`, logs exception via `logging.exception()`
- Update `POST /ingest` with `action=api`:
  - Enqueue `run_ingest.delay()` and return a JSON response `{"task_id": "<id>"}`
  - Remove the existing `subprocess.Popen` call
- Create `GET /ingest/status?task_id=<id>` route (JSON, auth required):
  - Returns `{"status": "PENDING"|"RUNNING"|"SUCCESS"|"FAILURE", "message": "...", "progress": N}`
  - Reads from Celery `AsyncResult` and/or `celery_task_log`
- Register nightly schedule in `tasks.py` beat config: `run_ingest` at `02:00 UTC` daily
- Update `templates/ingest.html` to poll `/ingest/status?task_id=<id>` via HTMX or JavaScript
  after enqueue, showing live status

## Acceptance Criteria
- [ ] `POST /ingest` (action=api) returns `{"task_id": "..."}` instead of blocking
- [ ] `GET /ingest/status?task_id=<id>` returns correct status JSON at all lifecycle stages
- [ ] Nightly schedule entry visible in Celery beat log at 02:00 UTC
- [ ] `ingest.html` shows live progress without page reload
- [ ] No `subprocess.Popen` call remains in the ingest code path
- [ ] Failed ingest task logs exception and marks `celery_task_log` row as `FAILURE`
- [ ] All existing tests still pass (mock `run_ingest.delay()` in tests)
- [ ] New tests pass

## Hard Dependencies
- Task 063: Redis provision and Celery skeleton — must be DONE before this task starts
- Task 064: Celery worker in Procfile — must be DONE before this task starts

## DB Changes
- None (uses `celery_task_log` table created in Task 064)

## API Changes
- Route: `POST /ingest` — now returns JSON `{"task_id": "..."}` instead of redirecting
- Route: `GET /ingest/status?task_id=<id>` — returns JSON task progress (auth required)

## Frontend Changes
- Template: `templates/ingest.html` — add status polling after enqueue (HTMX or JS fetch)

## New Dependencies (requirements.txt)
- None (Celery already added in Task 063)

## Suggested Commit Message
`feat: move SAM.gov ingest to Celery background task with nightly schedule (Task 065)`
