"""Tests for the access-decision observability layer (pure instrumentation)."""
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import db as db_module
import users as users_module
from access_observability import build_access_record, log_access_decision


# ---------------------------------------------------------------------------
# Pure record builder
# ---------------------------------------------------------------------------

class TestBuildRecord:
    def test_basic_record(self):
        rec = build_access_record("u1", "w1", "expired", "/settings/billing",
                                  "unified", "/dashboard")
        assert rec["event"] == "access_decision"
        assert rec["mode"] == "unified"
        assert rec["user_id"] == "u1"
        assert rec["workspace_id"] == "w1"
        assert rec["state"] == "expired"
        assert rec["granted"] is False
        assert rec["redirect_path"] == "/settings/billing"
        assert rec["request_path"] == "/dashboard"

    def test_granted_states(self):
        assert build_access_record(1, 1, "allowed", None, "unified", "/x")["granted"] is True
        assert build_access_record(1, 1, "trialing", None, "unified", "/x")["granted"] is True
        assert build_access_record(1, 1, "expired", "/b", "unified", "/x")["granted"] is False
        assert build_access_record(1, 1, "billing_required", "/b", "unified", "/x")["granted"] is False

    def test_state_dict_is_normalized(self):
        rec = build_access_record(1, 1, {"state": "allowed"}, None, "legacy", "/x")
        assert rec["state"] == "allowed"
        assert rec["granted"] is True

    def test_none_ids_serialized_as_none(self):
        rec = build_access_record(None, None, "billing_required", "/b", "shadow", "/x")
        assert rec["user_id"] is None
        assert rec["workspace_id"] is None

    def test_ids_coerced_to_string(self):
        rec = build_access_record(7, 9, "allowed", None, "unified", "/x")
        assert rec["user_id"] == "7" and rec["workspace_id"] == "9"


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class TestLogAccessDecision:
    def test_emits_to_access_audit_logger(self, caplog):
        with caplog.at_level(logging.INFO, logger="access.audit"):
            log_access_decision("u1", "w1", "expired", "/settings/billing",
                                "unified", "/dashboard")
        msgs = [r.getMessage() for r in caplog.records if r.name == "access.audit"]
        assert len(msgs) == 1
        payload = json.loads(msgs[0])
        assert payload["state"] == "expired" and payload["mode"] == "unified"

    def test_returns_record(self):
        rec = log_access_decision("u", "w", "allowed", None, "unified", "/x")
        assert rec["granted"] is True

    def test_never_raises_on_bad_input(self):
        # A non-serializable state value must not bubble up from instrumentation.
        class Bad:
            pass
        assert log_access_decision("u", "w", Bad(), None, "x", "/p") is None


# ---------------------------------------------------------------------------
# Integration with the gates
# ---------------------------------------------------------------------------

@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("obs@example.com", "password123", company_name="Acme")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email='obs@example.com'").fetchone()[0]
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


def _decisions(caplog, mode=None):
    out = []
    for r in caplog.records:
        if r.name != "access.audit":
            continue
        try:
            p = json.loads(r.getMessage())
        except ValueError:
            continue
        if mode is None or p.get("mode") == mode:
            out.append(p)
    return out


class TestGateInstrumentation:
    def test_legacy_workspace_redirect_logged(self, client, pdb, monkeypatch, caplog):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", False)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        _login(client, uid)
        with caplog.at_level(logging.INFO, logger="access.audit"):
            client.get("/contracts")
        legacy = _decisions(caplog, "legacy")
        assert any(d["redirect_path"] == "/settings/billing?expired=1"
                   and d["state"] == "expired" for d in legacy)

    def test_shadow_logged_when_flag_off(self, client, pdb, monkeypatch, caplog):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", False)
        uid = _uid(pdb)
        db_module.get_or_create_workspace_for_user(uid)  # fresh trial
        _login(client, uid)
        with caplog.at_level(logging.INFO, logger="access.audit"):
            client.get("/dashboard")
        shadow = _decisions(caplog, "shadow")
        # Shadow observer records the would-be unified decision (trialing -> granted).
        assert any(d["state"] == "trialing" and d["granted"] is True for d in shadow)

    def test_unified_decision_logged_when_flag_on(self, client, pdb, monkeypatch, caplog):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        ws = db_module.get_or_create_workspace_for_user(uid)
        _expire_workspace(ws["id"])
        _login(client, uid)
        with caplog.at_level(logging.INFO, logger="access.audit"):
            client.get("/dashboard")
        unified = _decisions(caplog, "unified")
        assert any(d["state"] == "expired" and d["granted"] is False
                   and d["redirect_path"] == "/settings/billing?expired=1"
                   for d in unified)

    def test_no_shadow_when_flag_on(self, client, pdb, monkeypatch, caplog):
        import app as app_module
        monkeypatch.setattr(app_module, "UNIFIED_ACCESS_ENABLED", True)
        uid = _uid(pdb)
        db_module.get_or_create_workspace_for_user(uid)
        _login(client, uid)
        with caplog.at_level(logging.INFO, logger="access.audit"):
            client.get("/dashboard")
        assert _decisions(caplog, "shadow") == []
