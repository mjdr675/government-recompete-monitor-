# Task 084 — Add user_saved_searches table

**Epic:** E06
**Milestone:** M3
**Sprint:** B-7
**Complexity:** XS
**Status:** QUEUED

## Objective

Create the `user_saved_searches` table so users can persist named contract filter sets.

## Requirements

- In `db.py` `init_db()` add `CREATE TABLE IF NOT EXISTS user_saved_searches`:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`
  - `name TEXT NOT NULL` — user-supplied label (e.g. "DoD Janitorial expiring 90d")
  - `query_params_json TEXT NOT NULL` — JSON-encoded query string params
  - `created_at TEXT NOT NULL`
- In `migrations/001_initial_pg.sql` add equivalent PostgreSQL `CREATE TABLE IF NOT EXISTS user_saved_searches` with `SERIAL PRIMARY KEY`
- No application logic changes — schema only

## Acceptance Criteria

- [ ] `user_saved_searches` table created by `init_db()`
- [ ] PostgreSQL migration SQL is valid (IF NOT EXISTS, SERIAL)
- [ ] Test: table exists after `init_db()`, UNIQUE not required but insert two rows for same user works
- [ ] All existing tests still pass

## Hard Dependencies

- Task 077: users table exists — DONE

## DB Changes

New table: `user_saved_searches`.

## Testing

Add 2 tests to `tests/test_db.py`: table exists after init, can insert two saved searches for same user.

## Suggested Commit Message

`feat: add user_saved_searches table (Task 084)`
