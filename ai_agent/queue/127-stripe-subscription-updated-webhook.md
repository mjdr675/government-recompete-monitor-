# Task 127 — Handle customer.subscription.updated Stripe webhook

**Epic:** E10
**Milestone:** M3
**Sprint:** F-5
**Complexity:** S
**Status:** QUEUED

## Objective

Keep `users.subscription_status` in sync with Stripe whenever a subscription is upgraded,
downgraded, or changed. This ensures the trial gate (Task 126) and plan enforcement
(Task 129) reflect the customer's current billing state.

## Requirements

- In the existing Stripe webhook handler in `app.py` (or `routes/stripe_webhook.py`),
  add a branch for `event['type'] == 'customer.subscription.updated'`:
  ```python
  subscription = event['data']['object']
  stripe_customer_id = subscription['customer']
  new_status = subscription['status']  # e.g., 'active', 'past_due', 'trialing'
  update_subscription_status(stripe_customer_id, new_status)
  ```
  - Map Stripe statuses directly to `subscription_status` (no translation needed;
    Stripe's values match the column's allowed values).
- Import `update_subscription_status` from `users.py` (added in Task 123).
- Return `200 {"received": True}` after processing (consistent with existing webhook handler).

## Acceptance Criteria

- [ ] `customer.subscription.updated` event updates `users.subscription_status` correctly
- [ ] Unknown `stripe_customer_id` logs a warning and returns 200 (do not 500)
- [ ] Existing webhook handler tests still pass
- [ ] Webhook signature verification (Task 074) is not bypassed

## Hard Dependencies

- Task 123: subscription_status column + `update_subscription_status()` — must be DONE
- Task 074: Stripe webhook signature enforcement — must be DONE

## DB Changes

Updates `users.subscription_status` via `update_subscription_status()`.

## API Changes

Extends existing `POST /stripe/webhook` handler.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_stripe_webhook.py` (or existing webhook test file):
- `test_subscription_updated_sets_active`: send mock `customer.subscription.updated`
  event with `status='active'` and known `stripe_customer_id`; assert DB updated.
- `test_subscription_updated_sets_past_due`: same with `status='past_due'`; assert DB.
- `test_subscription_updated_unknown_customer_returns_200`: unknown `stripe_customer_id`;
  assert 200 returned and no exception.

## Suggested Commit Message

`feat: handle customer.subscription.updated Stripe webhook (Task 127)`
