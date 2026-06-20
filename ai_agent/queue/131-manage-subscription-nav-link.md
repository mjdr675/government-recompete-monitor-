# Task 131 — Add "Manage Subscription" link to nav

**Epic:** E10
**Milestone:** M3
**Sprint:** F-3
**Complexity:** XS
**Status:** QUEUED

## Objective

Surface the billing portal link in the navigation so authenticated users can reach it
without hunting through settings.

## Requirements

- In `templates/base.html` (or the navigation partial), inside the authenticated-user
  navigation section, add a form that POSTs to `/billing/portal`:
  ```html
  <form action="/billing/portal" method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button type="submit" class="nav-link-button">Manage Subscription</button>
  </form>
  ```
  (A `<form>` with a styled `<button>` is needed because `/billing/portal` is a POST
  route. Do not use `<a href>` which would issue a GET.)
- The link should only be visible to authenticated users (already inside the logged-in
  nav block).
- Style the button to match existing nav links (no background, text color consistent with
  nav items).

## Acceptance Criteria

- [ ] "Manage Subscription" is visible in the nav when authenticated
- [ ] Clicking it submits a POST to `/billing/portal`
- [ ] CSRF token is included in the form
- [ ] Link is absent for anonymous users
- [ ] All existing nav-related tests still pass

## Hard Dependencies

- Task 130: /billing/portal route — must be DONE
- Task 071: CSRF infrastructure — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

Modify `templates/base.html` navigation section.

## New Dependencies

None.

## Testing

Add tests to `tests/test_billing.py`:
- `test_manage_subscription_nav_visible_authenticated`: GET `/dashboard` as authenticated user;
  assert "Manage Subscription" in response data.
- `test_manage_subscription_nav_absent_anonymous`: GET `/dashboard` as anonymous user
  (expect redirect); or GET a public page; assert "Manage Subscription" not in response.

## Suggested Commit Message

`feat: add Manage Subscription nav link POSTing to /billing/portal (Task 131)`
