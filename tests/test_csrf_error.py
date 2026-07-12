"""
Regression tests for the friendly CSRF error recovery page.

A stale or missing form session (Flask-WTF ``CSRFError``) must still return
HTTP 400, but render a friendly first-party recovery page instead of the raw
default response — without weakening CSRF enforcement or leaking token,
session, password, or traceback data.
"""

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
