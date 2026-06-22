"""Tests for Opportunity Pipeline routes and templates (Commit 2).

Covers:
- Auth guard: anon users redirected, authed users get 200 + nav
- Empty pipeline state: message + CTA
- Populated pipeline: contract row, stage selector, remove button, count
- pipeline_add: redirects, creates opp, flash, idempotent, anon guard
- pipeline_remove: redirects, removes, flash, no-op, anon guard, IDOR (db layer)
- pipeline_update: stage persists, flash success, invalid stage flash, IDOR (db layer)
- contract_detail: Add button when not in pipeline, In Pipeline + Remove when added
"""

import sqlite3
import pytest
import db as db_module
import users as users_module
from db import (
    add_opportunity,
    get_opportunity,
    get_opportunity_by_contract,
    remove_opportunity,
    update_opportunity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipe_db(tmp_path, monkeypatch):
    """Isolated DB with alice + bob and one contract."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    users_module.create_user("alice@example.com", "pw123456")
    users_module.create_user("bob@example.com", "pw123456")
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR IGNORE INTO contracts"
        " (internal_id, agency, vendor, value, recompete_score, end_date, days_remaining)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("CTR-001", "DoD", "Acme Corp", 5_000_000.0, 80, "2026-12-31", 190),
    )
    con.commit()
    con.close()
    yield db_path
    db_module._cached_engine.cache_clear()


def _uid(db_path, email):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    con.close()
    return uid


def _make_client(pipe_db, email="alice@example.com", authed=True):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    c = flask_app.app.test_client()
    if authed:
        c.post("/login", data={"email": email, "password": "pw123456"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
    return c


@pytest.fixture()
def alice(pipe_db):
    return _make_client(pipe_db, "alice@example.com")


@pytest.fixture()
def anon(pipe_db):
    return _make_client(pipe_db, authed=False)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_pipeline_anon_redirects(self, anon):
        r = anon.get("/pipeline")
        assert r.status_code in (301, 302)

    def test_pipeline_authed_200(self, alice):
        r = alice.get("/pipeline")
        assert r.status_code == 200

    def test_pipeline_nav_present(self, alice):
        r = alice.get("/pipeline")
        assert b"Pipeline" in r.data

    def test_add_anon_redirects(self, anon):
        r = anon.post("/pipeline/add/CTR-001")
        assert r.status_code in (301, 302)

    def test_remove_anon_redirects(self, anon):
        r = anon.post("/pipeline/remove/CTR-001")
        assert r.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Empty pipeline page
# ---------------------------------------------------------------------------

class TestEmptyPipeline:
    def test_empty_message(self, alice):
        r = alice.get("/pipeline")
        assert b"No opportunities" in r.data

    def test_browse_contracts_cta(self, alice):
        r = alice.get("/pipeline")
        assert b"Browse contracts" in r.data


# ---------------------------------------------------------------------------
# Populated pipeline page
# ---------------------------------------------------------------------------

class TestPopulatedPipeline:
    def test_contract_link_shown(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert b"CTR-001" in r.data

    def test_stage_selector_present(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert b"<select" in r.data
        assert b'name="stage"' in r.data

    def test_remove_button_present(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert b"Remove" in r.data

    def test_count_shown(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert b"1 opportunity" in r.data

    def test_does_not_show_others_opportunities(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "bob@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert b"CTR-001" not in r.data


# ---------------------------------------------------------------------------
# pipeline_add
# ---------------------------------------------------------------------------

class TestPipelineAdd:
    def test_add_redirects(self, alice):
        r = alice.post("/pipeline/add/CTR-001")
        assert r.status_code in (301, 302)

    def test_add_creates_opportunity(self, alice, pipe_db):
        alice.post("/pipeline/add/CTR-001")
        opp = get_opportunity_by_contract(_uid(pipe_db, "alice@example.com"), "CTR-001")
        assert opp is not None
        assert opp["stage"] == "new"

    def test_add_flash_created(self, alice):
        r = alice.post("/pipeline/add/CTR-001", follow_redirects=True)
        assert b"Added to your pipeline" in r.data

    def test_add_idempotent_flash(self, alice, pipe_db):
        alice.post("/pipeline/add/CTR-001")
        r = alice.post("/pipeline/add/CTR-001", follow_redirects=True)
        assert b"Already in your pipeline" in r.data

    def test_add_does_not_affect_other_user(self, alice, pipe_db):
        alice.post("/pipeline/add/CTR-001")
        opp = get_opportunity_by_contract(_uid(pipe_db, "bob@example.com"), "CTR-001")
        assert opp is None


# ---------------------------------------------------------------------------
# pipeline_remove
# ---------------------------------------------------------------------------

class TestPipelineRemove:
    def test_remove_redirects(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.post("/pipeline/remove/CTR-001")
        assert r.status_code in (301, 302)

    def test_remove_deletes_opportunity(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        alice.post("/pipeline/remove/CTR-001")
        opp = get_opportunity_by_contract(_uid(pipe_db, "alice@example.com"), "CTR-001")
        assert opp is None

    def test_remove_flash(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.post("/pipeline/remove/CTR-001", follow_redirects=True)
        assert b"Removed from your pipeline" in r.data

    def test_remove_noop_on_missing(self, alice):
        r = alice.post("/pipeline/remove/CTR-999")
        assert r.status_code in (301, 302)

    def test_remove_cannot_delete_other_users_opp_via_idor(self, pipe_db):
        """Bob's opp cannot be removed by alice (db-layer scoping)."""
        bob_uid = _uid(pipe_db, "bob@example.com")
        add_opportunity(bob_uid, "CTR-001")
        # Attempt removal scoped to alice — should be no-op
        alice_uid = _uid(pipe_db, "alice@example.com")
        remove_opportunity(alice_uid, "CTR-001")
        opp = get_opportunity_by_contract(bob_uid, "CTR-001")
        assert opp is not None


# ---------------------------------------------------------------------------
# pipeline_update
# ---------------------------------------------------------------------------

class TestPipelineUpdate:
    def test_update_stage_persists(self, alice, pipe_db):
        opp_id, _ = add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.post(f"/pipeline/update/{opp_id}",
                       data={"stage": "interested", "notes": "", "next_action": "",
                             "next_action_due": "", "probability": ""})
        assert r.status_code in (301, 302)
        opp = get_opportunity(_uid(pipe_db, "alice@example.com"), opp_id)
        assert opp["stage"] == "interested"

    def test_update_flash_success(self, alice, pipe_db):
        opp_id, _ = add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.post(f"/pipeline/update/{opp_id}",
                       data={"stage": "researching", "notes": "", "next_action": "",
                             "next_action_due": "", "probability": ""},
                       follow_redirects=True)
        assert b"Pipeline updated" in r.data

    def test_update_invalid_stage_flash_error(self, alice, pipe_db):
        opp_id, _ = add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.post(f"/pipeline/update/{opp_id}",
                       data={"stage": "badstage", "notes": "", "next_action": "",
                             "next_action_due": "", "probability": ""},
                       follow_redirects=True)
        assert b"Invalid pipeline stage" in r.data

    def test_update_idor_db_layer(self, pipe_db):
        """update_opportunity raises LookupError for wrong owner."""
        bob_uid = _uid(pipe_db, "bob@example.com")
        alice_uid = _uid(pipe_db, "alice@example.com")
        opp_id, _ = add_opportunity(bob_uid, "CTR-001")
        with pytest.raises(LookupError):
            update_opportunity(alice_uid, opp_id, {"stage": "interested"})


# ---------------------------------------------------------------------------
# Contract detail pipeline integration
# ---------------------------------------------------------------------------

class TestContractDetailPipeline:
    def test_add_button_when_not_in_pipeline(self, alice):
        r = alice.get("/contract/CTR-001")
        assert r.status_code == 200
        assert b"Add to Pipeline" in r.data

    def test_in_pipeline_badge_when_added(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contract/CTR-001")
        assert b"In Pipeline" in r.data

    def test_remove_button_when_in_pipeline(self, alice, pipe_db):
        add_opportunity(_uid(pipe_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contract/CTR-001")
        assert b"/pipeline/remove/CTR-001" in r.data
