"""
Regression tests for the friendly CSRF error recovery page.

A stale or missing form session (Flask-WTF ``CSRFError``) must still return
HTTP 400, but render a friendly first-party recovery page instead of the raw
default response — without weakening CSRF enforcement or leaking token,
session, password, or traceback data.

The recovery link must be a GET-safe target: the failing request may be a
POST-only endpoint (e.g. ``/onboarding/dismiss``), so reflecting ``request.path``
would produce a link that 405s on reload. The handler instead accepts the
referring page only when it validates as same-origin/local, and otherwise falls
back to the login page — external origins are never reflected.
"""

import re

import pytest
import db as db_module


@pytest.fixture()
def _isolated_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def csrf_client(_isolated_db):
    """Test client with CSRF protection ENABLED (production-like)."""
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = True
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c
    flask_app.app.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture()
def no_csrf_client(_isolated_db):
    """Test client with CSRF disabled — mirrors the normal login test path."""
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


_FRIENDLY = b"Reload and try again"

# A POST-only, non-CSRF-exempt endpoint. CSRFProtect runs before the login
# gate, so a sessionless POST here raises CSRFError (not a login redirect); a
# GET reload of this exact path would 405, which is what the recovery link must
# avoid.
_POST_ONLY_ROUTE = "/onboarding/dismiss"


def _recovery_href(data):
    """Return the href of the "Reload and try again" button, or None."""
    m = re.search(rb'href="([^"]+)"[^>]*>\s*Reload and try again', data)
    return m.group(1).decode() if m else None


def test_get_login_still_200(csrf_client):
    rv = csrf_client.get("/login")
    assert rv.status_code == 200


def test_sessionless_login_post_returns_friendly_400(csrf_client):
    rv = csrf_client.post(
        "/login", data={"email": "x@example.com", "password": "supersecretpw"}
    )
    assert rv.status_code == 400
    assert _FRIENDLY in rv.data
    assert b"session" in rv.data.lower()


def test_friendly_page_leaks_no_sensitive_data(csrf_client):
    rv = csrf_client.post(
        "/login", data={"email": "x@example.com", "password": "supersecretpw"}
    )
    assert rv.status_code == 400
    body = rv.data.lower()
    # No submitted password, no CSRF token value, no traceback internals.
    assert b"supersecretpw" not in rv.data
    assert b"csrf_token" not in body
    assert b"traceback" not in body
    assert b"werkzeug" not in body


def test_csrf_still_enforced_on_other_protected_form(csrf_client):
    """Another unsafe form (forgot-password) is still CSRF-protected, and the
    friendly handler applies to it too (proves protection is not weakened)."""
    rv = csrf_client.post("/forgot-password", data={"email": "x@example.com"})
    assert rv.status_code == 400
    assert _FRIENDLY in rv.data


def test_unrelated_error_not_routed_through_csrf_handler(csrf_client):
    """A non-CSRF response (an unknown route redirects to login) must not be
    caught by the CSRF handler: it is neither a 400 nor the friendly page."""
    rv = csrf_client.get("/this-route-does-not-exist-xyz")
    assert rv.status_code != 400
    assert _FRIENDLY not in rv.data


def test_valid_login_form_behavior_unchanged(no_csrf_client):
    """With CSRF disabled (existing test path), a login POST is handled by the
    login view (not the CSRF handler): invalid creds re-render the form, not a
    400 recovery page."""
    rv = no_csrf_client.post(
        "/login", data={"email": "nobody@example.com", "password": "wrongpw"}
    )
    assert rv.status_code == 200
    assert _FRIENDLY not in rv.data


def test_post_only_endpoint_gets_get_safe_recovery_link(csrf_client):
    """A sessionless CSRF failure on a POST-only endpoint must render the 400
    friendly page with a recovery link that is safe to GET — i.e. NOT the
    POST-only path itself (which would 405 on reload)."""
    rv = csrf_client.post(_POST_ONLY_ROUTE)
    assert rv.status_code == 400
    assert _FRIENDLY in rv.data

    href = _recovery_href(rv.data)
    assert href is not None
    # Must not reflect the POST-only request path (the old request.path bug).
    assert href not in (_POST_ONLY_ROUTE, "http://localhost" + _POST_ONLY_ROUTE)
    # With no referrer it falls back to the GET-able login page.
    assert href == "/login"
    # Prove it is actually GET-safe: reloading the link does not 405.
    assert csrf_client.get(href).status_code != 405


def test_external_referrer_is_rejected(csrf_client):
    """An off-origin Referer must never be reflected into the recovery link;
    the handler falls back to the login page instead (no open redirect)."""
    rv = csrf_client.post(
        _POST_ONLY_ROUTE, headers={"Referer": "https://evil.example.com/phish"}
    )
    assert rv.status_code == 400
    href = _recovery_href(rv.data)
    assert href == "/login"
    assert b"evil.example.com" not in rv.data


def test_same_origin_referrer_is_accepted(csrf_client):
    """A validated same-origin Referer (the page that rendered the form) is used
    as the recovery target, and it is a GET-safe page (not a 405)."""
    rv = csrf_client.post(
        _POST_ONLY_ROUTE, headers={"Referer": "http://localhost/onboarding"}
    )
    assert rv.status_code == 400
    href = _recovery_href(rv.data)
    assert href == "http://localhost/onboarding"
    # GET-safe: the originating form page does not 405 (sessionless → redirect).
    assert csrf_client.get("/onboarding").status_code != 405


def test_scheme_relative_referrer_is_rejected(csrf_client):
    """A scheme/protocol-relative Referer pointing off-origin must not be
    reflected (defense against ``//evil.example.com`` style bypasses)."""
    rv = csrf_client.post(
        _POST_ONLY_ROUTE, headers={"Referer": "//evil.example.com/x"}
    )
    assert rv.status_code == 400
    href = _recovery_href(rv.data)
    assert href == "/login"
    assert b"evil.example.com" not in rv.data
