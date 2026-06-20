# Task 063 — Add Redis service to Railway and Celery skeleton

**Epic:** E02
**Milestone:** M2
**Complexity:** S
**Status:** QUEUED

## Objective
Add Railway Redis as the Celery message broker. Create the `tasks.py` Celery app entry
point so subsequent tasks (064, 065) can register background tasks. The app must continue
to start and serve traffic when Redis is unavailable — degraded mode, not a crash.

## Requirements
- Add `REDIS_URL` to Railway environment variables (done by operator; app must consume it)
- Add `redis` and `celery` to `requirements.txt`
- Create `tasks.py` at the project root:
  - `tasks = Celery('recompete', broker=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))`
  - `tasks.conf.task_serializer = 'json'`
  - `tasks.conf.task_acks_late = True`
  - `tasks.conf.task_reject_on_worker_lost = True`
- On app startup, attempt a Redis `PING`; if Redis is unreachable, log a warning at `WARNING`
  level and continue — do not raise an exception or set app state to unhealthy
- `GET /health` must still return 200 when Redis is unavailable

## Acceptance Criteria
- [ ] `tasks.py` imports without error when `REDIS_URL` is set
- [ ] `tasks.py` imports without error when `REDIS_URL` is absent (falls back to localhost)
- [ ] App starts without crashing when Redis is unreachable
- [ ] `GET /health` returns 200 regardless of Redis availability
- [ ] All existing tests still pass (mock Redis in test env)
- [ ] New tests pass

## Hard Dependencies
- Task 061: PostgreSQL provision — must be DONE before this task starts

## DB Changes
- None

## API Changes
- None

## Frontend Changes
- None

## New Dependencies (requirements.txt)
- `redis` — Redis client library
- `celery` — distributed task queue

## Suggested Commit Message
`feat: add Redis service and Celery task app skeleton (Task 063)`
