"""Tests for the unified access control layers.

Layer separation:
- access.get_access_state  -> pure domain state (no URLs/Flask)
- app.get_access_redirect  -> pure web mapping (state -> path)
- app.require_access       -> single before_request orchestrator (flag-gated)

Validates: domain correctness, web mapping, no Flask in the domain module,
flag OFF == current behavior, and the flag ON access matrix.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import db as db_module
import users as users_module
import access
from access import (
    get_access_state,
    is_access_granted,
    ALLOWED, TRIALING, BILLING_REQUIRED, EXPIRED,
)


NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _ts(days):
    return (NOW + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Domain layer — get_access_state (pure)
# ---------------------------------------------------------------------------

class TestDomainState:
    def test_active_workspace_allowed(self):
        assert get_access_state({}, {"subscription_status": "active"}, now=NOW) == ALLOWED

    def test_user_subscription_is_not_an_authority(self):
        # LOCKED: workspace is the sole authority. A user-level active sub with
        # no workspace does NOT grant access.
        assert get_access_state({"subscription_status": "active"}, None, now=NOW) == BILLING_REQUIRED

    def test_live_workspace_trial_trialing(self):
        ws = {"subscription_status": "trialing", "trial_end_at": _ts(3)}
        assert get_access_state({}, ws, now=NOW) == TRIALING

    def test_user_trial_is_not_an_authority(self):
        # A user-level trial alone, with no workspace, is not entitlement.
        user = {"subscription_status": "trialing", "trial_ends_at": _ts(2)}
        assert get_access_state(user, None, now=NOW) == BILLING_REQUIRED

    def test_expired_trial_expired(self):
        ws = {"subscription_status": "trialing", "trial_end_at": _ts(-1)}
        assert get_access_state({}, ws, now=NOW) == EXPIRED

    def test_no_markers_billing_required(self):
        assert get_access_state({}, {}, now=NOW) == BILLING_REQUIRED
        assert get_access_state(None, None, now=NOW) == BILLING_REQUIRED

    def test_active_overrides_expired_trial(self):
        ws = {"subscription_status": "active", "trial_end_at": _ts(-5)}
        assert get_access_state({}, ws, now=NOW) == ALLOWED

    def test_workspace_authority_ignores_user_state(self):
        # User state never rescues or overrides the workspace, in either direction.
        expired_user = {"subscription_status": "trialing", "trial_ends_at": _ts(-10)}
        live_ws = {"subscription_status": "trialing", "trial_end_at": _ts(1)}
        assert get_access_state(expired_user, live_ws, now=NOW) == TRIALING

        active_user = {"subscription_status": "active"}
        expired_ws = {"subscription_status": "canceled", "trial_end_at": _ts(-1)}
        assert get_access_state(active_user, expired_ws, now=NOW) == EXPIRED

    def test_deterministic(self):
        ws = {"subscription_status": "trialing", "trial_end_at": _ts(1)}
        a = get_access_state({}, ws, now=NOW)
        b = get_access_state({}, ws, now=NOW)
        assert a == b == TRIALING

    def test_is_access_granted(self):
        assert is_access_granted(ALLOWED) and is_access_granted(TRIALING)
        assert not is_access_granted(EXPIRED)
        assert not is_access_granted(BILLING_REQUIRED)

    def test_domain_module_has_no_flask_dependency(self):
        # The domain layer must not import Flask/web concerns. Inspect actual
        # import statements (not docstrings) via the AST.
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(access))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "flask" not in imported
        assert "app" not in imported  # no dependency cycle into the web layer


# ---------------------------------------------------------------------------
# Web layer — get_access_redirect (pure mapping)
# ---------------------------------------------------------------------------

class TestWebMapping:
    def test_billing_required_maps_to_billing(self):
        import app as app_module
        assert app_module.get_access_redirect(BILLING_REQUIRED) == "/settings/billing"

    def test_expired_maps_to_billing_expired(self):
        import app as app_module
        assert app_module.get_access_redirect(EXPIRED) == "/settings/billing?expired=1"

    def test_allowed_and_trialing_map_to_none(self):
        import app as app_module
        assert app_module.get_access_redirect(ALLOWED) is None
        assert app_module.get_access_redirect(TRIALING) is None


# ---------------------------------------------------------------------------
# Enforcement — flag OFF (parity) and flag ON (matrix)
# ---------------------------------------------------------------------------

@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("acc@example.com", "password123", company_name="Acme")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email='acc@example.com'").fetchone()[0]
    con.close()
    return uid


def _expire_workspace(workspace_id):
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE workspaces SET trial_end_at = :t WHERE id = :id"),
            {"t": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "id": workspace_id},
        )


@pytest.fixture()
def client(pdb):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    app_module.app.config["RATELIMIT_ENABLED"] = False
    app_module.app.secret_key = "test-secret"
    with app_module.app.test_client() as c:
        yield c


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


class TestFlagOffParity:
    """With the flag OFF (default), behavior is identical to the legacy system."""

    def test_unified_gate_dormant_when_off(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", False)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        _login(client, uid)
        # Legacy workspace gate still drives the redirect to /settings/billing.
        resp = client.get("/contracts")
        assert resp.status_code == 302
        assert "/settings/billing" in resp.headers["Location"]

    def test_legacy_user_gate_still_redirects_to_subscribe(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", False)
        uid = _uid(pdb)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with db_module.get_engine().begin() as conn:
            conn.execute(text("UPDATE users SET trial_ends_at = :t WHERE id = :id"),
                         {"t": past, "id": uid})
        _login(client, uid)
        resp = client.get("/contracts")
        assert resp.status_code == 302
        assert "/subscribe" in resp.headers["Location"]


class TestFlagOnMatrix:
    """With the flag ON, the single unified gate decides; legacy billing is dormant."""

    def test_active_trial_allowed(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        db_module.get_or_create_workspace_for_user(uid)  # fresh trial
        _login(client, uid)
        resp = client.get("/dashboard")
        assert "/settings/billing" not in (resp.headers.get("Location") or "")

    def test_active_subscription_allowed(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        db_module.update_workspace_subscription_status(ws["id"], "active")
        _login(client, uid)
        resp = client.get("/dashboard")
        assert "/settings/billing" not in (resp.headers.get("Location") or "")

    def test_expired_redirects_to_billing(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        _login(client, uid)
        resp = client.get("/dashboard")
        assert resp.status_code == 302
        assert "/settings/billing" in resp.headers["Location"]

    def test_anonymous_still_handled_by_require_login(self, client, pdb, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        # No login → require_login redirects to the login page, not billing.
        resp = client.get("/dashboard")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unified_gate_does_not_redirect_to_subscribe(self, client, pdb, monkeypatch):
        # When unified, expired access goes to the canonical /settings/billing,
        # never the legacy /subscribe page.
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        _login(client, uid)
        resp = client.get("/contracts")
        assert "/subscribe" not in resp.headers["Location"]
        assert "/settings/billing" in resp.headers["Location"]
