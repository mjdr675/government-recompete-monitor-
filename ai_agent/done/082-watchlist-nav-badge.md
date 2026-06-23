# Task 082 — Add watchlist count badge to nav

**Epic:** E06  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

Show the number of bookmarked contracts next to the "Watchlist" nav link so users
can see at a glance how many they have saved.

## Requirements

- In `app.py`: add a `before_request` hook (or update the existing one) that, for logged-in
  users, queries `COUNT(*) FROM user_watchlist WHERE user_id = :uid` and sets `g.watchlist_count`
- In `templates/base.html`: update the Watchlist nav link to show the count:
  `Watchlist ({{ g.watchlist_count }})` — show nothing if 0, or always show the number
- Use `get_engine()` + `text()` — single lightweight query, runs on every page load for logged-in users

## Acceptance Criteria

- [ ] Logged-in user with 0 bookmarks sees "Watchlist (0)" or "Watchlist" in nav
- [ ] Logged-in user with 3 bookmarks sees "Watchlist (3)" in nav
- [ ] Count updates correctly after adding/removing bookmarks (page reload reflects correct count)
- [ ] Unauthenticated users do not trigger the watchlist count query
- [ ] All existing tests still pass

## Hard Dependencies

- Task 077: user_watchlist table — must be DONE
- Task 081: Watchlist nav link — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

- `templates/base.html` — nav link updated

## New Dependencies

None.

## Testing

No new tests required. Existing test suite must pass (g.watchlist_count gracefully absent for unauthenticated test clients).

## Suggested Commit Message

`feat: add watchlist count badge to nav (Task 082)`
