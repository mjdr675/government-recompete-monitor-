"""Tests for Customer Workspace billing, trials, and Stripe foundation.

Covers:
- trial starts on workspace creation (7-day window)
- trial expiry logic (is_workspace_in_trial / is_workspace_active)
- active vs expired workspace access enforcement on gated routes
- subscription activation updates access
- webhook updates workspace state (mocked Stripe payloads)
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import db as db_module
import users as users_module
from db import (
    get_or_create_workspace_for_user,
    get_workspace_for_user,
    get_workspace_billing,
    update_workspace_subscription_status,
    is_workspace_in_trial,
    is_workspace_active,
    get_workspace_by_stripe_customer,
)


@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("bill@example.com", "password123", company_name="Acme")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email='bill@example.com'").fetchone()[0]
    con.close()
    return uid


def _set_workspace_trial_end(workspace_id, dt):
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE workspaces SET trial_end_at = :t WHERE id = :id"),
            {"t": dt.isoformat(), "id": workspace_id},
        )


@pytest.fixture()
def client(pdb, monkeypatch):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    app_module.app.config["RATELIMIT_ENABLED"] = False
    app_module.app.secret_key = "test-secret"
    with app_module.app.test_client() as c:
        yield c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# ---------------------------------------------------------------------------
# Trial system
# ---------------------------------------------------------------------------

class TestTrialSystem:
    def test_trial_starts_on_workspace_creation(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        billing = get_workspace_billing(ws["id"])
        assert billing["subscription_status"] == "trialing"
        assert billing["plan"] == "starter"
        assert billing["trial_start_at"] is not None
        assert billing["trial_end_at"] is not None

    def test_trial_window_is_seven_days(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        billing = get_workspace_billing(ws["id"])
        start = datetime.fromisoformat(billing["trial_start_at"])
        end = datetime.fromisoformat(billing["trial_end_at"])
        assert (end - start) == timedelta(days=7)

    def test_workspace_in_trial_true_when_fresh(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        assert is_workspace_in_trial(ws["id"]) is True
        assert is_workspace_active(ws["id"]) is True

    def test_expired_trial_not_active(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        _set_workspace_trial_end(ws["id"], datetime.now(timezone.utc) - timedelta(days=1))
        assert is_workspace_in_trial(ws["id"]) is False
        assert is_workspace_active(ws["id"]) is False

    def test_active_subscription_overrides_expired_trial(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        _set_workspace_trial_end(ws["id"], datetime.now(timezone.utc) - timedelta(days=1))
        update_workspace_subscription_status(ws["id"], "active")
        assert is_workspace_active(ws["id"]) is True

    def test_provision_idempotent_does_not_reset_trial(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        first_end = get_workspace_billing(ws["id"])["trial_end_at"]
        # Re-provision; trial window must not move.
        get_or_create_workspace_for_user(uid)
        assert get_workspace_billing(ws["id"])["trial_end_at"] == first_end


# ---------------------------------------------------------------------------
# Billing helpers
# ---------------------------------------------------------------------------

class TestBillingHelpers:
    def test_update_subscription_status_and_linkage(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace_subscription_status(
            ws["id"], "active", plan="growth",
            stripe_customer_id="cus_1", stripe_subscription_id="sub_1",
        )
        billing = get_workspace_billing(ws["id"])
        assert billing["subscription_status"] == "active"
        assert billing["plan"] == "growth"
        assert billing["stripe_customer_id"] == "cus_1"
        assert billing["stripe_subscription_id"] == "sub_1"

    def test_lookup_by_stripe_customer(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace_subscription_status(ws["id"], "active", stripe_customer_id="cus_lookup")
        found = get_workspace_by_stripe_customer("cus_lookup")
        assert found is not None and found["id"] == ws["id"]

    def test_lookup_unknown_customer_returns_none(self, pdb):
        assert get_workspace_by_stripe_customer("cus_nope") is None


# ---------------------------------------------------------------------------
# Access enforcement (Phase 5 gate)
# ---------------------------------------------------------------------------

class TestAccessEnforcement:
    def test_active_trial_allows_dashboard(self, client, pdb):
        uid = _uid(pdb)
        get_or_create_workspace_for_user(uid)  # fresh trial
        _login(client, uid)
        resp = client.get("/dashboard")
        assert "/settings/billing" not in (resp.headers.get("Location") or "")

    def test_expired_workspace_redirects_to_billing(self, client, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        _set_workspace_trial_end(ws["id"], datetime.now(timezone.utc) - timedelta(days=1))
        _login(client, uid)
        resp = client.get("/contracts")
        assert resp.status_code == 302
        assert "/settings/billing" in resp.headers["Location"]

    def test_active_subscription_allows_access(self, client, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        _set_workspace_trial_end(ws["id"], datetime.now(timezone.utc) - timedelta(days=1))
        update_workspace_subscription_status(ws["id"], "active")
        _login(client, uid)
        resp = client.get("/pipeline")
        assert "/settings/billing" not in (resp.headers.get("Location") or "")

    def test_billing_page_reachable_when_expired(self, client, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        _set_workspace_trial_end(ws["id"], datetime.now(timezone.utc) - timedelta(days=1))
        _login(client, uid)
        resp = client.get("/settings/billing")
        assert resp.status_code == 200
        assert "Billing" in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Webhook → workspace state (mocked Stripe payloads)
# ---------------------------------------------------------------------------

class TestWebhookWorkspaceUpdates:
    def test_checkout_completed_activates_workspace(self, pdb):
        import app as app_module
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        event = {
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": str(ws["id"]),
                "customer": "cus_ck",
                "subscription": "sub_ck",
                "metadata": {"workspace_id": str(ws["id"]), "plan": "pro"},
            }},
        }
        app_module._apply_workspace_billing_event(event)
        billing = get_workspace_billing(ws["id"])
        assert billing["subscription_status"] == "active"
        assert billing["plan"] == "pro"
        assert billing["stripe_customer_id"] == "cus_ck"
        assert billing["stripe_subscription_id"] == "sub_ck"

    def test_subscription_updated_sets_status(self, pdb):
        import app as app_module
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace_subscription_status(ws["id"], "active", stripe_customer_id="cus_up")
        event = {
            "id": "evt_2",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_up", "customer": "cus_up", "status": "past_due"}},
        }
        app_module._apply_workspace_billing_event(event)
        assert get_workspace_billing(ws["id"])["subscription_status"] == "past_due"

    def test_subscription_deleted_cancels(self, pdb):
        import app as app_module
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace_subscription_status(ws["id"], "active", stripe_customer_id="cus_del")
        event = {
            "id": "evt_3",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_del", "customer": "cus_del"}},
        }
        app_module._apply_workspace_billing_event(event)
        assert get_workspace_billing(ws["id"])["subscription_status"] == "canceled"

    def test_event_without_workspace_linkage_is_noop(self, pdb):
        import app as app_module
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        before = get_workspace_billing(ws["id"])["subscription_status"]
        event = {
            "id": "evt_4",
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_orphan"}},  # no client_reference_id
        }
        app_module._apply_workspace_billing_event(event)  # must not raise
        assert get_workspace_billing(ws["id"])["subscription_status"] == before

    def test_billing_event_recorded(self, pdb):
        import app as app_module
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        event = {
            "id": "evt_5",
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": str(ws["id"]),
                "customer": "cus_rec",
                "metadata": {"workspace_id": str(ws["id"]), "plan": "growth"},
            }},
        }
        app_module._apply_workspace_billing_event(event)
        con = sqlite3.connect(pdb)
        n = con.execute(
            "SELECT COUNT(*) FROM workspace_billing_events WHERE workspace_id = ?",
            (ws["id"],),
        ).fetchone()[0]
        con.close()
        assert n == 1


# ---------------------------------------------------------------------------
# Existing user-level gate must remain intact
# ---------------------------------------------------------------------------

class TestExistingUserGateUnbroken:
    def test_expired_user_trial_still_redirects_to_subscribe(self, client, pdb):
        # No workspace created → user-level gate (registered first) wins.
        uid = _uid(pdb)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with db_module.get_engine().begin() as conn:
            conn.execute(text("UPDATE users SET trial_ends_at = :t WHERE id = :id"),
                         {"t": past, "id": uid})
        _login(client, uid)
        resp = client.get("/contracts")
        assert resp.status_code == 302
        assert "/subscribe" in resp.headers["Location"]
