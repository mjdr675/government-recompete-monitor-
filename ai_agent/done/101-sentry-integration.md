# Task 101 — Add Sentry error tracking

**Epic:** E09
**Milestone:** M3
**Sprint:** G-1 + G-2
**Complexity:** S
**Status:** QUEUED

## Objective

Wire Sentry so production exceptions are captured automatically and surfaced in the Sentry dashboard.

## Requirements

- Add `sentry-sdk[flask]==2.22.0` to `requirements.txt`
- In `app.py`, after `load_dotenv()`:
  ```python
  import sentry_sdk
  from sentry_sdk.integrations.flask import FlaskIntegration

  _sentry_dsn = os.environ.get("SENTRY_DSN", "")
  if _sentry_dsn:
      sentry_sdk.init(
          dsn=_sentry_dsn,
          integrations=[FlaskIntegration()],
          traces_sample_rate=0.1,
          environment=os.environ.get("RAILWAY_ENVIRONMENT", "development"),
      )
  ```
- In `tasks.py`, import and init Sentry for the worker process:
  ```python
  from sentry_sdk.integrations.celery import CeleryIntegration
  _sentry_dsn = os.environ.get("SENTRY_DSN", "")
  if _sentry_dsn:
      import sentry_sdk
      sentry_sdk.init(dsn=_sentry_dsn, integrations=[CeleryIntegration()], traces_sample_rate=0.0)
  ```
  Place this at module level after the Celery app is created.
- If `SENTRY_DSN` is not set, Sentry is silently disabled — no error, no warning
- Do NOT add `SENTRY_DSN` to `.env` or any committed file; it is a Railway env var only

## Acceptance Criteria

- [ ] `sentry-sdk[flask]` appears in `requirements.txt`
- [ ] When `SENTRY_DSN` is not set, app starts without error (existing tests pass)
- [ ] When `SENTRY_DSN` is set, `sentry_sdk.init()` is called (verify with monkeypatch)
- [ ] All existing tests still pass (Sentry is a no-op when DSN absent)

## Hard Dependencies

None.

## Testing

Add 2 tests to `tests/test_app.py`:
- `test_sentry_init_skipped_when_no_dsn`: monkeypatch `SENTRY_DSN` to `""`; patch `sentry_sdk.init`; import app; assert `sentry_sdk.init` not called
- `test_sentry_init_called_when_dsn_set`: monkeypatch `SENTRY_DSN` to `"https://fake@sentry.io/1"`; patch `sentry_sdk.init`; trigger init path; assert called

Note: Sentry init runs at module import time. Tests may need to reload the module or test via a helper function. If module-level init is untestable without reload, test that `_sentry_dsn` logic is correct via a simpler assertion (e.g. assert `sentry_sdk` is importable and the env gate works).

## Suggested Commit Message

`feat: add Sentry error tracking for Flask and Celery (Task 101)`
