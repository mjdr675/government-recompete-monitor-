# Task 086 — Add "Save this search" button to contracts filter bar

**Epic:** E06
**Milestone:** M3
**Sprint:** B-9
**Complexity:** S
**Status:** QUEUED

## Objective

Let users save the current filter state from the contracts page with one click.

## Requirements

- In `templates/contracts.html`:
  - After the Filter/Reset buttons in the `<form>`, add a "Save this search" button (type="button", not submit)
  - On click: prompt user for a name via `window.prompt("Name this search:", "")`; if empty or cancelled, abort
  - Serialize current URL query params from `window.location.search` into a params object
  - `POST /searches/save` with JSON `{"name": "<name>", "params": <params object>}`; use `meta[name="csrf-token"]` for the token
  - On success: show a brief inline confirmation ("Search saved") for 2 seconds, then clear it
  - On failure: alert the user
- Button only visible to logged-in users: wrap with `{% if g.user %}`

## Acceptance Criteria

- [ ] "Save this search" button appears on /contracts when logged in
- [ ] Button is absent for unauthenticated users
- [ ] Clicking and providing a name POSTs to /searches/save and shows confirmation
- [ ] All existing tests still pass (no new tests required — UI-only change)

## Hard Dependencies

- Task 085: /searches/save route — must be DONE

## Testing

No new automated tests required (frontend-only JS interaction). Existing suite must still pass.

## Suggested Commit Message

`feat: add "Save this search" button to contracts filter bar (Task 086)`
