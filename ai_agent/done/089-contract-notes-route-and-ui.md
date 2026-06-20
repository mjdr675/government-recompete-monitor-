# Task 089 — Add POST /contract/:id/note route and display notes on contract detail

**Epic:** E06
**Milestone:** M3
**Sprint:** B-12
**Complexity:** S
**Status:** QUEUED

## Objective

Users can add and view private notes on contract detail pages.

## Requirements

- New `POST /contract/<internal_id>/note` route in `app.py` (login required, CSRF-exempt JSON):
  - Reads JSON body `{"body": "..."}`
  - Validates `body` non-empty (400 if missing/blank after strip)
  - Inserts row into `contract_notes` using `get_engine().begin()` + `text()`
  - Returns `{"ok": true, "id": <new_id>, "created_at": "<iso>"}` (dialect-branch for id)
  - Add `/contract/` prefix paths to `_PUBLIC_PATHS`? No — require login via `require_login` (302 is fine for this route since caller is JS; add to `_PUBLIC_PATHS` and return 401 JSON instead)
- In `templates/contract_detail.html`:
  - Below the existing detail table, add a "Notes" section
  - `GET /contract/<id>` route must also query `contract_notes WHERE user_id = :uid AND internal_id = :iid ORDER BY created_at DESC` and pass `notes` list to template
  - Display existing notes in a `<ul>` (body + timestamp)
  - Add a `<textarea>` + "Add note" button that POSTs to `/contract/<id>/note` via fetch and prepends the new note to the list without page reload
  - Notes section only rendered if `g.user`
- Add `/contract/` note route path to `_PUBLIC_PATHS` (pattern: all `/contract/*/note` paths). Use `request.path.startswith("/contract/") and request.path.endswith("/note")` check inside route instead, since wildcard paths can't be in a frozenset. Return 401 JSON if not `g.user`.

## Acceptance Criteria

- [ ] `POST /contract/C001/note` with `{"body": "test"}` from logged-in user returns 200 with id
- [ ] `POST /contract/C001/note` with empty body returns 400
- [ ] `POST /contract/C001/note` unauthenticated returns 401
- [ ] Contract detail page shows existing notes for logged-in user
- [ ] All existing tests still pass

## Hard Dependencies

- Task 088: contract_notes table — must be DONE
- Task 080: contract detail page exists — DONE

## Testing

New file `tests/test_notes.py` with auth_db + client + anon_client fixtures. Min 4 tests: add note returns ok+id, empty body returns 400, unauthenticated returns 401, GET /contract/:id includes note in response (check via HTML or route query).

## Suggested Commit Message

`feat: add contract notes route and display on detail page (Task 089)`
