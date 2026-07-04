"""End-to-end test-mode evidence: trial -> checkout -> activation, via BOTH
the real webhook route (genuine Stripe-style signature verification, not a
bypassed reimplementation) AND the new checkout-return fallback added to
/success. No network calls to Stripe -- a locally-generated signing secret
is used to compute a real, valid Stripe webhook signature over a synthetic
event, exercising the actual `stripe.Webhook.construct_event` verification
path in payments/providers/stripe_provider.py. The fallback path exercises
the real /success route with payments.service.retrieve_checkout_session
monkeypatched (same convention already used by the rest of this suite for
Stripe API calls), since simulating a customer's browser redirect doesn't
require a live checkout session to exist.
"""
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import stripe

import db as db_module
import users as users_module

TEST_WEBHOOK_SECRET = "whsec_test_only_57a1c9f0e3b2d4a6"  # local test-mode value, never a real Stripe secret


@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db, monkeypatch):
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    # This IS "setting the TEST-mode STRIPE_WEBHOOK_SECRET in the local/test
    # config" -- monkeypatching the already-imported module attribute is
    # this codebase's existing convention for injecting test-time config
    # (see UNIFIED_ACCESS_ENABLED in test_access_unification.py) and never
    # touches any real file, Railway, or live key.
    monkeypatch.setattr(flask_app, "STRIPE_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            yield c


@pytest.fixture()
def trial_user(test_db):
    user = users_module.create_user("stripe-e2e@example.com", "password123")
    users_module.set_trial(user["id"], days=14)
    # Force expiry so we can prove access is actually gated before activation,
    # and actually restored after -- not just that a DB column flips.
    with db_module.connect() as con:
        con.execute(
            "UPDATE users SET trial_ends_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user["id"]),
        )
        con.commit()
    return user


def _sign(secret: str, payload: bytes, timestamp: int | None = None) -> str:
    """Real Stripe webhook signing scheme: t=<ts>,v1=hmac_sha256(secret, f'{ts}.{payload}')."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    v1 = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def _stripe_session(data: dict) -> "stripe.checkout.Session":
    """A GENUINE stripe.checkout.Session instance (via the SDK's own
    construct_from, no network call) rather than a plain dict -- this is
    what retrieve_checkout_session actually returns in production, and it
    is exactly what exposed the .get()-doesn't-exist bug in /success. Using
    a plain dict here would silently skip the .to_dict() conversion branch
    and prove nothing about real Stripe objects."""
    return stripe.checkout.Session.construct_from(data, "sk_test_fake_not_a_real_key")


def _checkout_completed_payload(email, customer_id, session_id="cs_test_e2e_1", payment_status="paid"):
    return json.dumps({
        "id": "evt_test_e2e_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id,
            "object": "checkout.session",
            "customer": customer_id,
            "payment_status": payment_status,
            "customer_details": {"email": email, "name": "E2E Test User"},
        }},
    }).encode("utf-8")


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["user_email"] = user["email"]


# --------------------------------------------------------------------------
# Access is genuinely gated before activation (proves the test is meaningful)
# --------------------------------------------------------------------------

def test_expired_trial_blocks_access_before_activation(client, trial_user):
    _login(client, trial_user)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]


# --------------------------------------------------------------------------
# PRIMARY PATH: real webhook route, genuine signature verification
# --------------------------------------------------------------------------

def test_webhook_with_valid_signature_activates_subscription(client, trial_user):
    payload = _checkout_completed_payload(trial_user["email"], "cus_e2e_webhook")
    sig = _sign(TEST_WEBHOOK_SECRET, payload)

    resp = client.post("/stripe/webhook", data=payload, headers={
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    })
    assert resp.status_code == 200

    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] == "active"
    assert fetched["stripe_customer_id"] == "cus_e2e_webhook"

    # Access is actually restored, not just the DB column.
    _login(client, trial_user)
    resp2 = client.get("/dashboard", follow_redirects=False)
    assert resp2.status_code != 302 or "/subscribe" not in (resp2.headers.get("Location") or "")


def test_webhook_with_invalid_signature_is_rejected(client, trial_user):
    payload = _checkout_completed_payload(trial_user["email"], "cus_should_not_activate")
    bad_sig = _sign("whsec_totally_wrong_secret", payload)

    resp = client.post("/stripe/webhook", data=payload, headers={
        "Content-Type": "application/json",
        "Stripe-Signature": bad_sig,
    })
    assert resp.status_code == 400

    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] != "active"


def test_webhook_refuses_when_secret_not_configured(client, trial_user, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app, "STRIPE_WEBHOOK_SECRET", "")
    payload = _checkout_completed_payload(trial_user["email"], "cus_no_secret")
    sig = _sign(TEST_WEBHOOK_SECRET, payload)
    resp = client.post("/stripe/webhook", data=payload, headers={
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    })
    assert resp.status_code == 400
    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] != "active"


# --------------------------------------------------------------------------
# FALLBACK PATH: /success verifies with Stripe directly, no webhook involved
# --------------------------------------------------------------------------

def test_success_fallback_activates_when_webhook_never_fires(client, trial_user):
    """Simulates exactly the gap the audit found: webhook misconfigured/absent
    (STRIPE_WEBHOOK_SECRET unset, matching real Railway prod state today),
    customer still lands on /success after paying. The fallback must activate
    access on its own, with zero webhook involvement."""
    import app as flask_app

    monkeypatch_target = flask_app.payments.service
    fake_session = _stripe_session({
        "id": "cs_test_e2e_fallback",
        "customer": "cus_e2e_fallback",
        "payment_status": "paid",
        "customer_details": {"email": trial_user["email"], "name": "E2E Test User"},
    })
    with patch.object(monkeypatch_target, "retrieve_checkout_session", return_value=fake_session):
        with patch.object(flask_app.hubspot_service, "handle_stripe_checkout", return_value=None):
            resp = client.get("/success?session_id=cs_test_e2e_fallback")
    assert resp.status_code == 200

    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] == "active"
    assert fetched["stripe_customer_id"] == "cus_e2e_fallback"

    _login(client, trial_user)
    resp2 = client.get("/dashboard", follow_redirects=False)
    assert resp2.status_code != 302 or "/subscribe" not in (resp2.headers.get("Location") or "")


def test_success_fallback_does_not_activate_when_not_paid(client, trial_user):
    import app as flask_app

    fake_session = _stripe_session({
        "id": "cs_test_e2e_unpaid",
        "customer": "cus_e2e_unpaid",
        "payment_status": "unpaid",
        "customer_details": {"email": trial_user["email"], "name": "E2E Test User"},
    })
    with patch.object(flask_app.payments.service, "retrieve_checkout_session", return_value=fake_session):
        with patch.object(flask_app.hubspot_service, "handle_stripe_checkout", return_value=None):
            resp = client.get("/success?session_id=cs_test_e2e_unpaid")
    assert resp.status_code == 200

    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] != "active"


def test_webhook_and_fallback_both_firing_is_idempotent_and_safe(client, trial_user):
    """Both paths can legitimately fire for the same session (webhook catches
    up after the fallback already activated, or vice versa) -- must not
    error, duplicate side effects, or leave inconsistent state."""
    import app as flask_app

    # Fallback fires first (webhook delayed).
    fake_session = _stripe_session({
        "id": "cs_test_e2e_both",
        "customer": "cus_e2e_both",
        "payment_status": "paid",
        "customer_details": {"email": trial_user["email"], "name": "E2E Test User"},
    })
    with patch.object(flask_app.payments.service, "retrieve_checkout_session", return_value=fake_session):
        with patch.object(flask_app.hubspot_service, "handle_stripe_checkout", return_value=None):
            resp1 = client.get("/success?session_id=cs_test_e2e_both")
    assert resp1.status_code == 200

    # Webhook catches up later for the same session -- must not blow up or diverge.
    payload = _checkout_completed_payload(trial_user["email"], "cus_e2e_both", session_id="cs_test_e2e_both")
    sig = _sign(TEST_WEBHOOK_SECRET, payload)
    resp2 = client.post("/stripe/webhook", data=payload, headers={
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    })
    assert resp2.status_code == 200

    fetched = users_module.get_user_by_id(trial_user["id"])
    assert fetched["subscription_status"] == "active"
    assert fetched["stripe_customer_id"] == "cus_e2e_both"
