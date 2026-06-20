# Task 079 — Add bookmark toggle to contract list rows

**Epic:** E06  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

Add a bookmark (★/☆) toggle button to each row in the `/contracts` table so users can
add/remove contracts from their watchlist without leaving the page.

## Requirements

- In `app.py` `/contracts` route: query `user_watchlist` for the current user's bookmarked
  `internal_id` values; pass `watchlist_ids` (a Python set) to the template
- In `templates/contracts.html`:
  - Add a new `<td>` column (first column, before the checkbox) with a bookmark button
  - Button text: `★` if already bookmarked, `☆` if not; class `bm-btn`; `data-id="{{ r['internal_id'] }}"`
  - On click: JS calls `POST /watchlist/add` or `POST /watchlist/remove` depending on current state,
    then toggles the button text/class without a page reload
  - Add the JS `bookmarkToggle(btn)` function in a `<script>` block at bottom of template
  - Add a `<th>` header for the new column (empty label or "Watch")
- Do NOT add a column header sort link for the bookmark column

## Acceptance Criteria

- [ ] Each contract row has a ★/☆ button reflecting current watchlist state
- [ ] Clicking ☆ calls `/watchlist/add` and changes button to ★ without reload
- [ ] Clicking ★ calls `/watchlist/remove` and changes button to ☆ without reload
- [ ] Page renders correctly when user has no bookmarks (all ☆)
- [ ] Existing sort/filter/pagination tests still pass
- [ ] CSRF token is included in the fetch calls (read from `{{ csrf_token() }}` stored in a `<meta>` or hidden input)

## Hard Dependencies

- Task 078: watchlist routes — must be DONE

## DB Changes

None (reads user_watchlist via the route).

## API Changes

None — uses routes from Task 078.

## Frontend Changes

- `templates/contracts.html` — new column + JS

## New Dependencies

None.

## Testing

No new automated tests required (JS interaction is visual). Verify existing `test_app.py` contract tests still pass.

## Suggested Commit Message

`feat: add bookmark toggle to contract list rows (Task 079)`
