# Task 122 — Enable Stripe Customer Portal in Stripe dashboard

**Epic:** E10
**Milestone:** M3
**Sprint:** F-1
**Complexity:** XS
**Status:** QUEUED

## Objective

Configure the Stripe Customer Portal so subscribers can upgrade, downgrade, cancel, and
view invoices without contacting support. This is an external configuration step with no
code changes — required before Task 130 (the `/billing/portal` route) can be tested.

## Requirements

This task is DevOps only — no application code changes.

1. Log in to the Stripe dashboard → Billing → Customer portal.
2. Enable the portal.
3. Configure allowed actions:
   - Allow customers to cancel subscriptions: **Yes**
   - Allow customers to update payment methods: **Yes**
   - Allow customers to view invoice history: **Yes**
   - Allow plan upgrades/downgrades: **Yes** (select the Starter/Professional/Team price IDs)
4. Set the default return URL to `https://<app>.railway.app/dashboard`.
5. Save configuration.
6. Document the portal configuration ID (e.g., `bpc_xxx`) in `docs/OPERATIONS.md` under
   a new "Stripe Configuration" section.

## Acceptance Criteria

- [ ] Stripe Customer Portal is enabled in the Stripe dashboard
- [ ] Upgrade and cancellation flows are permitted
- [ ] Default return URL is set to the production dashboard URL
- [ ] Portal configuration ID is noted in `docs/OPERATIONS.md`

## Hard Dependencies

- Task 111: docs/OPERATIONS.md created — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

No automated test for this task. Verified manually in Task 130 when the billing portal
route is implemented and a portal session is created successfully.

## Suggested Commit Message

`docs: record Stripe Customer Portal config ID in OPERATIONS.md (Task 122)`
