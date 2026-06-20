# Task 137 — Polish /success and /cancel pages

**Epic:** E10
**Milestone:** M3
**Sprint:** F-15
**Complexity:** S
**Status:** QUEUED

## Objective

Replace the placeholder `/success` and `/cancel` pages with branded layouts that give
users a clear next step after Stripe checkout completes or is abandoned.

## Requirements

**`/success` page** (`templates/success.html`):
- Heading: "You're all set!"
- Body: "Your subscription is now active. Welcome to Gov Recompete Monitor."
  - If user is authenticated, personalize: "Welcome, {{ user_first_name }}!"
- Next steps list: "Go to your dashboard", "Set up expiration alerts", "Bookmark your
  first contract"
- Primary CTA: "Go to Dashboard" → `/dashboard`
- On load (or via Stripe webhook — not here): set `subscription_status = 'active'` for
  the user. Note: authoritative status update happens via webhook (Tasks 127/128); this
  page should only show a confirmation, not write to DB.

**`/cancel` page** (`templates/cancel.html`):
- Heading: "No worries — your trial is still active"
- Body: "You can subscribe any time before your trial ends on {{ trial_ends_at }}."
  (Show generic message if user is not authenticated.)
- CTA: "Return to dashboard" → `/dashboard`
- Secondary: "View plans" → `/subscribe`

**Route changes in `app.py`**:
- `/success` and `/cancel` are already routed; update them to pass user context if
  authenticated (`user_first_name`, `trial_ends_at`).

## Acceptance Criteria

- [ ] GET `/success` returns 200 with "You're all set!" heading
- [ ] GET `/cancel` returns 200 with "No worries" heading
- [ ] Authenticated user sees personalized name on `/success`
- [ ] Trial end date visible on `/cancel` for authenticated trial users
- [ ] Both pages accessible without auth (Stripe may redirect before session exists)
- [ ] All existing tests still pass

## Hard Dependencies

- Task 124: trial_ends_at column (for cancel page context) — must be DONE
- Task 136: /subscribe page (cancel page links to it) — must be DONE

## DB Changes

None (reads only; status update authoritative from webhook).

## API Changes

Updates existing `GET /success` and `GET /cancel` routes.

## Frontend Changes

Rewrites `templates/success.html` and `templates/cancel.html`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_billing.py`:
- `test_success_page_returns_200`: anonymous GET `/success`; assert 200, "all set" in response.
- `test_success_page_authenticated_shows_name`: authenticated GET; assert username in response.
- `test_cancel_page_returns_200`: anonymous GET `/cancel`; assert 200, "No worries" in response.
- `test_cancel_page_shows_trial_date`: authenticated trial user; GET `/cancel`; assert
  trial_ends_at date in response.

## Suggested Commit Message

`feat: polish /success and /cancel pages with next-step guidance (Task 137)`
