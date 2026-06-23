# Task 069 — Fix analytics.py agency_profile() for PostgreSQL

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`agency_profile(con, agency)` uses SQLite-specific `con.execute()` with `?` placeholders
and `con.row_factory`. On PostgreSQL this fails. Rewrite to use `get_engine()` and
SQLAlchemy `text()` with named parameters. This is the same pattern as Task 068 applied
to the agency profile function.

## Requirements

- Change signature from `agency_profile(con, agency)` to `agency_profile(agency)`
- Replace all `con.execute("...", (agency,))` with `engine.connect()` + `text("... WHERE agency = :agency")` + `{"agency": agency}`
- Replace `con.row_factory = lambda cur, row: ...` with `.mappings().fetchall()` / `.mappings().fetchone()`
- Update `app.py` agency_profile route: remove `con = connect()` / `con.close()`; call `agency_profile_query(name)` with one argument
- All returned sub-dicts (`summary`, `vendors`, `upcoming`, `active`, `pipeline_by_priority`, `score_distribution`, `win_loss_summary`, `change_events`, `timeline`) must retain the same keys

## Acceptance Criteria

- [ ] `agency_profile(agency)` takes only the agency name, no `con`
- [ ] Function works on both PostgreSQL and SQLite
- [ ] `app.py` `/agency/<name>` route no longer calls `connect()` for this function
- [ ] Agency page renders correctly with same data layout
- [ ] `change_events` fallback (try/except) preserved for missing changes table
- [ ] All existing agency analytics tests pass

## Hard Dependencies

- Task 062: Schema migration — must be DONE
- Task 068: `vendor_profile_analytics()` fix — same pattern, do first

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None — template receives same data structure.

## New Dependencies (requirements.txt)

None.

## Testing

Update `tests/test_analytics.py`: remove `con` argument from `agency_profile()` calls.
Assert returned dict has expected keys when called with an agency name that exists and one that does not.

## Documentation

None required.

## Suggested Commit Message

`fix: rewrite agency_profile() with SQLAlchemy for PostgreSQL compatibility (Task 069)`
