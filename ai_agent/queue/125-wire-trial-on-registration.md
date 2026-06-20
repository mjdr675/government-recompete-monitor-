# Task 125 — Wire trial_ends_at on new user registration

**Epic:** E10
**Milestone:** M3
**Sprint:** F-8b
**Complexity:** XS
**Status:** QUEUED

## Objective

Set `trial_ends_at = now + 14 days` the moment a new user registers so the trial gate
(Task 126) and trial reminder emails (Task 135) have a reference date from day one.

## Requirements

- In `users.py`, modify `create_user()` (or equivalent registration helper):
  - After writing the new user row, update `trial_ends_at` to
    `(datetime.utcnow() + timedelta(days=14)).isoformat()`.
  - Can be written directly into the `INSERT` if the DDL default is not convenient,
    or via an immediate `UPDATE users SET trial_ends_at = :ts WHERE id = last_insert_rowid()`.
- Also set `subscription_status = 'trialing'` on registration so the trial gate in
  Task 126 can distinguish active trial from no-trial.
- Do not modify the registration route itself (just the data layer function).

## Acceptance Criteria

- [ ] After `create_user()`, the new row has `trial_ends_at` approximately 14 days in the future
- [ ] After `create_user()`, `subscription_status = 'trialing'`
- [ ] Existing `test_register_*` tests still pass
- [ ] Re-registering with the same email (error path) does not set any `trial_ends_at`

## Hard Dependencies

- Task 124: trial_ends_at column — must be DONE
- Task 123: subscription_status column — must be DONE

## DB Changes

Writes `users.trial_ends_at` and `users.subscription_status` on registration.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

`from datetime import datetime, timedelta` (stdlib).

## Testing

Add tests to `tests/test_users.py`:
- `test_create_user_sets_trial_ends_at`: `create_user(...)`; query row; assert
  `trial_ends_at` is within 13–15 days from now.
- `test_create_user_sets_status_trialing`: assert `subscription_status = 'trialing'`.
- `test_duplicate_email_does_not_set_trial`: attempt to create duplicate email; assert
  exception raised and no new row with `trial_ends_at` written.

## Suggested Commit Message

`feat: set trial_ends_at and status=trialing on new user registration (Task 125)`
