# Task 062 — Migrate schema from SQLite to PostgreSQL

**Epic:** E02
**Milestone:** M2
**Complexity:** XL
**Status:** QUEUED

## Objective
Rewrite `db.py` using SQLAlchemy Core so all table definitions and queries work on both
PostgreSQL (production) and SQLite (local dev). Port FTS5 full-text search to PostgreSQL
`tsvector` + `GIN` index. Write a one-time migration script that is idempotent and safe
to run against the existing SQLite data before cut-over. This task unblocks 35+ downstream
tasks and is the highest-risk single task in the roadmap.

## Requirements
- Add `sqlalchemy>=2.0` to `requirements.txt`
- Rewrite all SQL in `db.py` to use `sqlalchemy.text()` with named bind parameters
  (`:param` style for SQLAlchemy, compatible with both PG and SQLite via `text()`)
- Rewrite `init_db()` to use `CREATE TABLE IF NOT EXISTS` DDL compatible with PostgreSQL:
  - `TEXT` instead of `VARCHAR`; `REAL` instead of `FLOAT`; `BOOLEAN` as `BOOLEAN`
  - Remove SQLite-only `WITHOUT ROWID` or `STRICT` clauses if present
- Replace FTS5 virtual table with a `tsvector` generated column on `contracts` (PostgreSQL)
  or keep FTS5 for SQLite dev: detect dialect in `init_db()` and run the appropriate DDL
- Replace FTS query (`MATCH` syntax) with `to_tsvector @@ to_tsquery` in PostgreSQL path;
  keep `MATCH` for SQLite path
- Port all queries in `analytics.py` and `change_detector.py` to the same `sqlalchemy.text()` style
- Create `migrations/001_initial_pg.sql` — SQL script that creates all tables on a fresh
  PostgreSQL instance (mirrors `init_db()` DDL, idempotent with `IF NOT EXISTS`)
- Add `CREATE EXTENSION IF NOT EXISTS vector;` to the migration (pgvector, for future use)
- Migration runs from `Procfile` entry: `release: python -c "from db import init_db; init_db()"`
  before gunicorn starts

## Acceptance Criteria
- [ ] All 84+ existing tests pass when run against SQLite (default test mode)
- [ ] FTS search returns the same results as before the migration
- [ ] `migrations/001_initial_pg.sql` runs without error on a fresh PostgreSQL 14+ instance
- [ ] `init_db()` is idempotent — safe to call on an existing database (no data loss)
- [ ] SQLite still works for local dev when `DATABASE_URL` is absent
- [ ] `GET /health` returns 200 after migration in production
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- Task 061: PostgreSQL provision and DATABASE_URL config — must be DONE before this task starts

## DB Changes
- Table: `contracts` — add `search_vector tsvector` column (PostgreSQL only); DDL made PG-compatible
- All existing tables: DDL rewritten for PostgreSQL compatibility (no column additions)
- New file: `migrations/001_initial_pg.sql`

## API Changes
- None

## Frontend Changes
- None

## New Dependencies (requirements.txt)
- `sqlalchemy>=2.0` — database abstraction layer (Core only, no ORM)

## Suggested Commit Message
`feat: migrate database layer to PostgreSQL with SQLAlchemy Core (Task 062)`
