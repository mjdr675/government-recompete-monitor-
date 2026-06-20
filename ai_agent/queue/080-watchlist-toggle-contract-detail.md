# Task 080 — Add bookmark toggle to contract detail page

**Epic:** E06  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

Add a bookmark button to the `/contract/<id>` detail page, consistent with the list toggle.

## Requirements

- In `app.py` `/contract/<internal_id>` route: check if `internal_id` is in the current
  user's watchlist; pass `is_bookmarked` (bool) to the template
- In `templates/contract_detail.html`:
  - Add a bookmark button near the page title: `★ Remove from watchlist` or `☆ Add to watchlist`
  - Same `bookmarkToggle()` JS pattern as Task 079 (inline script)
  - Include the CSRF token in the fetch call

## Acceptance Criteria

- [ ] Contract detail page shows ★ button when already bookmarked, ☆ when not
- [ ] Clicking the button toggles state and updates button label without reload
- [ ] `app.py` contract_detail route checks `user_watchlist` for current user
- [ ] Existing contract detail tests still pass

## Hard Dependencies

- Task 078: watchlist routes — must be DONE
- Task 079: bookmark toggle JS pattern established

## DB Changes

None.

## API Changes

None.

## Frontend Changes

- `templates/contract_detail.html` — bookmark button + JS

## New Dependencies

None.

## Testing

No new automated tests. Existing `test_app.py` contract detail tests must pass.

## Suggested Commit Message

`feat: add bookmark toggle to contract detail page (Task 080)`
