# Task 070 — Fix analytics.py opportunity_recommendations() for PostgreSQL

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`opportunity_recommendations(con)` uses SQLite-specific `con.execute()` with raw SQL
strings and `con.row_factory`. On PostgreSQL this fails. This is the last of the four
analytics functions that need rewriting. After this task, the dashboard, vendor, and
agency pages will all work on PostgreSQL.

## Requirements

- Change signature from `opportunity_recommendations(con)` to `opportunity_recommendations()`
- Replace all `con.execute(...)` with a single `engine.connect()` context; run all five
  sub-queries inside it using `text(...)` with no positional params (these queries have no params)
- Replace `con.row_factory = lambda cur, row: ...` with `.mappings().fetchall()`
- The `_add(row, reason)` inner function accesses rows as dicts — `.mappings()` returns
  `RowMapping` objects which support dict-style access; no change needed to `_add()`
- Preserve the `try/except Exception: pass` guard around the `changes` JOIN query
- Update `app.py` dashboard route: remove `con` argument from `opportunity_recommendations()` call

## Acceptance Criteria

- [ ] `opportunity_recommendations()` takes no arguments
- [ ] Returns a list of dicts, each with `internal_id`, `vendor`, `agency`, `value`, `end_date`, `days_remaining`, `priority`, `recompete_score`, `reason`
- [ ] Function works on both PostgreSQL and SQLite
- [ ] Dashboard route no longer calls `connect()` solely for this function
- [ ] `change_events` JOIN query failure (missing changes table) is caught silently
- [ ] All existing recommendation tests pass
- [ ] After tasks 067–070 are complete, `app.py` dashboard route requires zero `connect()` / `con.close()` calls

## Hard Dependencies

- Task 062: Schema migration — must be DONE
- Task 067: `dashboard_analytics()` fix — must be DONE (removes first `con` from dashboard route)

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None — template receives same list structure.

## New Dependencies (requirements.txt)

None.

## Testing

Update `tests/test_analytics.py`: call `opportunity_recommendations()` with no arguments.
Assert returns a list; assert each element has a `reason` key.

## Documentation

None required.

## Suggested Commit Message

`fix: rewrite opportunity_recommendations() with SQLAlchemy for PostgreSQL compatibility (Task 070)`
