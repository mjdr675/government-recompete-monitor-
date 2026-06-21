# Task 106 — Wire sentry_sdk.capture_exception() into app.py except blocks

**Epic:** E05
**Milestone:** M3
**Sprint:** G-2
**Complexity:** S
**Status:** QUEUED

## Objective

Sentry is initialized (Task 101) but exceptions caught in `except` blocks are swallowed
before Sentry can capture them. Wire `sentry_sdk.capture_exception()` into every
`except Exception` block in `app.py` so production errors surface in the Sentry dashboard.

## Requirements

- In `app.py`, for every `except Exception as exc:` (or `except Exception:`) block
  that currently only logs or returns an error response, add:
  ```python
  import sentry_sdk
  sentry_sdk.capture_exception(exc)
  ```
  immediately before the existing `logger.error(...)` or `return` call.
- Do NOT add `capture_exception` to:
  - Blocks that handle expected/recoverable conditions (e.g. `IntegrityError` for
    duplicate email, which is a normal user flow, not a bug).
  - Blocks inside routes that raise `404` or `400` due to bad user input.
- Target blocks in `app.py` that catch unexpected errors: Stripe webhook processing,
  ingest trigger errors, HubSpot submission failures, and any generic fallback handlers.
- The import at the top of the function body is fine; `sentry_sdk` is already in
  `requirements.txt`. Alternatively, add `import sentry_sdk` at module level — either is acceptable.
- When `SENTRY_DSN` is not set, `sentry_sdk.capture_exception()` is a no-op (safe to call unconditionally).

## Acceptance Criteria

- [ ] At least 3 `except` blocks in `app.py` now call `sentry_sdk.capture_exception()`
- [ ] `IntegrityError` blocks for user-facing duplicate email/known conflicts are NOT instrumented
- [ ] All existing tests still pass (Sentry is a no-op in test environment)
- [ ] No new imports break the import graph

## Hard Dependencies

- Task 101: Sentry initialized in app.py — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None (sentry-sdk already in requirements.txt from Task 101).

## Testing

Add 1 test to `tests/test_app.py`:
- `test_sentry_capture_exception_called_on_stripe_webhook_error`: monkeypatch
  `stripe.Webhook.construct_event` to raise `Exception("boom")`; monkeypatch
  `sentry_sdk.capture_exception` to record calls; POST to `/webhook`; assert
  `capture_exception` was called once.

## Suggested Commit Message

`feat: wire sentry_sdk.capture_exception into app.py except blocks (Task 106)`
