# Task 085 — Add POST /searches/save and DELETE /searches/:id routes

**Epic:** E06
**Milestone:** M3
**Sprint:** B-8
**Complexity:** S
**Status:** QUEUED

## Objective

Backend routes to create and delete saved searches.

## Requirements

- `POST /searches/save` (login required, CSRF-exempt JSON endpoint):
  - Reads JSON body `{"name": "...", "params": {...}}`
  - Validates `name` non-empty (400 if missing)
  - Inserts row into `user_saved_searches` using `get_engine().begin()` + `text()`
  - Returns `{"ok": true, "id": <new_id>}` (use `RETURNING id` on PG, `lastrowid` on SQLite)
  - `is_pg = engine.dialect.name == "postgresql"` for dialect branch
- `DELETE /searches/<int:search_id>` (login required, CSRF-exempt JSON endpoint):
  - Deletes row where `id = :id AND user_id = :uid` (user can only delete their own)
  - Returns `{"ok": true}` whether or not row existed
- Add both paths to `_PUBLIC_PATHS` frozenset in `app.py` so `require_login` does not redirect before the routes can return 401 JSON
- Both routes check `g.user` and return `{"error": "login required"}, 401` if not authenticated
- `@csrf.exempt` on both routes

## Acceptance Criteria

- [ ] `POST /searches/save` with valid JSON returns 200 `{"ok": true, "id": N}`
- [ ] `POST /searches/save` without `name` returns 400
- [ ] `DELETE /searches/1` deletes the right row (own row only)
- [ ] Both routes return 401 JSON for unauthenticated requests
- [ ] All existing tests still pass

## Hard Dependencies

- Task 084: user_saved_searches table — must be DONE

## Testing

New file `tests/test_saved_searches.py` with `auth_db` + `client` + `anon_client` fixtures (same pattern as `test_watchlist.py`). Min 5 tests covering: save returns id, save missing name, delete own, delete nonexistent is idempotent, unauthenticated returns 401.

## Suggested Commit Message

`feat: add POST /searches/save and DELETE /searches/:id routes (Task 085)`
