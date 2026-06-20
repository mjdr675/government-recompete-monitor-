# Task 061 — Provision PostgreSQL on Railway and add DATABASE_URL config

**Epic:** E02
**Milestone:** M2
**Complexity:** S
**Status:** QUEUED

## Objective
Add Railway PostgreSQL as the production database backend. Wire `DATABASE_URL` into the
app so the data layer can detect it and prefer PostgreSQL over the SQLite fallback. SQLite
must remain functional for local development when `DATABASE_URL` is absent. This task is
purely provisioning and config — the schema migration is Task 062.

## Requirements
- Add `DATABASE_URL` to Railway environment variables (done manually by operator, but app must consume it)
- Update `db.py`: add a `get_connection()` helper that returns a `psycopg2` connection when
  `DATABASE_URL` is set, or an `sqlite3` connection to `DB_PATH` otherwise
- All existing `sqlite3.connect(DB_PATH)` calls in `db.py` replaced with `get_connection()`
- Add `psycopg2-binary` to `requirements.txt`
- App must start without error when `DATABASE_URL` is set (even if schema does not yet exist)
- App must start without error when `DATABASE_URL` is absent (SQLite fallback)
- `GET /health` returns 200 in both modes

## Acceptance Criteria
- [ ] `get_connection()` returns `psycopg2` connection when `DATABASE_URL` is set
- [ ] `get_connection()` returns `sqlite3` connection when `DATABASE_URL` is absent
- [ ] App starts without crashing in both modes
- [ ] `GET /health` returns 200 in both modes
- [ ] All existing tests still pass (tests use SQLite via `tmp_path`; `DATABASE_URL` absent in test env)
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None (schema migration is Task 062)

## API Changes
- None

## Frontend Changes
- None

## New Dependencies (requirements.txt)
- `psycopg2-binary` — PostgreSQL adapter for Python

## Suggested Commit Message
`feat: add PostgreSQL support with DATABASE_URL env var (Task 061)`
