# Task 130 — Add POST /billing/portal route

**Epic:** E10
**Milestone:** M3
**Sprint:** F-2
**Complexity:** S
**Status:** QUEUED

## Objective

Let authenticated users open the Stripe Customer Portal directly from the app to manage
their subscription (upgrade, downgrade, cancel, update payment method) without contacting
support.

## Requirements

- In `app.py` (or a `routes/billing.py` blueprint), add:
  ```python
  @app.route("/billing/portal", methods=["POST"])
  @login_required
  def billing_portal():
  ```
  - Look up `users.stripe_customer_id` for the current user.
  - If `stripe_customer_id IS NULL`: flash "No billing account found." and redirect to
    `/subscribe`.
  - Otherwise: create a Stripe Customer Portal session:
    ```python
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=url_for("dashboard", _external=True),
    )
    return redirect(session.url)
    ```
  - Use `STRIPE_SECRET_KEY` from `os.environ`.
- Return `302` to the Stripe portal URL on success.

## Acceptance Criteria

- [ ] POST `/billing/portal` with authenticated user + `stripe_customer_id` → redirect to Stripe portal URL
- [ ] POST with no `stripe_customer_id` → redirect to `/subscribe` with flash message
- [ ] Route requires authentication; anonymous POST → 302 to `/login`
- [ ] Stripe API call mocked in tests (no live Stripe calls)

## Hard Dependencies

- Task 122: Stripe Customer Portal enabled (external) — must be DONE
- Task 123: stripe_customer_id column — must be DONE

## DB Changes

Reads `users.stripe_customer_id`.

## API Changes

New route: `POST /billing/portal`.

## Frontend Changes

None (nav link added in Task 131).

## New Dependencies

`stripe` package already in `requirements.txt`.

## Testing

Add tests to `tests/test_billing.py` (new file):
- `test_billing_portal_redirects_to_stripe`: monkeypatch `stripe.billing_portal.Session.create`
  to return `Mock(url="https://billing.stripe.com/test")`; POST with authenticated user
  who has `stripe_customer_id`; assert 302 to stripe URL.
- `test_billing_portal_no_customer_id_redirects_subscribe`: user has `stripe_customer_id=NULL`;
  POST; assert 302 to `/subscribe`.
- `test_billing_portal_requires_auth`: anonymous POST; assert 302 to `/login`.

## Suggested Commit Message

`feat: add POST /billing/portal route for Stripe Customer Portal (Task 130)`
