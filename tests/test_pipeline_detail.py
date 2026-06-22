"""Tests for Opportunity Pipeline Commit 3: detail page + Business Match.

Covers:
- Unauthenticated users cannot access /pipeline/<id>
- Authenticated user can view their own opportunity detail (200)
- User cannot view another user's opportunity (redirect, no 200)
- Detail page shows contract information
- Detail page shows pipeline fields (stage, next_action, notes, probability)
- Pipeline list page links to opportunity detail
- Contract detail page links to opportunity detail when in pipeline
- Update form saves and redirects back safely
- Business Match section renders when Company Profile exists
- Business Match empty state when Company Profile does not exist
"""

import sqlite3
import pytest
import db as db_module
import users as users_module
from db import add_opportunity, get_opportunity, update_opportunity, save_company_profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def detail_db(tmp_path, monkeypatch):
    """Isolated DB: alice + bob + one contract."""
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
        " (internal_id, agency, sub_agency, vendor, value, recompete_score,"
        "  priority, end_date, days_remaining, competition_type)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("CTR-001", "Dept of Defense", "Army", "Acme Corp",
         5_000_000.0, 80, "HIGH", "2026-12-31", 190, "Full and Open"),
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


def _make_client(detail_db, email="alice@example.com", authed=True):
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
def alice(detail_db):
    return _make_client(detail_db)


@pytest.fixture()
def anon(detail_db):
    return _make_client(detail_db, authed=False)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_anon_redirect(self, anon, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = anon.get(f"/pipeline/{opp_id}")
        assert r.status_code in (301, 302)

    def test_authed_can_view_own(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert r.status_code == 200

    def test_cannot_view_other_users_opp(self, detail_db):
        bob_opp_id, _ = add_opportunity(_uid(detail_db, "bob@example.com"), "CTR-001")
        alice_client = _make_client(detail_db, "alice@example.com")
        r = alice_client.get(f"/pipeline/{bob_opp_id}")
        # should redirect, not 200
        assert r.status_code in (301, 302)


# ---------------------------------------------------------------------------
# Contract data on detail page
# ---------------------------------------------------------------------------

class TestContractDataDisplay:
    def test_shows_internal_id(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"CTR-001" in r.data

    def test_shows_agency(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"Dept of Defense" in r.data

    def test_shows_vendor(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"Acme Corp" in r.data

    def test_shows_value(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"5,000,000" in r.data

    def test_shows_end_date(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"2026-12-31" in r.data

    def test_shows_recompete_score(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"80" in r.data

    def test_shows_contract_detail_link(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"/contract/CTR-001" in r.data


# ---------------------------------------------------------------------------
# Pipeline fields on detail page
# ---------------------------------------------------------------------------

class TestPipelineFieldsDisplay:
    def test_shows_stage(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"new" in r.data.lower() or b"New" in r.data

    def test_shows_next_action_after_update(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"next_action": "Draft capability statement"})
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"Draft capability statement" in r.data

    def test_shows_notes_after_update(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"notes": "Strong incumbent relationship"})
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"Strong incumbent relationship" in r.data

    def test_shows_probability_after_update(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"probability": "65"})
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"65" in r.data

    def test_stage_selector_in_update_form(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b'name="stage"' in r.data

    def test_back_to_pipeline_link(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"/pipeline" in r.data


# ---------------------------------------------------------------------------
# Update form submission
# ---------------------------------------------------------------------------

class TestUpdateForm:
    def test_update_redirects(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        r = alice.post(f"/pipeline/update/{opp_id}",
                       data={"stage": "capturing", "notes": "test note",
                             "next_action": "Call PM", "next_action_due": "2026-08-01",
                             "probability": "70"})
        assert r.status_code in (301, 302)

    def test_update_persists_fields(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        alice.post(f"/pipeline/update/{opp_id}",
                   data={"stage": "capturing", "notes": "test note",
                         "next_action": "Call PM", "next_action_due": "2026-08-01",
                         "probability": "70"})
        opp = get_opportunity(uid, opp_id)
        assert opp["stage"] == "capturing"
        assert opp["notes"] == "test note"
        assert opp["next_action"] == "Call PM"
        assert opp["probability"] == 70

    def test_update_flash_visible_on_detail_page(self, alice, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        r = alice.post(f"/pipeline/update/{opp_id}",
                       data={"stage": "interested", "notes": "",
                             "next_action": "", "next_action_due": "", "probability": ""},
                       follow_redirects=True)
        assert b"Pipeline updated" in r.data


# ---------------------------------------------------------------------------
# Pipeline list links to detail
# ---------------------------------------------------------------------------

class TestPipelineListLinks:
    def test_pipeline_list_links_to_detail(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get("/pipeline")
        assert f"/pipeline/{opp_id}".encode() in r.data


# ---------------------------------------------------------------------------
# Contract detail links to opportunity detail when in pipeline
# ---------------------------------------------------------------------------

class TestContractDetailPipelineLink:
    def test_in_pipeline_badge_links_to_detail(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contract/CTR-001")
        assert f"/pipeline/{opp_id}".encode() in r.data


# ---------------------------------------------------------------------------
# Business Match integration
# ---------------------------------------------------------------------------

class TestBusinessMatchDisplay:
    def test_biz_match_shown_with_profile(self, detail_db):
        uid = _uid(detail_db, "alice@example.com")
        save_company_profile(uid, {"company_name": "Acme", "naics_codes": ["561720"]})
        opp_id, _ = add_opportunity(uid, "CTR-001")
        alice_client = _make_client(detail_db, "alice@example.com")
        r = alice_client.get(f"/pipeline/{opp_id}")
        assert b"Business Match" in r.data
        assert b"%" in r.data

    def test_biz_match_empty_state_without_profile(self, alice, detail_db):
        opp_id, _ = add_opportunity(_uid(detail_db, "alice@example.com"), "CTR-001")
        r = alice.get(f"/pipeline/{opp_id}")
        assert b"Business Match" in r.data
        assert b"Company Profile" in r.data

    def test_biz_match_no_crash_when_contract_missing(self, detail_db):
        """Orphaned opportunity (no contract row) should still load without error."""
        uid = _uid(detail_db, "alice@example.com")
        save_company_profile(uid, {"company_name": "Acme"})
        opp_id, _ = add_opportunity(uid, "CTR-GHOST")
        alice_client = _make_client(detail_db, "alice@example.com")
        r = alice_client.get(f"/pipeline/{opp_id}")
        assert r.status_code == 200
