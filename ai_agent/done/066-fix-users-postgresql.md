# Task 066 — Fix users.py PostgreSQL compatibility

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`users.py` uses `sqlite3.IntegrityError`, `sqlite3.Row`, and `?` placeholders directly.
When `DATABASE_URL` points to PostgreSQL, `create_user()`, `get_user_by_id()`, and
`get_user_by_email()` all fail. Rewrite the module to use SQLAlchemy Core so it works
against both SQLite (dev) and PostgreSQL (production).

## Requirements

- Replace `import sqlite3` with `from sqlalchemy import text` and `from sqlalchemy.exc import IntegrityError`
- Replace `from db import connect` with `from db import get_engine`
- Rewrite `create_user()`:
  - Use `get_engine().begin()` as the connection context
  - Follow the `is_pg = engine.dialect.name == "postgresql"` pattern already used in `db.py`
  - For PostgreSQL: use `text("INSERT INTO users ... VALUES (...) RETURNING id")` and call `result.scalar()` for the new ID
  - For SQLite: use `text("INSERT INTO users ... VALUES (...)")` and call `result.lastrowid` for the new ID
  - On `IntegrityError` (from `sqlalchemy.exc`), raise `ValueError(f"Email already registered: {email}")`
- Rewrite `get_user_by_id()`:
  - Use `get_engine().connect()` + `text("SELECT ... WHERE id = :id AND is_active = 1")`
  - Return `dict(row._mapping)` instead of `dict(sqlite3.Row)`
- Rewrite `get_user_by_email()`:
  - Same pattern as `get_user_by_id()` with `WHERE email = :email`
- `verify_password()` requires no changes (calls the above functions)

## Acceptance Criteria

- [ ] `create_user()` inserts a row and returns `{"id": ..., "email": ..., "created_at": ...}`
- [ ] `create_user()` raises `ValueError` on duplicate email
- [ ] `get_user_by_id()` returns a dict (not a sqlite3.Row)
- [ ] `get_user_by_email()` returns a dict including `password_hash`
- [ ] `verify_password()` returns user dict on correct credentials, None otherwise
- [ ] No `import sqlite3` remains in `users.py`
- [ ] All existing `tests/test_auth.py` tests pass
- [ ] New test: call `create_user()` twice with same email — assert `ValueError` raised

## Hard Dependencies

- Task 062: Schema migration (SQLAlchemy + PostgreSQL schema) — must be DONE

## DB Changes

None — schema unchanged.

## API Changes

None — internal module only.

## Frontend Changes

None.

## New Dependencies (requirements.txt)

None — SQLAlchemy already added in Task 062.

## Testing

Update `tests/test_auth.py` fixture: replace any `sqlite3`-specific connection setup with
`get_engine()`. All 22 existing auth tests must continue to pass.

## Documentation

None required.

## Suggested Commit Message

`fix: rewrite users.py with SQLAlchemy for PostgreSQL compatibility (Task 066)`
