# Task 123 — Add stripe_customer_id and subscription_status columns to users

**Epic:** E10
**Milestone:** M3
**Sprint:** F-4
**Complexity:** XS
**Status:** QUEUED

## Objective

Add `stripe_customer_id` and `subscription_status` to the `users` table so webhook
handlers (Tasks 127, 128) and the trial gate (Task 126) can read and update subscription
state without a round-trip to Stripe.

## Requirements

- In `db.py` `init_db()`: add to the `CREATE TABLE IF NOT EXISTS users` DDL:
  - `stripe_customer_id TEXT` (nullable)
  - `subscription_status TEXT NOT NULL DEFAULT 'inactive'`
    (valid values: `'inactive'`, `'trialing'`, `'active'`, `'past_due'`, `'cancelled'`)
- For existing SQLite installs, guard with `try/except` around `ALTER TABLE users ADD COLUMN`
  for each column (SQLite does not support `ADD COLUMN IF NOT EXISTS`).
- In `migrations/001_initial_pg.sql`: add both columns to the `users` CREATE TABLE DDL and
  as idempotent `ALTER TABLE users ADD COLUMN IF NOT EXISTS` statements at the bottom.
- In `users.py`, add a helper:
  ```python
  def update_subscription_status(stripe_customer_id: str, status: str) -> None:
  ```
  Updates `subscription_status` WHERE `stripe_customer_id = :stripe_customer_id`.

## Acceptance Criteria

- [ ] `init_db()` adds `stripe_customer_id` and `subscription_status` to `users`
- [ ] `subscription_status` defaults to `'inactive'` for new users
- [ ] Calling `init_db()` twice does not raise
- [ ] `update_subscription_status()` updates the correct row
- [ ] All existing auth tests still pass

## Hard Dependencies

- Task 066: users.py PostgreSQL compatibility fixed — must be DONE

## DB Changes

Modify table `users`. Add `stripe_customer_id TEXT`, `subscription_status TEXT DEFAULT 'inactive'`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_users.py`:
- `test_users_table_has_subscription_columns`: `init_db()`; create user; query `users` table;
  assert `stripe_customer_id IS NULL` and `subscription_status = 'inactive'`.
- `test_update_subscription_status`: insert user with `stripe_customer_id='cus_test'`;
  call `update_subscription_status('cus_test', 'active')`; assert DB row updated.
- `test_init_db_idempotent_subscription_columns`: `init_db()` twice; no exception.

## Suggested Commit Message

`feat: add stripe_customer_id and subscription_status columns to users (Task 123)`
