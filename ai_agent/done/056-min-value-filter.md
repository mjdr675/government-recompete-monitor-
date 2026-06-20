# Task 056 — Add min_value filter to get_contracts()

**Epic:** E01
**Milestone:** M1
**Complexity:** S
**Status:** QUEUED

## Objective
The High Value Contracts saved view returns all contracts because `get_contracts()` has no
`min_value` parameter. Add it so the view filters correctly and any caller can specify a
minimum contract value threshold. This is a carry-forward backlog item blocking accurate
saved view results for paying customers.

## Requirements
- Add `min_value=None` keyword argument to `get_contracts()` in `db.py`
- When `min_value` is set, append `AND c.value >= ?` (SQLite) or `AND c.value >= %s` (PostgreSQL) to the query with a bound parameter
- Pass `request.args.get('min_value', type=float)` through the `/contracts` route in `app.py`
- Return HTTP 400 if `min_value` is provided but is a negative number
- Update `SAVED_VIEWS` dict (in `views.py` or wherever views are defined) so the High Value view passes `min_value=1000000`

## Acceptance Criteria
- [ ] `GET /contracts?min_value=1000000` returns only contracts with `value >= 1000000`
- [ ] High Value saved view correctly filters to ≥ $1M contracts
- [ ] `GET /contracts?min_value=-1` returns HTTP 400
- [ ] `GET /contracts` with no `min_value` returns all contracts (no regression)
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None

## API Changes
- Route: `GET /contracts` — accepts new `min_value` query parameter (float, optional)

## Frontend Changes
- None (parameter passthrough only; no template changes)

## New Dependencies (requirements.txt)
- None

## Suggested Commit Message
`feat: add min_value filter to get_contracts and /contracts route (Task 056)`
