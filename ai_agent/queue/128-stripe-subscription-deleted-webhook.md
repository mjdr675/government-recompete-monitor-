# Task 128 — Handle customer.subscription.deleted Stripe webhook

**Epic:** E10
**Milestone:** M3
**Sprint:** F-6
**Complexity:** S
**Status:** QUEUED

## Objective

Downgrade a user to the free/inactive tier when their subscription is cancelled in Stripe,
so they lose access to paid features immediately without requiring a manual update.

## Requirements

- In the existing Stripe webhook handler, add a branch for
  `event['type'] == 'customer.subscription.deleted'`:
  ```python
  subscription = event['data']['object']
  stripe_customer_id = subscription['customer']
  update_subscription_status(stripe_customer_id, 'cancelled')
  ```
- After setting status to `'cancelled'`, log `INFO` with the `stripe_customer_id`
  (masked: show only last 4 chars) for audit purposes.
- Return `200 {"received": True}`.
- Do not delete the user row — only change status. The trial gate (Task 126) will redirect
  them to `/subscribe` on next login.

## Acceptance Criteria

- [ ] `customer.subscription.deleted` event sets `subscription_status = 'cancelled'`
- [ ] User row is not deleted
- [ ] Unknown `stripe_customer_id` logs a warning and returns 200
- [ ] Existing webhook tests and signature verification still work

## Hard Dependencies

- Task 123: subscription_status column + `update_subscription_status()` — must be DONE
- Task 127: subscription.updated handler (establishes the webhook branching pattern) — must be DONE

## DB Changes

Updates `users.subscription_status` to `'cancelled'`.

## API Changes

Extends existing `POST /stripe/webhook` handler.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_stripe_webhook.py`:
- `test_subscription_deleted_sets_cancelled`: mock `customer.subscription.deleted` event;
  assert `subscription_status = 'cancelled'` in DB.
- `test_subscription_deleted_does_not_delete_user`: after event, user row still exists.
- `test_subscription_deleted_unknown_customer_returns_200`: unknown customer; assert 200.

## Suggested Commit Message

`feat: handle customer.subscription.deleted Stripe webhook (Task 128)`
