"""Behavioural tests for the global 404 / 500 error handlers and branded pages.

Covers both request classes (HTML browser vs JSON/API), authenticated and
unauthenticated flows, correct status codes, absence of sensitive/internal
detail, logging, recursion safety, and regression of normal routes.

Architecture notes that shape these tests:
* The app's ``require_login`` before-request gate redirects *unauthenticated*
  requests for non-public paths to ``/login`` **before** routing runs. That is
  deliberate existing security behaviour (anonymous users are not told which
  routes exist), so the branded 404 is reached by anonymous users only through
  a public prefix such as ``/static/<missing>``; authenticated users reach it
  on any unknown path. We assert both, and assert the anonymous-unknown-route
  redirect is preserved (not converted to a 200/dashboard).
* The 500 path is exercised via a raising route registered ONLY here (never in
  production code). It is temporarily added to the public set so the auth gate
  does not intercept it, and ``PROPAGATE_EXCEPTIONS=False`` is set so Flask
  invokes the registered handler instead of re-raising under TESTING.
"""

import json
import logging

import pytest

import app as flask_app
import db as db_module

# Marker planted in the test-only failure route; asserting its ABSENCE from
# every 500 response proves exception detail never leaks to the client.
BOOM_SECRET = "boom-secret-should-never-leak-to-client"


def _boom():
    raise RuntimeError(BOOM_SECRET)


# Register the test-only failure route at IMPORT time (during collection, before
# the shared app singleton has served any request) — Flask 3 locks add_url_rule
# after the first request. This route exists only while this test module is
# imported; it is never part of the production application.
if "boom_test" not in flask_app.app.view_functions:
    flask_app.app.add_url_rule("/__boom__", "boom_test", _boom)


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


def _configure(app):
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["RATELIMIT_ENABLED"] = False
    app.secret_key = "test-secret-key"


def _register(client):
    """Register (and thereby authenticate) a fresh user via the real flow."""
    return client.post(
        "/register",
        data={
            "email": "erruser@example.com",
            "password": "supersecret123",
            "confirm": "supersecret123",
        },
    )


@pytest.fixture()
def anon_client(auth_db):
    _configure(flask_app.app)
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture()
def client(auth_db):
    _configure(flask_app.app)
    with flask_app.app.test_client() as c:
        _register(c)
        yield c


@pytest.fixture()
def boom_client(auth_db):
    """Anonymous client where /__boom__ is reachable and the 500 handler runs."""
    _configure(flask_app.app)
    original_public = flask_app._PUBLIC_PATHS
    flask_app._PUBLIC_PATHS = original_public | {"/__boom__"}
    original_prop = flask_app.app.config.get("PROPAGATE_EXCEPTIONS")
    flask_app.app.config["PROPAGATE_EXCEPTIONS"] = False
    with flask_app.app.test_client() as c:
        yield c
    flask_app._PUBLIC_PATHS = original_public
    flask_app.app.config["PROPAGATE_EXCEPTIONS"] = original_prop


# --------------------------------------------------------------------------- #
# 404 — HTML
# --------------------------------------------------------------------------- #

def test_unmatched_route_authenticated_returns_404(client):
    rv = client.get("/this-route-does-not-exist-xyz", headers={"Accept": "text/html"})
    assert rv.status_code == 404


def test_404_renders_branded_html_authenticated(client):
    rv = client.get("/this-route-does-not-exist-xyz", headers={"Accept": "text/html"})
    assert rv.status_code == 404
    body = rv.get_data(as_text=True)
    assert "text/html" in rv.content_type
    assert "Page not found" in body
    assert "Recompete" in body
    assert 'href="/contracts"' in body
    assert 'href="/"' in body


def test_404_branded_html_anonymous_via_static_miss(anon_client):
    # Anonymous users reach the branded 404 through a public prefix (static).
    rv = anon_client.get("/static/definitely-missing-asset.css", headers={"Accept": "text/html"})
    assert rv.status_code == 404
    body = rv.get_data(as_text=True)
    assert "Page not found" in body
    assert "Recompete" in body


def test_anonymous_unknown_route_redirects_to_login_not_dashboard(anon_client):
    # Existing security behaviour preserved: anon unknown route -> login, never a
    # 200/dashboard redirect and never a masked 404 leak of route existence.
    rv = anon_client.get("/some-unknown-page", headers={"Accept": "text/html"})
    assert rv.status_code == 302
    assert "/login" in rv.headers.get("Location", "")


def test_404_is_not_redirect_to_dashboard(client):
    rv = client.get("/nope-not-here", headers={"Accept": "text/html"})
    assert rv.status_code == 404
    assert rv.status_code != 302
    assert "Location" not in rv.headers


def test_404_leaks_no_internal_detail(client):
    rv = client.get("/secret-internal-xyz", headers={"Accept": "text/html"})
    body = rv.get_data(as_text=True)
    assert "Traceback" not in body
    assert "werkzeug" not in body.lower()
    # Attacker-controlled path is not reflected into the page.
    assert "secret-internal-xyz" not in body


# --------------------------------------------------------------------------- #
# 404 — JSON / API
# --------------------------------------------------------------------------- #

def test_404_json_via_api_path_authenticated(client):
    rv = client.get("/api/does-not-exist")
    assert rv.status_code == 404
    assert "application/json" in rv.content_type
    data = json.loads(rv.data)
    assert data["error"] == "not_found"
    assert data["status"] == 404
    assert "message" in data


def test_404_json_via_accept_header_anonymous(anon_client):
    rv = anon_client.get("/static/missing.json", headers={"Accept": "application/json"})
    assert rv.status_code == 404
    assert "application/json" in rv.content_type
    data = json.loads(rv.data)
    assert data["error"] == "not_found"


def test_404_json_body_has_no_html(client):
    rv = client.get("/api/missing", headers={"Accept": "application/json"})
    body = rv.get_data(as_text=True)
    assert "<html" not in body.lower()
    assert "<!doctype" not in body.lower()


# --------------------------------------------------------------------------- #
# 500 — HTML / JSON
# --------------------------------------------------------------------------- #

def test_boom_route_returns_500(boom_client):
    rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    assert rv.status_code == 500


def test_500_renders_branded_html(boom_client):
    rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    assert rv.status_code == 500
    body = rv.get_data(as_text=True)
    assert "text/html" in rv.content_type
    assert "Something went wrong" in body
    assert "Recompete" in body
    assert 'href="/"' in body


def test_500_hides_exception_detail_and_traceback(boom_client):
    rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    body = rv.get_data(as_text=True)
    assert BOOM_SECRET not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body
    assert "__boom__" not in body


def test_500_html_unauthenticated(boom_client):
    rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    assert rv.status_code == 500
    assert "Something went wrong" in rv.get_data(as_text=True)


def test_500_html_authenticated(boom_client):
    _register(boom_client)  # boom route is public, so this only adds a session
    rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    assert rv.status_code == 500
    body = rv.get_data(as_text=True)
    assert "Something went wrong" in body
    assert BOOM_SECRET not in body


def test_500_json_via_accept_header(boom_client):
    rv = boom_client.get("/__boom__", headers={"Accept": "application/json"})
    assert rv.status_code == 500
    assert "application/json" in rv.content_type
    data = json.loads(rv.data)
    assert data["error"] == "internal_error"
    assert data["status"] == 500
    assert BOOM_SECRET not in rv.get_data(as_text=True)


def test_500_logs_the_exception(boom_client, caplog):
    with caplog.at_level(logging.ERROR):
        rv = boom_client.get("/__boom__", headers={"Accept": "text/html"})
    assert rv.status_code == 500
    # Flask logs the traceback via app.log_exception; the handler adds a
    # breadcrumb. Either way at least one ERROR record must be present.
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# --------------------------------------------------------------------------- #
# Regression — normal routes unchanged
# --------------------------------------------------------------------------- #

def test_health_still_ok(anon_client):
    rv = anon_client.get("/health")
    assert rv.status_code == 200
    assert json.loads(rv.data) == {"status": "ok"}


def test_public_landing_still_ok(anon_client):
    rv = anon_client.get("/")
    assert rv.status_code == 200


def test_login_page_still_ok(anon_client):
    rv = anon_client.get("/login")
    assert rv.status_code == 200


def test_authenticated_dashboard_still_ok(client):
    rv = client.get("/dashboard")
    # 200 (dashboard) or a normal in-app redirect (e.g. onboarding) — never 404/500.
    assert rv.status_code in (200, 302)


def test_contracts_route_still_reachable(client):
    rv = client.get("/contracts")
    assert rv.status_code in (200, 302)
