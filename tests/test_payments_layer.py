"""Tests for the payments capability layer.

All tests run without any Stripe credentials or network access —
the MockPaymentsProvider is used exclusively here.
"""
import json
import os
import pytest

from payments.providers.mock_provider import MockPaymentsProvider
from payments.interface import PaymentsService


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
        monkeypatch.setenv("STRIPE_ENABLED", "false")
        import importlib
        import payments as pay_mod
        importlib.reload(pay_mod)
        from payments.providers.mock_provider import MockPaymentsProvider
        assert isinstance(pay_mod.service, MockPaymentsProvider)
        # restore
        importlib.reload(pay_mod)

    def test_stripe_enabled_flag_is_bool(self):
        import payments as pay_mod
        assert isinstance(pay_mod.STRIPE_ENABLED, bool)
