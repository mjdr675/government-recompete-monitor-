# Task 126 — Add trial expiry gate redirecting to /subscribe

**Epic:** E10
**Milestone:** M3
**Sprint:** F-9
**Complexity:** S
**Status:** QUEUED

## Objective

Block access to protected routes for users whose trial has expired and who have no active
subscription. Redirect them to `/subscribe` with a clear message rather than showing a
broken or empty experience.

## Requirements

- In `app.py`, add a `@app.before_request` function `enforce_trial_gate()`:
  ```python
  @app.before_request
  def enforce_trial_gate():
  ```
  - Skip for: unauthenticated users, static files, public paths (`/login`, `/register`,
    `/subscribe`, `/success`, `/cancel`, `/health`, `/unsubscribe`), and billing routes
    (`/billing/portal`).
  - If the user is authenticated:
    - Query `users.subscription_status` and `users.trial_ends_at`.
    - If `subscription_status in ('active', 'past_due')`: allow through (paying customer).
    - If `subscription_status = 'trialing'` and `trial_ends_at > now`: allow through.
    - Otherwise (trial expired or `subscription_status = 'inactive'`): redirect to
      `/subscribe` with `flash("Your trial has ended. Subscribe to continue.", "warning")`.
- Add `/subscribe` to `_PUBLIC_PATHS` so the gate does not block the subscribe page itself.

## Acceptance Criteria

- [ ] User with active subscription passes through without redirect
- [ ] User with active trial (trial_ends_at in the future) passes through
- [ ] User with expired trial and no subscription → redirect to /subscribe
- [ ] User with `subscription_status='inactive'` and `trial_ends_at=None` → redirect
- [ ] Anonymous users are not affected by the gate (let existing auth redirect handle them)
- [ ] `/subscribe`, `/login`, `/health` are exempt from the gate
- [ ] All existing tests still pass

## Hard Dependencies

- Task 124: trial_ends_at column — must be DONE
- Task 123: subscription_status column — must be DONE
- Task 125: wire trial on registration — must be DONE

## DB Changes

Reads `users.subscription_status`, `users.trial_ends_at`.

## API Changes

None.

## Frontend Changes

None (subscribe page built in Task 136).

## New Dependencies

`from datetime import datetime` (stdlib).

## Testing

Add tests to `tests/test_trial_gate.py` (new file):
- `test_gate_allows_active_subscription`: user with `subscription_status='active'`;
  GET `/dashboard`; assert 200.
- `test_gate_allows_active_trial`: user with `subscription_status='trialing'` and
  `trial_ends_at` 5 days out; GET `/dashboard`; assert 200.
- `test_gate_blocks_expired_trial`: user with `subscription_status='trialing'` and
  `trial_ends_at` 2 days ago; GET `/dashboard`; assert 302 to `/subscribe`.
- `test_gate_blocks_inactive_user`: `subscription_status='inactive'`, `trial_ends_at=None`;
  GET `/dashboard`; assert 302.
- `test_gate_exempts_subscribe_page`: same expired-trial user; GET `/subscribe`; assert 200.

## Suggested Commit Message

`feat: add trial expiry gate redirecting expired users to /subscribe (Task 126)`
