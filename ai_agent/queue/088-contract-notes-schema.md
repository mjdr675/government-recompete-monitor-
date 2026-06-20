# Task 088 — Add contract_notes table

**Epic:** E06
**Milestone:** M3
**Sprint:** B-11
**Complexity:** XS
**Status:** QUEUED

## Objective

Create the `contract_notes` table so users can attach private notes to contracts.

## Requirements

- In `db.py` `init_db()` add `CREATE TABLE IF NOT EXISTS contract_notes`:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`
  - `internal_id TEXT NOT NULL` — soft reference to contracts.internal_id (same pattern as user_watchlist)
  - `body TEXT NOT NULL`
  - `created_at TEXT NOT NULL`
- In `migrations/001_initial_pg.sql` add equivalent PostgreSQL DDL with `SERIAL PRIMARY KEY`
- No application logic changes — schema only

## Acceptance Criteria

- [ ] `contract_notes` table created by `init_db()`
- [ ] PostgreSQL migration DDL is valid
- [ ] Test: table exists after `init_db()`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 077: users table exists — DONE

## Testing

Add 1 test to `tests/test_db.py`: `contract_notes` table exists after `init_db()`.

## Suggested Commit Message

`feat: add contract_notes table (Task 088)`
