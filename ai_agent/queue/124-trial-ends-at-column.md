# Task 124 — Add trial_ends_at column to users table

**Epic:** E10
**Milestone:** M3
**Sprint:** F-8a
**Complexity:** XS
**Status:** QUEUED

## Objective

Add `trial_ends_at` to the `users` table so the trial gate (Task 126) and trial reminder
emails (Task 135) can determine how much of the trial remains.

## Requirements

- In `db.py` `init_db()`: add to the `CREATE TABLE IF NOT EXISTS users` DDL:
  - `trial_ends_at TEXT` (nullable, ISO-8601 datetime, set on registration in Task 125)
- For existing SQLite installs: guard `ALTER TABLE users ADD COLUMN trial_ends_at TEXT`
  in a `try/except` block.
- In `migrations/001_initial_pg.sql`: add `trial_ends_at TIMESTAMP` to the users DDL and
  as `ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP` at the bottom.

## Acceptance Criteria

- [ ] `init_db()` creates `users.trial_ends_at`
- [ ] New users have `trial_ends_at IS NULL` until Task 125 wires it
- [ ] Calling `init_db()` twice does not raise
- [ ] Migration SQL is valid PostgreSQL
- [ ] All existing auth tests still pass

## Hard Dependencies

- Task 123: stripe_customer_id and subscription_status columns — must be DONE
  (batch schema work in one migration file update pass)

## DB Changes

Modify table `users`. Add `trial_ends_at TEXT`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_users.py`:
- `test_users_table_has_trial_ends_at`: `init_db()`; create user; query; assert
  `trial_ends_at IS NULL`.
- `test_init_db_idempotent_trial_column`: `init_db()` twice; no exception.

## Suggested Commit Message

`feat: add trial_ends_at column to users table (Task 124)`
