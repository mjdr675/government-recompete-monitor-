# Task 112 — Add alert_preferences table

**Epic:** E03
**Milestone:** M3
**Sprint:** E-1
**Complexity:** XS
**Status:** QUEUED

## Objective

Create the `alert_preferences` table so users can configure which expiration thresholds
trigger email alerts. This is the schema prerequisite for the alert settings page (Task 114)
and the alert dispatch task (Task 117).

## Requirements

- In `db.py` `init_db()`: add `CREATE TABLE IF NOT EXISTS alert_preferences` with columns:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `user_id INTEGER NOT NULL REFERENCES users(id)`
  - `alert_days TEXT NOT NULL DEFAULT '[30, 60, 90]'` (JSON array of integer day thresholds)
  - `min_value INTEGER NOT NULL DEFAULT 0` (minimum contract value in dollars to alert on)
  - `enabled INTEGER NOT NULL DEFAULT 1` (boolean: 1 = alerts on, 0 = off)
  - `unsubscribe_token TEXT` (nullable; set when user receives first alert, used by Task 120)
  - `created_at TEXT NOT NULL DEFAULT (datetime('now'))`
  - `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`
- In `migrations/001_initial_pg.sql`: add equivalent PostgreSQL DDL with `SERIAL PRIMARY KEY`,
  `BOOLEAN DEFAULT TRUE`, `JSONB DEFAULT '[30, 60, 90]'`, and an idempotent
  `CREATE TABLE IF NOT EXISTS alert_preferences` block at the bottom.
- No default row on user creation — row is created on first visit to `/settings/alerts`.

## Acceptance Criteria

- [ ] `init_db()` creates `alert_preferences` with all columns
- [ ] Calling `init_db()` twice on an existing DB does not raise
- [ ] Migration SQL is valid PostgreSQL
- [ ] All existing tests still pass

## Hard Dependencies

- Task 082: watchlist nav badge (confirms Sprint B complete) — must be DONE
- Task 100: welcome email wired (confirms Sprint D email infra exists) — must be DONE

## DB Changes

New table: `alert_preferences`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 2 tests to `tests/test_db.py`:
- `test_alert_preferences_table_created`: call `init_db()`, insert a row with `user_id=1`,
  select it back, assert `alert_days='[30, 60, 90]'`, `enabled=1`, `min_value=0`.
- `test_init_db_idempotent_alert_preferences`: call `init_db()` twice; assert no exception.

## Suggested Commit Message

`feat: add alert_preferences table for user alert configuration (Task 112)`
