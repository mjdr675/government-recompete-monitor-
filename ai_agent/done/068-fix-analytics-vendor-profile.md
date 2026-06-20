# Task 068 — Fix analytics.py vendor_profile_analytics() for PostgreSQL

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`vendor_profile_analytics(con, vendor)` uses SQLite-specific `con.execute()` with `?`
placeholders and `con.row_factory`. On PostgreSQL this fails. Rewrite to use
`get_engine()` and SQLAlchemy `text()` with named parameters.

## Requirements

- Change signature from `vendor_profile_analytics(con, vendor)` to `vendor_profile_analytics(vendor)`
- Replace all `con.execute("...", (vendor,))` with `engine.connect()` + `text("... WHERE vendor = :vendor")` + `{"vendor": vendor}`
- Replace `con.row_factory = lambda cur, row: ...` with `.mappings().fetchall()` / `.mappings().fetchone()`
- Update `app.py` vendor_profile route: remove `con = connect()` / `con.close()`; call `vendor_profile_analytics(name)` with one argument
- All returned sub-dicts (`summary`, `agencies`, `upcoming`, `active`, `pipeline_by_priority`, `score_distribution`, `win_loss_summary`, `change_events`, `timeline`) must retain the same keys

## Acceptance Criteria

- [ ] `vendor_profile_analytics(vendor)` takes only the vendor name, no `con`
- [ ] Function works on both PostgreSQL and SQLite
- [ ] `app.py` `/vendor/<name>` route no longer calls `connect()` for this function
- [ ] Vendor page renders correctly with same data layout
- [ ] `change_events` fallback (try/except) preserved for missing changes table
- [ ] All existing vendor analytics tests pass
- [ ] New test: call with a vendor name that has no contracts — assert empty lists returned gracefully

## Hard Dependencies

- Task 062: Schema migration — must be DONE
- Task 067: `dashboard_analytics()` fix — establishes the pattern (recommended first)

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None — template receives same data structure.

## New Dependencies (requirements.txt)

None.

## Testing

Update `tests/test_analytics.py`: remove `con` argument from `vendor_profile_analytics()` calls.

## Documentation

None required.

## Suggested Commit Message

`fix: rewrite vendor_profile_analytics() with SQLAlchemy for PostgreSQL compatibility (Task 068)`
