"""Abstract interface for the payments capability.

Business logic imports only from this module — never from a provider directly.
"""
from abc import ABC, abstractmethod
from typing import Any


class PaymentsService(ABC):
    @abstractmethod
    def create_checkout_session(
        self, price_id: str, success_url: str, cancel_url: str, **kwargs: Any
    ) -> Any:
        """Return an object with a `.url` attribute for the Stripe-hosted checkout page."""

    @abstractmethod
    def retrieve_checkout_session(self, session_id: str) -> Any:
        """Return a dict-like object with `customer_details`, `customer`, `id`."""

    @abstractmethod
    def create_billing_portal_session(self, customer_id: str, return_url: str) -> Any:
        """Return an object with a `.url` attribute for the Stripe billing portal."""

    @abstractmethod
    def construct_webhook_event(self, payload: bytes, sig: str, secret: str) -> Any:
        """Parse and verify a webhook payload.

        Raises ValueError for invalid signatures or bad payloads so callers need
        only catch ValueError — no Stripe-specific exception types leak out.
        """
