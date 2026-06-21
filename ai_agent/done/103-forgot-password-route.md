# Task 103 — Add GET/POST /forgot-password route

**Epic:** E05
**Milestone:** M3
**Sprint:** D-10
**Complexity:** S
**Status:** QUEUED

## Objective

Implement the first half of the password reset flow: accept the user's email address,
generate a time-limited reset token, store it, and enqueue a reset email.

## Requirements

- Add two helper functions to `users.py`:
  - `set_reset_token(email: str) -> str | None`: query user by email; if found, generate
    a 32-byte hex token (`secrets.token_hex(32)`), set `reset_token_expires_at` to
    `(datetime.utcnow() + timedelta(hours=1)).isoformat()`, write both to the `users`
    row, return the token; return `None` if email not found.
  - `get_user_by_reset_token(token: str) -> dict | None`: return user row where
    `reset_token = :token` and `reset_token_expires_at > :now`; return `None` if not found
    or expired.
- In `auth.py` blueprint, add:
  ```python
  @bp.route("/forgot-password", methods=["GET", "POST"])
  def forgot_password():
  ```
  - GET: render `templates/forgot_password.html` (simple email input form).
  - POST: call `set_reset_token(email)`; regardless of whether email exists, render the
    same success page (`templates/forgot_password.html` with `sent=True`) to avoid
    user enumeration. If token returned, enqueue `send_email_task.delay()` with subject
    "Reset your Gov Recompete Monitor password" and `reset_url = f"{APP_URL}/reset-password?token={token}"`.
    Render the password reset email template (Task 104) for the body.
- Add `/forgot-password` to `_PUBLIC_PATHS` in `app.py`.
- Add `templates/forgot_password.html` extending `base.html` with email field and
  conditional success message.

## Acceptance Criteria

- [ ] GET `/forgot-password` returns 200 for unauthenticated users
- [ ] POST with unknown email returns 200 (same success page — no enumeration)
- [ ] POST with known email stores token in DB and enqueues email task
- [ ] Token expires 1 hour after generation
- [ ] `set_reset_token` is idempotent: calling twice overwrites with a new token
- [ ] All existing auth tests still pass

## Hard Dependencies

- Task 102: reset_token columns — must be DONE
- Task 097: send_email_task Celery task — must be DONE
- Task 104: password reset email template — write in parallel; route can stub the body if 104 not done

## DB Changes

Writes to `users.reset_token` and `users.reset_token_expires_at`.

## API Changes

New route: `GET /forgot-password`, `POST /forgot-password`.

## Frontend Changes

New template: `templates/forgot_password.html`.

## New Dependencies

`import secrets` (stdlib — already available).

## Testing

Add tests to `tests/test_auth.py`:
- `test_forgot_password_get_returns_200`: unauthenticated GET returns 200.
- `test_forgot_password_post_unknown_email_returns_200`: unknown email → 200, no exception.
- `test_forgot_password_post_known_email_sets_token`: POST with registered email → token
  written to DB, `send_email_task.delay` called (monkeypatch).
- `test_forgot_password_post_known_email_no_enumeration`: response body identical for
  known vs. unknown email.

## Suggested Commit Message

`feat: add /forgot-password route with reset token generation (Task 103)`
