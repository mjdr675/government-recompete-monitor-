# Task 136 — Build /subscribe page with tier comparison

**Epic:** E10
**Milestone:** M3
**Sprint:** F-14
**Complexity:** S
**Status:** QUEUED

## Objective

Give users a clear, self-serve page to pick a plan and start a Stripe checkout session.
This is the destination of every trial gate redirect and trial expiry email CTA.

## Requirements

- In `app.py` (or `routes/billing.py`), add:
  ```python
  @app.route("/subscribe", methods=["GET"])
  def subscribe():
  ```
  - Accessible without authentication (so expired-trial users who are logged out can see it).
  - Pass plan details to the template: name, price, feature list, Stripe price ID.
  - Define plan data inline or in `plans.py` (use the feature sets from Task 129).
- Create `templates/subscribe.html` extending `base.html`:
  - Three-column tier comparison: **Starter** ($99/mo), **Professional** ($199/mo), **Team** ($299/mo).
  - Feature list per tier using the `PLAN_FEATURES` dict from Task 129.
  - "Subscribe" button per tier that POSTs to the existing Stripe checkout route
    (already integrated) with the appropriate `price_id`.
  - If user is authenticated and in trial: show "Your trial ends on {{ trial_ends_at }}"
    banner at the top.
  - If user already has `subscription_status='active'`: show "You already have an active
    subscription." with a link to the billing portal.
- Add `/subscribe` to `_PUBLIC_PATHS`.

## Acceptance Criteria

- [ ] GET `/subscribe` returns 200 for anonymous users
- [ ] GET `/subscribe` returns 200 for authenticated users
- [ ] All three tiers and prices displayed
- [ ] Active subscribers see "already subscribed" message instead of plan grid
- [ ] Trial users see trial-end date banner
- [ ] All existing tests still pass

## Hard Dependencies

- Task 129: plan enforcement feature flags (PLAN_FEATURES) — must be DONE
- Task 124: trial_ends_at column — must be DONE (for trial banner)

## DB Changes

None (reads `users.trial_ends_at`, `users.subscription_status`).

## API Changes

New route: `GET /subscribe`.

## Frontend Changes

New template: `templates/subscribe.html`.

## New Dependencies

None.

## Testing

Add tests to `tests/test_billing.py`:
- `test_subscribe_page_anonymous_200`: anonymous GET `/subscribe`; assert 200.
- `test_subscribe_page_authenticated_200`: authenticated GET; assert 200, "Starter" in response.
- `test_subscribe_page_active_user_sees_already_subscribed`: user with `subscription_status='active'`;
  GET `/subscribe`; assert "already have an active subscription" in response.
- `test_subscribe_page_trial_user_sees_trial_banner`: trialing user; GET; assert `trial_ends_at`
  date appears in response.

## Suggested Commit Message

`feat: build /subscribe page with tier comparison (Task 136)`
