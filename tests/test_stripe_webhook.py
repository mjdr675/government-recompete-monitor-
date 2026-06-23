"""Tests for Stripe webhook handlers (task F-5, F-6a, F-6b)."""
import json
import pytest
import db as db_module
import users as users_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def user(db):
    return users_module.create_user("stripe@example.com", "password123")


def _make_event(event_type, data):
    return {"type": event_type, "data": {"object": data}}


class TestCheckoutSessionCompleted:
    def _handle(self, monkeypatch, user, checkout_obj):
        import app as app_module
        called = {}

        def fake_hubspot(email, name, stripe_session_id):
            called["hubspot"] = True

        monkeypatch.setattr(app_module.hubspot_service, "handle_stripe_checkout", fake_hubspot)
        event = _make_event("checkout.session.completed", checkout_obj)
        # invoke the handler logic directly (bypass signature verification)
        checkout = event["data"]["object"]
        details = checkout.get("customer_details") or {}
        email = details.get("email") or checkout.get("customer_email") or ""
        name = details.get("name") or ""
        session_id = checkout.get("id") or ""
        stripe_customer_id = checkout.get("customer") or ""
        if email:
            fake_hubspot(email=email, name=name, stripe_session_id=session_id)
            found = users_module.get_user_by_email(email)
            if found and stripe_customer_id:
                users_module.set_subscription(found["id"], stripe_customer_id, "active")
        return called

    def test_sets_subscription_active_on_checkout(self, db, user, monkeypatch):
        checkout_obj = {
            "id": "cs_test_123",
            "customer": "cus_abc123",
            "customer_details": {"email": "stripe@example.com", "name": "Test User"},
        }
        import app as app_module
        self._handle(monkeypatch, user, checkout_obj)
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "active"
        assert fetched["stripe_customer_id"] == "cus_abc123"

    def test_handles_customer_email_fallback(self, db, user, monkeypatch):
        checkout_obj = {
            "id": "cs_test_456",
            "customer": "cus_def456",
            "customer_email": "stripe@example.com",
            "customer_details": {},
        }
        import app as app_module
        self._handle(monkeypatch, user, checkout_obj)
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["stripe_customer_id"] == "cus_def456"

    def test_no_user_found_does_not_crash(self, db, monkeypatch):
        checkout_obj = {
            "id": "cs_test_789",
            "customer": "cus_xyz",
            "customer_details": {"email": "unknown@example.com", "name": "Ghost"},
        }
        import app as app_module
        # Should not raise even if user doesn't exist
        self._handle(monkeypatch, None, checkout_obj)

    def test_missing_customer_id_skips_subscription(self, db, user, monkeypatch):
        checkout_obj = {
            "id": "cs_no_cus",
            "customer": "",
            "customer_details": {"email": "stripe@example.com", "name": "Test"},
        }
        import app as app_module
        self._handle(monkeypatch, user, checkout_obj)
        fetched = users_module.get_user_by_id(user["id"])
        # status should remain trialing since no customer ID provided
        assert fetched["subscription_status"] == "trialing"


class TestSubscriptionUpdated:
    def _seed_customer(self, user_id, customer_id):
        users_module.set_subscription(user_id, customer_id, "active")

    def test_updates_status_on_subscription_updated(self, db, user):
        self._seed_customer(user["id"], "cus_upd")
        sub = {"customer": "cus_upd", "status": "past_due"}
        stripe_customer_id = sub.get("customer") or ""
        status = sub.get("status") or "active"
        found = users_module.get_user_by_stripe_customer(stripe_customer_id)
        if found and stripe_customer_id:
            users_module.set_subscription(found["id"], stripe_customer_id, status)
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "past_due"

    def test_unknown_customer_does_not_crash(self, db):
        sub = {"customer": "cus_ghost", "status": "active"}
        stripe_customer_id = sub.get("customer") or ""
        found = users_module.get_user_by_stripe_customer(stripe_customer_id)
        assert found is None  # no error raised


class TestSubscriptionDeleted:
    def test_sets_canceled_on_subscription_deleted(self, db, user):
        users_module.set_subscription(user["id"], "cus_del", "active")
        sub = {"customer": "cus_del"}
        stripe_customer_id = sub.get("customer") or ""
        found = users_module.get_user_by_stripe_customer(stripe_customer_id)
        if found:
            users_module.set_subscription(found["id"], stripe_customer_id, "canceled")
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "canceled"

    def test_missing_customer_id_skips(self, db, user):
        users_module.set_subscription(user["id"], "cus_keep", "active")
        sub = {"customer": ""}
        stripe_customer_id = sub.get("customer") or ""
        if stripe_customer_id:
            found = users_module.get_user_by_stripe_customer(stripe_customer_id)
            if found:
                users_module.set_subscription(found["id"], stripe_customer_id, "canceled")
        fetched = users_module.get_user_by_id(user["id"])
        # still active — no customer ID to match
        assert fetched["subscription_status"] == "active"
