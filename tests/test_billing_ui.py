"""
Tests for launch-safe billing UI:
  - /settings/billing loads without error
  - Cancellation/support copy is present
  - Support email link renders
  - Payment Link URLs appear on the page
  - No Stripe secret key leaked into HTML
  - Stripe Customer Portal form is absent
  - /settings/account loads with support email copy
"""

from unittest.mock import MagicMock, patch

import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures — mirrors test_app.py pattern
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            c.post("/register", data={
                "email": "billingtest@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


# ---------------------------------------------------------------------------
# /settings/billing
# ---------------------------------------------------------------------------

def test_settings_billing_loads(client):
    rv = client.get("/settings/billing")
    assert rv.status_code == 200


def test_settings_billing_heading_present(client):
    rv = client.get("/settings/billing")
    assert b"Billing" in rv.data


def test_settings_billing_support_email_present(client):
    """Support email link must appear on the billing page."""
    rv = client.get("/settings/billing")
    assert b"support@recompete.us" in rv.data


def test_settings_billing_cancellation_copy_present(client):
    """Cancellation guidance copy must be visible."""
    rv = client.get("/settings/billing")
    assert b"cancel" in rv.data.lower()


def test_settings_billing_payment_links_present(client):
    """Public Stripe Payment Links must appear for Basic and Pro plan selection."""
    rv = client.get("/settings/billing")
    assert b"buy.stripe.com" in rv.data


def test_settings_billing_basic_monthly_link(client):
    rv = client.get("/settings/billing")
    assert b"eVq3cwgki6R62T32Py28802" in rv.data  # Basic Monthly payment link fragment


def test_settings_billing_basic_yearly_link(client):
    rv = client.get("/settings/billing")
    assert b"28E3cwaZYdfubpz0Hq28803" in rv.data  # Basic Yearly payment link fragment


def test_settings_billing_pro_monthly_link(client):
    rv = client.get("/settings/billing")
    assert b"9B6aEY0lkejy51bcq828800" in rv.data  # Pro Monthly payment link fragment


def test_settings_billing_pro_yearly_link(client):
    rv = client.get("/settings/billing")
    assert b"3cIdRa9VU8ZectD0Hq28801" in rv.data  # Pro Yearly payment link fragment


def test_settings_billing_enterprise_goes_to_sales_email(client):
    """Enterprise CTA must point to mailto:sales@recompete.us, not a Stripe link."""
    rv = client.get("/settings/billing")
    assert b"sales@recompete.us" in rv.data
    assert b"Contact Sales" in rv.data


def test_settings_billing_enterprise_has_no_stripe_link(client):
    """Enterprise plan must not have a buy.stripe.com link."""
    rv = client.get("/settings/billing")
    html = rv.data.decode()
    # Confirm Enterprise section exists
    assert "Enterprise" in html
    # Find the Enterprise card block and verify no stripe.com URL in it
    enterprise_idx = html.find("Enterprise")
    # The next buy.stripe.com occurrence (if any) must come BEFORE the Enterprise block
    stripe_idx = html.rfind("buy.stripe.com")
    assert stripe_idx < enterprise_idx or stripe_idx == -1, \
        "buy.stripe.com URL found after Enterprise section — Enterprise must not link to Stripe"


def test_settings_billing_no_secret_key_in_html(client):
    """STRIPE_SECRET_KEY must never appear in rendered HTML."""
    import app as flask_app
    secret = flask_app.app.config.get("STRIPE_SECRET_KEY") or "sk_test_DUMMY_SECRET"
    with patch.dict("os.environ", {"STRIPE_SECRET_KEY": secret}):
        rv = client.get("/settings/billing")
    assert secret.encode() not in rv.data
    assert b"STRIPE_SECRET_KEY" not in rv.data


def test_settings_billing_no_portal_form(client):
    """Stripe Customer Portal POST form must not exist on the billing page."""
    rv = client.get("/settings/billing")
    # The portal form previously posted to /billing/portal
    assert b"/billing/portal" not in rv.data


def test_settings_billing_self_service_coming_soon_noted(client):
    """The page must honestly note that self-service billing is coming."""
    rv = client.get("/settings/billing")
    assert b"coming soon" in rv.data.lower()


def test_settings_billing_mailto_link_present(client):
    """A mailto: link for support must be present."""
    rv = client.get("/settings/billing")
    assert b"mailto:" in rv.data


# ---------------------------------------------------------------------------
# /settings/account
# ---------------------------------------------------------------------------

def test_settings_account_loads(client):
    rv = client.get("/settings/account")
    assert rv.status_code == 200


def test_settings_account_support_email_present(client):
    """Account page must show the support email for billing help."""
    rv = client.get("/settings/account")
    assert b"support@recompete.us" in rv.data


def test_settings_account_no_portal_form(client):
    """Stripe Customer Portal POST form must not be on account settings page."""
    rv = client.get("/settings/account")
    assert b"/billing/portal" not in rv.data


def test_settings_account_no_stripe_secret(client):
    """STRIPE_SECRET_KEY must not appear in the account settings page."""
    rv = client.get("/settings/account")
    assert b"STRIPE_SECRET_KEY" not in rv.data
    assert b"sk_live" not in rv.data
    assert b"sk_test" not in rv.data
