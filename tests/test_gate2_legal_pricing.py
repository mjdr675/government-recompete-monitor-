"""
Gate 2: legal + pricing pages.

Confirms the four public pages (/terms, /privacy, /refund, /pricing) render
200 without authentication, that /pricing carries the workspace ref plumbing
for logged-in users (mirrors /subscribe), and that the shared site footer
links to all four pages on every rendered surface.
"""

from unittest.mock import MagicMock, patch

import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def anon_client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture()
def logged_in(anon_client):
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=None)
    with patch("tasks.send_email_task", mock_task):
        anon_client.post("/register", data={
            "email": "gate2@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
    with anon_client.session_transaction() as sess:
        sess["onboarding_skipped"] = "1"
    return anon_client


PUBLIC_ROUTES = ["/terms", "/privacy", "/refund", "/pricing"]

FOOTER_LINKS = [
    'href="/pricing"',
    'href="/terms"',
    'href="/privacy"',
    'href="/refund"',
]


# ---------------------------------------------------------------------------
# Unauthenticated access — all four routes return 200
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PUBLIC_ROUTES)
def test_route_200_unauthenticated(anon_client, path):
    resp = anon_client.get(path)
    assert resp.status_code == 200, (
        f"{path} must return 200 without auth; got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Footer — all four legal/pricing links appear on every rendered surface
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PUBLIC_ROUTES + ["/subscribe", "/login"])
def test_footer_links_present(anon_client, path):
    resp = anon_client.get(path)
    assert resp.status_code == 200
    html = resp.data.decode()
    for link in FOOTER_LINKS:
        assert link in html, f"{path} missing footer link {link}"


# ---------------------------------------------------------------------------
# Content sanity — legal pages render the expected heading and no [REVIEW]
# markers leak to visitors (the pages are legally reviewed and final).
# ---------------------------------------------------------------------------

def test_terms_renders_expected_heading_and_no_review_markers(anon_client):
    html = anon_client.get("/terms").data.decode()
    assert "Terms of Service" in html
    assert "[REVIEW" not in html, "terms.html leaked a [REVIEW] marker to public HTML"


def test_privacy_renders_expected_heading_and_no_review_markers(anon_client):
    html = anon_client.get("/privacy").data.decode()
    assert "Privacy Policy" in html
    assert "[REVIEW" not in html, "privacy.html leaked a [REVIEW] marker to public HTML"


def test_refund_renders_expected_heading_and_no_review_markers(anon_client):
    html = anon_client.get("/refund").data.decode()
    assert "Refund Policy" in html
    assert "[REVIEW" not in html, "refund.html leaked a [REVIEW] marker to public HTML"


# ---------------------------------------------------------------------------
# Pricing — reuses the existing Payment Link + workspace ref plumbing
# ---------------------------------------------------------------------------

def test_pricing_shows_pro_stripe_payment_link(anon_client):
    html = anon_client.get("/pricing").data.decode()
    assert "buy.stripe.com" in html, "pricing must embed a Stripe Payment Link"


def test_pricing_logged_out_links_are_bare(anon_client):
    html = anon_client.get("/pricing").data.decode()
    assert "buy.stripe.com" in html
    assert "client_reference_id=" not in html
    assert "prefilled_email=" not in html


def test_pricing_logged_in_link_carries_client_reference_id(logged_in):
    resp = logged_in.get("/pricing")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "buy.stripe.com" in html
    assert "?client_reference_id=" in html
    assert "prefilled_email=" in html
    assert "gate2%40example.com" in html
