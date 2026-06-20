# Task 074 — Enforce Stripe webhook signature verification

**Epic:** E05  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

`stripe_webhook()` in `app.py` currently has a fallback path: if `STRIPE_WEBHOOK_SECRET`
is not set, it constructs a Stripe event from the raw JSON without verifying the signature.
This means a malicious actor can send fake webhook events (e.g., fake `checkout.session.completed`)
and the app will process them. Remove the fallback — if the secret is missing, return 400.

## Requirements

- In `stripe_webhook()`, remove the `else` branch that calls
  `stripe.Event.construct_from(request.get_json(force=True), stripe.api_key)`
- Replace with: if `STRIPE_WEBHOOK_SECRET` is not set, log a warning and return `"Webhook secret not configured", 400`
- The `try/except (stripe.error.SignatureVerificationError, ValueError)` block remains unchanged
- Add a startup warning (log `WARNING`) in `app.py` at startup if `STRIPE_WEBHOOK_SECRET` is unset, alongside the existing `_warn_if_ephemeral_db()` pattern

## Acceptance Criteria

- [ ] If `STRIPE_WEBHOOK_SECRET` env var is not set, `POST /stripe/webhook` returns 400
- [ ] A startup `WARNING` log line appears if `STRIPE_WEBHOOK_SECRET` is not configured
- [ ] Valid signed Stripe events (with correct secret) still return 200 and trigger HubSpot sync
- [ ] Invalid signatures still return 400
- [ ] No `stripe.Event.construct_from(...)` call remains in the webhook handler
- [ ] New test: POST to `/stripe/webhook` with no `STRIPE_WEBHOOK_SECRET` configured — assert 400

## Hard Dependencies

- Task 071: CSRF infrastructure — recommended first (Sprint A is done as a batch)

## DB Changes

None.

## API Changes

- `POST /stripe/webhook` — now returns 400 if `STRIPE_WEBHOOK_SECRET` is missing (previously processed the event unsafely)

## Frontend Changes

None.

## New Dependencies (requirements.txt)

None.

## Testing

Add to `tests/test_app.py`:
- `test_webhook_rejects_without_secret`: monkeypatch `STRIPE_WEBHOOK_SECRET = None`, POST to `/stripe/webhook`, assert 400
- `test_webhook_rejects_bad_signature`: existing test pattern (if present) — verify unchanged behavior

## Documentation

Update `docs/ARCHITECTURE.md` — add `STRIPE_WEBHOOK_SECRET` to the required environment
variables table.

## Suggested Commit Message

`fix: enforce Stripe webhook signature verification — reject unsigned events (Task 074)`
