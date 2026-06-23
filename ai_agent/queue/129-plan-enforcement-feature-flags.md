# Task 129 — Add plan enforcement feature flags per tier

**Epic:** E10
**Milestone:** M3
**Sprint:** F-7
**Complexity:** S
**Status:** QUEUED

## Objective

Define which features each subscription tier enables, and provide a decorator and helper
so routes and templates can gate access without hardcoding tier logic everywhere.

## Requirements

- Create `plans.py` at the project root (next to `app.py`):
  ```python
  PLAN_FEATURES = {
      "starter": {"watchlist", "saved_searches", "csv_export", "email_alerts"},
      "professional": {"watchlist", "saved_searches", "csv_export", "email_alerts",
                       "contract_notes", "data_freshness_api"},
      "team": {"watchlist", "saved_searches", "csv_export", "email_alerts",
               "contract_notes", "data_freshness_api", "billing_portal"},
      "trialing": {"watchlist", "saved_searches", "csv_export", "email_alerts"},
      "inactive": set(),
      "cancelled": set(),
  }

  def get_user_plan(user: dict) -> str:
      """Return the user's current plan key based on subscription_status."""
      return user.get("subscription_status", "inactive")

  def user_has_feature(user: dict, feature: str) -> bool:
      plan = get_user_plan(user)
      return feature in PLAN_FEATURES.get(plan, set())
  ```
- Add a Flask decorator `plan_required(feature)` in `plans.py`:
  - If user not logged in: redirect to `/login`.
  - If user lacks `feature`: return 403 with a brief "Upgrade your plan" message.
- Import and use `user_has_feature` in Jinja templates via `app.jinja_env.globals`.

## Acceptance Criteria

- [ ] `PLAN_FEATURES` covers all five status values
- [ ] `user_has_feature` returns correct bool for each tier
- [ ] `@plan_required("csv_export")` on a route blocks `inactive` users with 403
- [ ] `@plan_required("csv_export")` allows `trialing` users through
- [ ] All existing tests still pass

## Hard Dependencies

- Task 123: subscription_status column — must be DONE

## DB Changes

None.

## API Changes

None (decorator available for future routes).

## Frontend Changes

`user_has_feature` exposed to Jinja2 globals for template-level gating.

## New Dependencies

None (new `plans.py` module, no third-party packages).

## Testing

Add tests to `tests/test_plans.py` (new file):
- `test_starter_has_watchlist`: `user_has_feature({"subscription_status": "starter"}, "watchlist")` → True.
- `test_inactive_has_no_features`: `user_has_feature({"subscription_status": "inactive"}, "watchlist")` → False.
- `test_trialing_has_watchlist`: `trialing` → True for `watchlist`.
- `test_plan_required_decorator_blocks_inactive`: register route with `@plan_required("csv_export")`; GET with `inactive` user → 403.
- `test_plan_required_decorator_allows_trialing`: `trialing` user → 200.

## Suggested Commit Message

`feat: add plan enforcement feature flags and plan_required decorator (Task 129)`
