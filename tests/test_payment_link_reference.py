"""
Tests for per-user Stripe Payment Link references.

Payment Links on /settings/billing and /subscribe must be rendered with a
``client_reference_id`` (the workspace id) and ``prefilled_email`` query
param appended, so the checkout.session.completed webhook
(app.py:_apply_workspace_billing_event, app.py:1408) can resolve the workspace
and mark it active — exactly as it does for API-created Checkout Sessions.

Guard behavior: logged-out visitors (and users with no workspace yet) must get
BARE links so no empty params are emitted.

Isolated test file — does not touch the full suite.
"""

from unittest.mock import MagicMock, patch

import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures — mirror tests/test_billing_ui.py
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
def app_client(test_db):
    """Bare test client with no authenticated session (logged-out)."""
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture()
def logged_in(app_client):
    """Registered + logged-in user, onboarding skipped."""
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=None)
    with patch("tasks.send_email_task", mock_task):
        app_client.post("/register", data={
            "email": "billingtest@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
    with app_client.session_transaction() as sess:
        sess["onboarding_skipped"] = "1"
    return app_client


EXPECTED_EMAIL_ENC = "billingtest%40example.com"  # '@' URL-encoded


# ---------------------------------------------------------------------------
# /settings/billing — logged-in user with a workspace
# ---------------------------------------------------------------------------

def test_billing_links_carry_client_reference_id(logged_in):
    """Every Payment Link on /settings/billing must carry client_reference_id."""
    rv = logged_in.get("/settings/billing")
    assert rv.status_code == 200
    html = rv.data.decode()
    # The workspace is created by the /settings/billing route (get_or_create),
    # so client_reference_id must be present on the buy.stripe.com links.
    assert "buy.stripe.com" in html
    assert "?client_reference_id=" in html


def test_billing_links_carry_prefilled_email(logged_in):
    """prefilled_email must be appended and URL-encoded."""
    rv = logged_in.get("/settings/billing")
    html = rv.data.decode()
    assert "prefilled_email=" in html
    assert EXPECTED_EMAIL_ENC in html


def test_billing_reference_appended_to_a_stripe_url(logged_in):
    """The ref params must be appended to a buy.stripe.com URL (not floating)."""
    rv = logged_in.get("/settings/billing")
    html = rv.data.decode()
    import re
    # A buy.stripe.com URL immediately followed by the ref query string.
    # Jinja HTML-escapes '&' to '&amp;' in the attribute (browsers decode it
    # back to '&' when following the link), so match the escaped form.
    m = re.search(
        r"https://buy\.stripe\.com/[A-Za-z0-9]+\?client_reference_id=\d+&amp;prefilled_email="
        + re.escape(EXPECTED_EMAIL_ENC),
        html,
    )
    assert m is not None, "no buy.stripe.com URL carried both ref params"


# ---------------------------------------------------------------------------
# /subscribe — logged-in user with a workspace
# ---------------------------------------------------------------------------

def test_subscribe_links_carry_reference_for_user_with_workspace(logged_in):
    """/subscribe links carry the ref once the user has a workspace."""
    # Visit /settings/billing first to lazily create the workspace
    # (registration does not create one; inject_workspace does not create one).
    logged_in.get("/settings/billing")
    rv = logged_in.get("/subscribe")
    assert rv.status_code == 200
    html = rv.data.decode()
    assert "buy.stripe.com" in html
    assert "?client_reference_id=" in html
    assert "prefilled_email=" in html
    assert EXPECTED_EMAIL_ENC in html


# ---------------------------------------------------------------------------
# Guard — logged-out visitor gets BARE links (no empty params)
# ---------------------------------------------------------------------------

def test_subscribe_logged_out_links_are_bare(app_client):
    """Logged-out /subscribe must not emit client_reference_id/prefilled_email."""
    rv = app_client.get("/subscribe")
    assert rv.status_code == 200
    html = rv.data.decode()
    assert "buy.stripe.com" in html
    assert "client_reference_id=" not in html
    assert "prefilled_email=" not in html
