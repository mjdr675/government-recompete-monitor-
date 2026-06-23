"""Deterministic in-memory payments provider for CI and offline use.

No network calls, no credentials required. Returns predictable objects that
satisfy the same interface callers expect from the Stripe provider.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from payments.interface import PaymentsService


@dataclass
class _CheckoutSession:
    url: str
    id: str
    customer: str = ""
    customer_email: str = ""
    customer_details: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass
class _PortalSession:
    url: str


class MockPaymentsProvider(PaymentsService):
    """Deterministic mock — safe for CI, produces stable outputs across runs."""

    def create_checkout_session(self, price_id, success_url, cancel_url, **kwargs):
        return _CheckoutSession(
            url="https://mock.stripe.com/checkout/cs_mock_123",
            id="cs_mock_123",
        )

    def retrieve_checkout_session(self, session_id):
        return _CheckoutSession(
            url="https://mock.stripe.com/success",
            id=session_id,
            customer_details={"email": "", "name": ""},
        )

    def create_billing_portal_session(self, customer_id, return_url):
        return _PortalSession(url="https://mock.stripe.com/portal")

    def construct_webhook_event(self, payload, sig, secret):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON webhook payload: {exc}") from exc
