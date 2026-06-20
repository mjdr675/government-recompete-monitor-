# Task 067 — Fix analytics.py dashboard_analytics() for PostgreSQL

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`dashboard_analytics(con)` uses `con.execute()` with SQLite-style raw SQL and a
`con.row_factory` lambda that only works with `sqlite3.Connection`. On PostgreSQL
this raises `AttributeError` (psycopg2 has no `row_factory`). Rewrite this function
to use `get_engine()` so it works on both backends.

## Requirements

- Remove the `con` parameter from `dashboard_analytics()`
- Replace all `con.execute(...)` calls with `engine.connect()` + `text(...)` blocks
- Replace `con.row_factory = lambda cur, row: ...` with `.mappings().fetchall()` or
  `.mappings().fetchone()` to get dict-like rows from SQLAlchemy
- Use named parameters (`:param`) in all SQL strings passed to `text()`
- Update `app.py` dashboard route: remove `con = connect()` / `con.close()` for this call;
  call `dashboard_analytics()` with no arguments
- `platform`, `upcoming`, `critical`, `top_agencies`, `top_vendors` must return the
  same structure as before (dicts with matching keys)

## Acceptance Criteria

- [ ] `dashboard_analytics()` takes no `con` parameter
- [ ] Function works when `DATABASE_URL` is set to PostgreSQL
- [ ] Function works when `DATABASE_URL` is unset (SQLite dev mode)
- [ ] Dashboard route in `app.py` no longer calls `connect()` for this function
- [ ] All keys returned (`platform`, `upcoming`, `critical`, `top_agencies`, `top_vendors`) match existing template expectations
- [ ] `tests/test_analytics.py` tests for dashboard analytics pass
- [ ] No `import sqlite3` introduced

## Hard Dependencies

- Task 062: Schema migration — must be DONE
- Task 066: `users.py` fix — recommended first (establishes the pattern to follow)

## DB Changes

None.

## API Changes

None — internal function signature change only.

## Frontend Changes

None — template receives same data structure.

## New Dependencies (requirements.txt)

None.

## Testing

Update `tests/test_analytics.py`: remove any `con` argument passed to `dashboard_analytics()`.
Assert returned dict has all expected keys and non-None values.

## Documentation

None required.

## Suggested Commit Message

`fix: rewrite dashboard_analytics() with SQLAlchemy for PostgreSQL compatibility (Task 067)`
