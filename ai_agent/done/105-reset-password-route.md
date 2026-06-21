# Task 105 — Add GET/POST /reset-password route

**Epic:** E05
**Milestone:** M3
**Sprint:** D-12
**Complexity:** S
**Status:** QUEUED

## Objective

Implement the second half of the password reset flow: validate the token, display the
new-password form, update the password hash, and invalidate the token so it cannot
be reused.

## Requirements

- Add helper to `users.py`:
  - `clear_reset_token(user_id: int) -> None`: set `reset_token = NULL` and
    `reset_token_expires_at = NULL` for the given user.
  - `update_password(user_id: int, new_password: str) -> None`: re-hash with scrypt
    using the same `generate_password_hash()` call used in `create_user()`, update
    `users.password_hash`.
- In `auth.py` blueprint, add:
  ```python
  @bp.route("/reset-password", methods=["GET", "POST"])
  def reset_password():
  ```
  - GET: read `token` from `request.args`; call `get_user_by_reset_token(token)`;
    if None render `templates/reset_password.html` with `error="Invalid or expired link."`;
    otherwise render form.
  - POST: read `token` from `request.form`; validate via `get_user_by_reset_token(token)`;
    if invalid return 400 with error; validate `password == confirm` and `len >= 8`;
    call `update_password(user["id"], password)` then `clear_reset_token(user["id"])`;
    flash "Password updated. Please log in." and redirect to `/login`.
- Add `/reset-password` to `_PUBLIC_PATHS` in `app.py`.
- Add `templates/reset_password.html` extending `base.html`: password + confirm fields,
  hidden `token` input, submit button.

## Acceptance Criteria

- [ ] GET with valid token renders the form
- [ ] GET with expired/invalid token renders error message, 200 status
- [ ] POST with valid token, matching passwords: updates hash, clears token, redirects to /login
- [ ] POST with valid token, mismatched passwords: returns form with error, no DB change
- [ ] POST with expired token: returns 400
- [ ] After successful reset, the old token cannot be reused (returns invalid)
- [ ] New password works for login (end-to-end)

## Hard Dependencies

- Task 102: reset_token columns — must be DONE
- Task 103: forgot_password route + get_user_by_reset_token helper — must be DONE

## DB Changes

Writes to `users.password_hash`, `users.reset_token`, `users.reset_token_expires_at`.

## API Changes

New route: `GET /reset-password`, `POST /reset-password`.

## Frontend Changes

New template: `templates/reset_password.html`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_auth.py`:
- `test_reset_password_get_valid_token`: seed user with reset token; GET /reset-password?token=<tok> → 200 with form.
- `test_reset_password_get_invalid_token`: GET with bad token → 200 with error message.
- `test_reset_password_post_updates_password`: POST with valid token and matching passwords → password updated, token cleared, 302 to /login.
- `test_reset_password_post_mismatched_passwords`: POST with valid token, passwords mismatch → form error, no DB change.
- `test_reset_password_post_expired_token`: POST with expired token → 400.
- `test_reset_token_cannot_be_reused`: POST valid reset, then POST same token again → 400.

## Suggested Commit Message

`feat: add /reset-password route to complete password reset flow (Task 105)`
