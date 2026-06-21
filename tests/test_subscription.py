"""Tests for subscription/trial fields on the users table (task F-4a)."""
import pytest
import db as db_module
import users as users_module
from datetime import datetime, timezone


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def user(db):
    return users_module.create_user("test@example.com", "password123")


class TestSubscriptionColumns:
    def test_new_user_has_trialing_status(self, user):
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "trialing"

    def test_new_user_has_no_stripe_customer_id(self, user):
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["stripe_customer_id"] is None

    def test_new_user_has_no_trial_ends_at(self, user):
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["trial_ends_at"] is None

    def test_get_user_by_id_returns_subscription_fields(self, user):
        fetched = users_module.get_user_by_id(user["id"])
        assert "stripe_customer_id" in fetched
        assert "subscription_status" in fetched
        assert "trial_ends_at" in fetched


class TestSetTrial:
    def test_set_trial_writes_future_date(self, user):
        ends_at = users_module.set_trial(user["id"], days=14)
        assert ends_at is not None
        dt = datetime.fromisoformat(ends_at)
        assert dt > datetime.now(timezone.utc)

    def test_set_trial_is_readable_back(self, user):
        ends_at = users_module.set_trial(user["id"], days=14)
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["trial_ends_at"] == ends_at

    def test_set_trial_custom_days(self, user):
        ends_at = users_module.set_trial(user["id"], days=7)
        dt = datetime.fromisoformat(ends_at)
        delta = dt - datetime.now(timezone.utc)
        assert delta.total_seconds() > 6 * 86400


class TestSetSubscription:
    def test_set_subscription_writes_customer_id(self, user):
        users_module.set_subscription(user["id"], "cus_test123", "active")
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["stripe_customer_id"] == "cus_test123"
        assert fetched["subscription_status"] == "active"

    def test_set_subscription_can_update_status(self, user):
        users_module.set_subscription(user["id"], "cus_test123", "active")
        users_module.set_subscription(user["id"], "cus_test123", "canceled")
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "canceled"


class TestGetUserByStripeCustomer:
    def test_returns_user_for_known_customer(self, user):
        users_module.set_subscription(user["id"], "cus_abc", "active")
        found = users_module.get_user_by_stripe_customer("cus_abc")
        assert found is not None
        assert found["email"] == "test@example.com"

    def test_returns_none_for_unknown_customer(self, db):
        result = users_module.get_user_by_stripe_customer("cus_unknown")
        assert result is None
