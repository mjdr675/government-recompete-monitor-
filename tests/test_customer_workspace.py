"""Tests for Customer Workspace Phase 1.

Covers:
- workspaces / workspace_members tables and DB helpers
- lazy workspace provisioning (seeded from company_name, owner membership)
- workspace settings page: name edit + logo upload (+ validation, removal)
- branding (workspace name/logo) displayed app-wide via context processor
"""
import io
import os
import sqlite3

import pytest

import db as db_module
import users as users_module
from db import (
    get_workspace_for_user,
    get_or_create_workspace_for_user,
    update_workspace,
    list_workspace_members,
)


@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("ws@example.com", "password123", company_name="Acme Federal")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email='ws@example.com'").fetchone()[0]
    con.close()
    return uid


@pytest.fixture()
def authed_client(pdb, tmp_path, monkeypatch):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    # Redirect logo storage to a temp dir so tests never touch the repo tree.
    logo_dir = str(tmp_path / "logos")
    monkeypatch.setattr(flask_app, "WORKSPACE_LOGO_DIR", logo_dir)
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "ws@example.com", "password": "password123"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------

class TestWorkspaceDB:
    def test_tables_created(self, pdb):
        con = sqlite3.connect(pdb)
        names = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('workspaces','workspace_members')"
            )
        }
        con.close()
        assert names == {"workspaces", "workspace_members"}

    def test_get_workspace_none_before_create(self, pdb):
        uid = _uid(pdb)
        assert get_workspace_for_user(uid) is None

    def test_lazy_provision_seeds_name_and_owner(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        assert ws is not None
        assert ws["name"] == "Acme Federal"   # seeded from company_name
        assert ws["role"] == "owner"
        members = list_workspace_members(ws["id"])
        assert len(members) == 1
        assert members[0]["email"] == "ws@example.com"
        assert members[0]["role"] == "owner"

    def test_provision_is_idempotent(self, pdb):
        uid = _uid(pdb)
        ws1 = get_or_create_workspace_for_user(uid)
        ws2 = get_or_create_workspace_for_user(uid)
        assert ws1["id"] == ws2["id"]
        assert len(list_workspace_members(ws1["id"])) == 1

    def test_update_workspace_name_and_logo(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace(ws["id"], name="New Co", logo_path="uploads/logos/x.png")
        updated = get_workspace_for_user(uid)
        assert updated["name"] == "New Co"
        assert updated["logo_path"] == "uploads/logos/x.png"

    def test_update_workspace_partial_leaves_other_field(self, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace(ws["id"], logo_path="uploads/logos/y.png")
        update_workspace(ws["id"], name="Renamed")
        updated = get_workspace_for_user(uid)
        assert updated["name"] == "Renamed"
        assert updated["logo_path"] == "uploads/logos/y.png"  # preserved

    def test_provision_handles_blank_company_name(self, pdb):
        users_module.create_user("blank@example.com", "password123")
        con = sqlite3.connect(pdb)
        uid = con.execute("SELECT id FROM users WHERE email='blank@example.com'").fetchone()[0]
        con.close()
        ws = get_or_create_workspace_for_user(uid)
        assert ws is not None
        assert ws["name"] is None


# ---------------------------------------------------------------------------
# Workspace settings page
# ---------------------------------------------------------------------------

class TestWorkspaceSettingsPage:
    def test_page_renders(self, authed_client):
        rv = authed_client.get("/settings/workspace")
        assert rv.status_code == 200
        body = rv.get_data(as_text=True)
        assert "Workspace Settings" in body
        assert "Team Members" in body
        # Owner listed as a member.
        assert "ws@example.com" in body

    def test_update_name(self, authed_client, pdb):
        authed_client.post("/settings/workspace", data={"workspace_name": "Renamed Corp"})
        uid = _uid(pdb)
        assert get_workspace_for_user(uid)["name"] == "Renamed Corp"

    def test_logo_upload_accepted(self, authed_client, pdb):
        data = {
            "workspace_name": "Acme Federal",
            "logo": (io.BytesIO(b"\x89PNG\r\n\x1a\n fake png bytes"), "logo.png"),
        }
        rv = authed_client.post("/settings/workspace", data=data,
                                content_type="multipart/form-data")
        assert rv.status_code == 200
        uid = _uid(pdb)
        ws = get_workspace_for_user(uid)
        assert ws["logo_path"] == f"uploads/logos/workspace_{ws['id']}.png"

    def test_logo_upload_rejects_bad_extension(self, authed_client, pdb):
        data = {
            "workspace_name": "Acme Federal",
            "logo": (io.BytesIO(b"malware"), "evil.exe"),
        }
        rv = authed_client.post("/settings/workspace", data=data,
                                content_type="multipart/form-data")
        body = rv.get_data(as_text=True)
        assert "Logo must be" in body
        uid = _uid(pdb)
        assert get_workspace_for_user(uid)["logo_path"] is None

    def test_remove_logo(self, authed_client, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace(ws["id"], logo_path="uploads/logos/workspace_1.png")
        authed_client.post("/settings/workspace", data={"action": "remove_logo"})
        assert get_workspace_for_user(uid)["logo_path"] is None


# ---------------------------------------------------------------------------
# Branding displayed app-wide
# ---------------------------------------------------------------------------

class TestBrandingDisplay:
    def test_workspace_name_in_sidebar(self, authed_client, pdb):
        # Provision + name the workspace, then load any authed page.
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace(ws["id"], name="Brandable LLC")
        body = authed_client.get("/dashboard").get_data(as_text=True)
        assert "Brandable LLC" in body

    def test_logo_rendered_when_present(self, authed_client, pdb):
        uid = _uid(pdb)
        ws = get_or_create_workspace_for_user(uid)
        update_workspace(ws["id"], logo_path="uploads/logos/workspace_1.png")
        body = authed_client.get("/dashboard").get_data(as_text=True)
        assert "uploads/logos/workspace_1.png" in body
