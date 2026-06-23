# Task 102 — Add reset_token columns to users table

**Epic:** E05
**Milestone:** M3
**Sprint:** D-9
**Complexity:** XS
**Status:** QUEUED

## Objective

Add `reset_token` and `reset_token_expires_at` columns to the `users` table so
the password reset flow (Tasks 103–105) has schema to write to.

## Requirements

- In `db.py` `init_db()`: `ALTER TABLE IF NOT EXISTS` is not idempotent cross-dialect.
  Instead, add the two columns inside the `CREATE TABLE IF NOT EXISTS users` DDL so
  they exist on fresh installs. For existing SQLite DBs, use `ADD COLUMN IF NOT EXISTS`
  guarded by a try/except (SQLite does not support `IF NOT EXISTS` on `ALTER TABLE`).
  - `reset_token TEXT` (nullable, hex string)
  - `reset_token_expires_at TEXT` (nullable, ISO-8601 datetime)
- In `migrations/001_initial_pg.sql`: add both columns to the `users` table DDL and
  as idempotent `ALTER TABLE users ADD COLUMN IF NOT EXISTS` statements at the bottom
  of the file so they are added to existing PostgreSQL installs.
- `create_user()` in `users.py`: no change needed (columns nullable, default NULL).

## Acceptance Criteria

- [ ] `init_db()` creates `users` table with `reset_token` and `reset_token_expires_at`
- [ ] Calling `init_db()` twice on an existing DB does not raise
- [ ] Migration SQL is valid PostgreSQL
- [ ] All existing `test_auth.py` and `test_db.py` tests still pass

## Hard Dependencies

- Task 100: Welcome email wired (confirms email infrastructure complete) — must be DONE

## DB Changes

Modify table: `users`. Add `reset_token TEXT`, `reset_token_expires_at TEXT`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 2 tests to `tests/test_db.py`:
- `test_users_table_has_reset_token_column`: create test DB, insert user, assert
  `reset_token` and `reset_token_expires_at` columns exist and default to NULL.
- `test_init_db_idempotent_with_reset_token`: call `init_db()` twice, assert no exception.

## Suggested Commit Message

`feat: add reset_token columns to users table for password reset (Task 102)`
