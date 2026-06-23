# Task 077 — Add user_watchlist table to schema

**Epic:** E06  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

Add the `user_watchlist` table that will back the bookmark/watchlist feature (Sprint B).
Must be added to both the SQLite `init_db()` in `db.py` and the PostgreSQL migration.

## Requirements

- In `db.py` `init_db()`: add `CREATE TABLE IF NOT EXISTS user_watchlist` with columns:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT` (SQLite) / `SERIAL PRIMARY KEY` (PG)
  - `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`
  - `internal_id TEXT NOT NULL` (FK to contracts.internal_id — soft reference, no FK constraint to allow contract churn)
  - `added_at TEXT NOT NULL` (ISO-8601 timestamp)
  - `UNIQUE(user_id, internal_id)` — a user can only bookmark a contract once
- In `migrations/001_initial_pg.sql`: add equivalent `CREATE TABLE IF NOT EXISTS user_watchlist` block after the `users` table definition
- Use `TEXT` for timestamps (consistent with existing schema)

## Acceptance Criteria

- [ ] `init_db()` creates `user_watchlist` table on a fresh SQLite DB
- [ ] `UNIQUE(user_id, internal_id)` constraint is present (prevents duplicate bookmarks)
- [ ] Migration SQL is syntactically valid PostgreSQL
- [ ] Existing tests still pass (schema change is additive)
- [ ] New test: call `init_db()`, insert two rows with same (user_id, internal_id), assert IntegrityError on second insert

## Hard Dependencies

- Task 066: users.py fix (users table must exist) — DONE

## DB Changes

New table: `user_watchlist`.

## API / Frontend Changes

None — schema only.

## New Dependencies

None.

## Testing

Add to `tests/test_db.py` (or create `tests/test_watchlist.py`): test UNIQUE constraint.

## Suggested Commit Message

`feat: add user_watchlist table to schema (Task 077)`
