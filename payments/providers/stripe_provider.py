"""Stripe-backed payments provider.

Imported only when STRIPE_ENABLED=true. Never import this from business logic.
"""
import stripe

from payments.interface import PaymentsService


class StripePaymentsProvider(PaymentsService):
    def create_checkout_session(self, price_id, success_url, cancel_url, **kwargs):
        return stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            **kwargs,
        )

    def retrieve_checkout_session(self, session_id):
        return stripe.checkout.Session.retrieve(session_id)

    def create_billing_portal_session(self, customer_id, return_url):
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

    def construct_webhook_event(self, payload, sig, secret):
        try:
            return stripe.Webhook.construct_event(payload, sig, secret)
        except stripe.error.SignatureVerificationError as exc:
            raise ValueError(f"Stripe signature verification failed: {exc}") from exc
