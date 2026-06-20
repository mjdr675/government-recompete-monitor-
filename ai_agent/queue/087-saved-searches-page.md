# Task 087 — Add GET /searches page listing saved searches

**Epic:** E06
**Milestone:** M3
**Sprint:** B-10
**Complexity:** S
**Status:** QUEUED

## Objective

Dedicated page where users can view and delete their saved searches, and re-run them.

## Requirements

- New `GET /searches` route in `app.py` (login required via `require_login` before_request):
  - Queries `SELECT * FROM user_saved_searches WHERE user_id = :uid ORDER BY created_at DESC`
  - Parses `query_params_json` via `json.loads()` for each row
  - Builds a `/contracts?...` URL from the params dict for each row (use `urllib.parse.urlencode`)
  - Passes `searches` list and `count` to template
- New `templates/searches.html` extending `base.html`:
  - Table: Name | Filters summary | Saved | Actions
  - "Run" link → `/contracts?<params>`
  - "Delete" button → calls `DELETE /searches/<id>` via fetch, removes row from DOM on success
  - Empty state: "No saved searches yet."
- Add `<a href="/searches">Saved Searches</a>` to nav in `templates/base.html` (after Watchlist link)

## Acceptance Criteria

- [ ] `GET /searches` returns 200 for logged-in user
- [ ] `GET /searches` redirects to `/login` for unauthenticated user
- [ ] "Saved Searches" link appears in nav
- [ ] Empty state shown when no saved searches exist

## Hard Dependencies

- Task 085: /searches/save route — must be DONE

## Testing

Add 2 tests to `tests/test_saved_searches.py`: `test_searches_page_returns_200`, `test_searches_page_redirects_when_not_logged_in`.

## Suggested Commit Message

`feat: add GET /searches page for saved searches (Task 087)`
