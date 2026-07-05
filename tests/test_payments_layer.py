"""Tests for the payments capability layer.

All tests run without any Stripe credentials or network access —
the MockPaymentsProvider is used exclusively here.
"""
import json
import os
import pytest

from payments.providers.mock_provider import MockPaymentsProvider
from payments.interface import PaymentsService

# Captured once, at this test file's own import/collection time -- i.e.
# before any test in the suite has had a chance to run. Used only to prove
# the real, shared payments.service singleton is never reassigned by
# anything in this file (see TestServiceToggle below for why that matters).
import payments as _payments_at_collection
_SERVICE_AT_COLLECTION = _payments_at_collection.service


@pytest.fixture()
def svc():
    return MockPaymentsProvider()


class TestMockProviderInterface:
    def test_is_payments_service(self, svc):
        assert isinstance(svc, PaymentsService)

    def test_create_checkout_session_returns_url(self, svc):
        result = svc.create_checkout_session(
            price_id="price_mock",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        assert result.url.startswith("https://")
        assert result.id

    def test_retrieve_checkout_session_returns_session(self, svc):
        result = svc.retrieve_checkout_session("cs_test_123")
        assert result.id == "cs_test_123"
        assert isinstance(result.get("customer_details"), dict)

    def test_create_billing_portal_session_returns_url(self, svc):
        result = svc.create_billing_portal_session(
            customer_id="cus_mock", return_url="https://example.com/"
        )
        assert result.url.startswith("https://")

    def test_construct_webhook_event_parses_json(self, svc):
        payload = json.dumps({"type": "checkout.session.completed", "data": {}}).encode()
        event = svc.construct_webhook_event(payload, sig="sig_ignored", secret="sec_ignored")
        assert event["type"] == "checkout.session.completed"

    def test_construct_webhook_event_raises_value_error_on_bad_json(self, svc):
        with pytest.raises(ValueError, match="Invalid JSON"):
            svc.construct_webhook_event(b"not-json", sig="", secret="")

    def test_checkout_session_is_deterministic(self, svc):
        a = svc.create_checkout_session("price_1", "https://ok", "https://cancel")
        b = svc.create_checkout_session("price_2", "https://ok2", "https://cancel2")
        assert a.id == b.id  # mock always returns the same sentinel

    def test_billing_portal_session_is_deterministic(self, svc):
        a = svc.create_billing_portal_session("cus_a", "https://r1")
        b = svc.create_billing_portal_session("cus_b", "https://r2")
        assert a.url == b.url


class TestServiceToggle:
    def test_stripe_disabled_gives_mock(self, monkeypatch):
        # Deliberately does NOT use importlib.reload(pay_mod). reload() runs
        # payments/__init__.py's module-level code again, including
        # `service = _build_service()` -- REASSIGNING the shared, global
        # `payments.service` singleton that app.py's real request handling
        # imports and uses. monkeypatch.setenv's own reversion happens in
        # fixture teardown, AFTER this test function's body returns -- so a
        # same-function "restore" reload (as this test used to do) still
        # runs while the monkeypatched env var is in effect, builds ANOTHER
        # MockPaymentsProvider, and never restores the real
        # StripePaymentsProvider. Every later test in the same process then
        # silently gets MockPaymentsProvider.construct_webhook_event's plain
        # dict instead of a genuine stripe.Event from real signature
        # verification (this was a full-suite-only failure in
        # tests/test_stripe_webhook_and_fallback_e2e.py, invisible when that
        # file ran alone -- see STRIPE_TEST_POLLUTION_FIX.md).
        #
        # Testing `_build_service()` directly, with only the module-level
        # STRIPE_ENABLED attribute monkeypatched (auto-reverted, ordinary
        # attribute patch, not a module reload), exercises the exact same
        # branch without ever touching the shared `payments.service` global.
        import payments as pay_mod
        from payments.providers.mock_provider import MockPaymentsProvider

        monkeypatch.setattr(pay_mod, "STRIPE_ENABLED", False)
        assert isinstance(pay_mod._build_service(), MockPaymentsProvider)

    def test_stripe_enabled_gives_stripe_provider(self, monkeypatch):
        import payments as pay_mod
        from payments.providers.stripe_provider import StripePaymentsProvider

        monkeypatch.setattr(pay_mod, "STRIPE_ENABLED", True)
        assert isinstance(pay_mod._build_service(), StripePaymentsProvider)

    def test_stripe_enabled_flag_is_bool(self):
        import payments as pay_mod
        assert isinstance(pay_mod.STRIPE_ENABLED, bool)

    def test_service_singleton_is_untouched_by_this_class(self):
        """Guards against a regression back to the reload-based pollution:
        the real, shared payments.service singleton must be the exact same
        object it was at collection time, regardless of what ran above in
        this test class."""
        import payments as pay_mod
        assert pay_mod.service is _SERVICE_AT_COLLECTION
