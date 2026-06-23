# Task 081 — Add GET /watchlist page

**Epic:** E06  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

Add a `/watchlist` page where users can see all their bookmarked contracts in one place,
with the same key columns as the contract list.

## Requirements

- In `app.py`: add `GET /watchlist` route (login required)
  - Query `user_watchlist` JOIN `contracts` for the current user's bookmarked contracts
  - Order by `days_remaining ASC NULLS LAST`
  - Pass `contracts` list and `count` to template
- Create `templates/watchlist.html` extending `base.html`:
  - Page title: "My Watchlist"
  - Show count: "X contracts bookmarked"
  - Table with columns: internal_id link, vendor, agency, value, end_date, days_remaining, priority, recompete_score, and ★ remove button
  - Remove button calls `POST /watchlist/remove` then removes the row from DOM (no reload)
  - If empty: show "No contracts bookmarked yet. Browse contracts to add some."
- Add "Watchlist" link to `templates/base.html` nav

## Acceptance Criteria

- [ ] `GET /watchlist` returns 200 and shows bookmarked contracts
- [ ] Empty state shows helpful message (not a blank page)
- [ ] Removing a contract from this page removes it from the list without reload
- [ ] "Watchlist" appears in the nav on all pages
- [ ] Tests: GET /watchlist returns 200 when logged in; returns 302 to /login when not logged in

## Hard Dependencies

- Task 077: user_watchlist table — must be DONE
- Task 078: watchlist routes — must be DONE

## DB Changes

None.

## API Changes

- `GET /watchlist` — new route

## Frontend Changes

- `templates/watchlist.html` — new template
- `templates/base.html` — nav link added

## New Dependencies

None.

## Testing

Add to `tests/test_watchlist.py`: `test_watchlist_page_returns_200`, `test_watchlist_page_redirects_when_not_logged_in`.

## Suggested Commit Message

`feat: add GET /watchlist page with bookmarked contracts (Task 081)`
