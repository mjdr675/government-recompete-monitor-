# Task 107 — Wire sentry_sdk.capture_exception() into tasks.py except blocks

**Epic:** E05
**Milestone:** M3
**Sprint:** G-2
**Complexity:** S
**Status:** QUEUED

## Objective

Wire `sentry_sdk.capture_exception()` into every unexpected `except` block in
`tasks.py` so Celery worker failures are captured in Sentry independently of
whether the task retries or fails silently.

## Requirements

- In `tasks.py`, add `import sentry_sdk` at module level (after existing imports).
- In `run_ingest()`: in the outer `except Exception as exc:` block that logs the
  failure and inserts the `ingest_log` error row, add `sentry_sdk.capture_exception(exc)`
  immediately before the logger call.
- In `send_email_task()`: in the `except Exception as exc:` block before `self.retry()`,
  add `sentry_sdk.capture_exception(exc)` before the `logger.error(...)` line. Note:
  Sentry's `CeleryIntegration` (Task 101) already captures unhandled task exceptions;
  this adds explicit capture for caught+retried exceptions too.
- In `check_beat_health()`: if an exception occurs querying Redis, capture it.
- Do NOT instrument expected/no-op branches (e.g. `except ImportError` guards or
  `except ConnectionError` that already degrade gracefully with a logged warning).
- `sentry_sdk.capture_exception()` is a no-op when `SENTRY_DSN` is not set — safe to call unconditionally.

## Acceptance Criteria

- [ ] `run_ingest` except block calls `sentry_sdk.capture_exception(exc)`
- [ ] `send_email_task` except block calls `sentry_sdk.capture_exception(exc)`
- [ ] All existing Celery tests still pass
- [ ] No circular import introduced

## Hard Dependencies

- Task 101: Sentry initialized in tasks.py — must be DONE
- Task 106: Sentry wired in app.py — recommended first (establishes pattern)

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 1 test to `tests/test_celery_ingest.py`:
- `test_sentry_capture_called_on_ingest_failure`: monkeypatch `upsert_contract` to
  raise `RuntimeError`; monkeypatch `sentry_sdk.capture_exception` to record calls;
  run `run_ingest.apply()`; assert `capture_exception` was called.

## Suggested Commit Message

`feat: wire sentry_sdk.capture_exception into tasks.py except blocks (Task 107)`
