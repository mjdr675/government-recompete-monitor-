# Task 113 — Add alert_log table

**Epic:** E03
**Milestone:** M3
**Sprint:** E-7
**Complexity:** XS
**Status:** QUEUED

## Objective

Create the `alert_log` table to record every sent alert. The dispatch task (Task 117) reads
this table before sending to prevent duplicate alerts for the same (user, contract, threshold)
within the same expiration window.

## Requirements

- In `db.py` `init_db()`: add `CREATE TABLE IF NOT EXISTS alert_log` with columns:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `user_id INTEGER NOT NULL REFERENCES users(id)`
  - `contract_id TEXT NOT NULL` (SAM.gov contract identifier)
  - `days_threshold INTEGER NOT NULL` (which threshold triggered: 30, 60, or 90)
  - `sent_at TEXT NOT NULL DEFAULT (datetime('now'))`
- Add a `UNIQUE` constraint on `(user_id, contract_id, days_threshold)` so that a single
  INSERT replaces duplicate checks with a DB-level guarantee. Use
  `CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_log ON alert_log(user_id, contract_id, days_threshold)`.
- In `migrations/001_initial_pg.sql`: add equivalent PostgreSQL DDL with `SERIAL PRIMARY KEY`
  and `CREATE UNIQUE INDEX IF NOT EXISTS` at the bottom of the file.

## Acceptance Criteria

- [ ] `init_db()` creates `alert_log` with all columns
- [ ] Inserting the same `(user_id, contract_id, days_threshold)` twice raises IntegrityError
- [ ] Migration SQL is valid PostgreSQL
- [ ] All existing tests still pass

## Hard Dependencies

- Task 112: alert_preferences table — must be DONE

## DB Changes

New table: `alert_log`. New unique index: `uq_alert_log`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 2 tests to `tests/test_db.py`:
- `test_alert_log_table_created`: `init_db()`, insert a row, select back, assert columns.
- `test_alert_log_unique_constraint`: insert same `(user_id, contract_id, days_threshold)`
  twice; assert second insert raises an exception (IntegrityError or equivalent).

## Suggested Commit Message

`feat: add alert_log table with unique constraint for alert deduplication (Task 113)`
