# Task 078 — Add watchlist add/remove API routes

**Epic:** E06  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

Expose `POST /watchlist/add` and `POST /watchlist/remove` JSON routes so the frontend
can bookmark and un-bookmark contracts. Both require an active login session.

## Requirements

- In `app.py`, add two routes (both require login via `g.user`):
  - `POST /watchlist/add`: reads `internal_id` from JSON body, inserts into `user_watchlist`,
    returns `{"ok": true}` (200) or `{"ok": false, "error": "..."}` (400/409)
    - On duplicate (already bookmarked), return 200 `{"ok": true, "already": true}` (idempotent)
  - `POST /watchlist/remove`: reads `internal_id` from JSON body, deletes matching row,
    returns `{"ok": true}` (200) — idempotent even if row not present
- Both routes must be decorated with `@csrf.exempt` (JSON API, not form POST)
- Use `get_engine()` + `text()` with named params for all DB operations
- Unauthenticated requests → 401 JSON `{"error": "login required"}`

## Acceptance Criteria

- [ ] `POST /watchlist/add` with valid session and internal_id returns 200 `{"ok": true}`
- [ ] `POST /watchlist/add` twice with same internal_id returns 200 `{"ok": true, "already": true}` (no 500)
- [ ] `POST /watchlist/remove` removes the row; calling again returns 200 (idempotent)
- [ ] Both routes return 401 when called without a session
- [ ] Both routes are CSRF-exempt
- [ ] Tests for add, add-duplicate, remove, remove-nonexistent, and unauthenticated cases

## Hard Dependencies

- Task 077: user_watchlist table — must be DONE

## DB Changes

Reads/writes `user_watchlist`.

## API Changes

- `POST /watchlist/add` — new JSON endpoint
- `POST /watchlist/remove` — new JSON endpoint

## Frontend Changes

None — API only.

## New Dependencies

None.

## Testing

Add `tests/test_watchlist.py`. Fixture: auth_db + logged-in test client.

## Suggested Commit Message

`feat: add POST /watchlist/add and /watchlist/remove JSON routes (Task 078)`
