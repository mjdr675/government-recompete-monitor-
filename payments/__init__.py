"""Payments capability layer.

Usage in business logic:
    import payments
    session = payments.service.create_checkout_session(price_id, success_url, cancel_url)

The active provider is selected once at import time:
  - STRIPE_ENABLED=false → MockPaymentsProvider (CI-safe, no credentials required)
  - STRIPE_ENABLED=true (default) → StripePaymentsProvider (requires STRIPE_SECRET_KEY)
"""
import os

from payments.interface import PaymentsService

STRIPE_ENABLED: bool = os.getenv("STRIPE_ENABLED", "true").lower() not in (
    "0",
    "false",
    "no",
    "off",
)


def _build_service() -> PaymentsService:
    if STRIPE_ENABLED:
        from payments.providers.stripe_provider import StripePaymentsProvider
        return StripePaymentsProvider()
    from payments.providers.mock_provider import MockPaymentsProvider
    return MockPaymentsProvider()


service: PaymentsService = _build_service()
