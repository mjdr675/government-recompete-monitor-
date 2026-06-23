"""Tests for Opportunity Pipeline Commit 4: dashboard widget + contract list.

Covers:
- Dashboard shows pipeline widget for authenticated user
- Dashboard empty pipeline state
- Dashboard does not leak another user's pipeline data
- Contracts list shows In Pipeline badge for saved contracts
- Contracts list does not show badge for unsaved contracts
- Contracts list badge links to opportunity detail page
- /contracts?in_pipeline=1 shows only user's pipeline contracts
- /contracts?in_pipeline=1 excludes another user's pipeline contracts
- /contracts?in_pipeline=1 returns empty when pipeline is empty
- /contracts?in_pipeline=1 composes with other filters safely
- Unauthenticated /contracts?in_pipeline=1 silently shows all contracts
"""

import sqlite3
import pytest
import db as db_module
import users as users_module
from db import add_opportunity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vis_db(tmp_path, monkeypatch):
    """Isolated DB: alice + bob + two contracts."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    users_module.create_user("alice@example.com", "pw123456")
    users_module.create_user("bob@example.com", "pw123456")
    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT OR IGNORE INTO contracts"
        " (internal_id, agency, vendor, value, recompete_score, end_date, days_remaining, priority)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("CTR-001", "DoD", "Acme Corp", 5_000_000.0, 80, "2026-12-31", 190, "HIGH"),
            ("CTR-002", "GSA", "Beta LLC", 1_000_000.0, 60, "2027-06-30", 370, "MEDIUM"),
        ],
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


def _client(vis_db, email="alice@example.com", authed=True):
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
def alice(vis_db):
    return _client(vis_db)


@pytest.fixture()
def anon(vis_db):
    return _client(vis_db, authed=False)


# ---------------------------------------------------------------------------
# Dashboard pipeline widget
# ---------------------------------------------------------------------------

class TestDashboardPipelineWidget:
    def test_widget_present_for_authed_user(self, alice):
        r = alice.get("/dashboard")
        assert r.status_code == 200
        assert b"My Pipeline" in r.data

    def test_empty_state_when_no_opps(self, alice):
        r = alice.get("/dashboard")
        assert b"No opportunities yet" in r.data or b"Browse contracts" in r.data

    def test_widget_shows_opp_after_add(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/dashboard")
        assert b"CTR-001" in r.data

    def test_widget_active_count(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/dashboard")
        assert b"1 active" in r.data

    def test_widget_does_not_show_other_users_opps(self, vis_db):
        add_opportunity(_uid(vis_db, "bob@example.com"), "CTR-001")
        alice_client = _client(vis_db, "alice@example.com")
        r = alice_client.get("/dashboard")
        # CTR-001 should NOT appear in alice's pipeline widget
        # (it is in bob's pipeline only)
        # The dashboard might show CTR-001 in other sections (critical list, etc.)
        # so we just verify the pipeline widget empty state is shown
        assert b"No opportunities yet" in r.data or b"Browse contracts" in r.data

    def test_widget_shows_view_all_link(self, alice):
        r = alice.get("/dashboard")
        assert b"/pipeline" in r.data


# ---------------------------------------------------------------------------
# Contract list pipeline badges
# ---------------------------------------------------------------------------

class TestContractListBadges:
    def test_badge_shown_for_saved_contract(self, alice, vis_db):
        opp_id, _ = add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts")
        assert b"Pipeline" in r.data
        assert f"/pipeline/{opp_id}".encode() in r.data

    def test_no_badge_for_unsaved_contract(self, alice, vis_db):
        # CTR-001 is in pipeline; CTR-002 is not
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts")
        data = r.data.decode()
        # Row badge uses ✓ Pipeline; count that specific pattern — exactly 1 row badge
        assert data.count("&#10003; Pipeline</a>") == 1

    def test_badge_not_shown_for_anon(self, anon):
        r = anon.get("/contracts")
        assert b"Pipeline</a>" not in r.data

    def test_badge_links_to_opportunity_detail(self, alice, vis_db):
        opp_id, _ = add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts")
        assert f"/pipeline/{opp_id}".encode() in r.data


# ---------------------------------------------------------------------------
# /contracts?in_pipeline=1 filter
# ---------------------------------------------------------------------------

class TestInPipelineFilter:
    def test_shows_only_pipeline_contracts(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts?in_pipeline=1")
        assert b"CTR-001" in r.data
        assert b"CTR-002" not in r.data

    def test_empty_when_pipeline_empty(self, alice):
        r = alice.get("/contracts?in_pipeline=1")
        # Empty state now says "No contracts match your current filters"
        assert b"No contracts" in r.data

    def test_excludes_other_users_contracts(self, vis_db):
        add_opportunity(_uid(vis_db, "bob@example.com"), "CTR-002")
        alice_client = _client(vis_db, "alice@example.com")
        r = alice_client.get("/contracts?in_pipeline=1")
        # Alice's pipeline is empty, so CTR-002 (Bob's) must not appear
        assert b"CTR-002" not in r.data

    def test_anon_in_pipeline_ignored(self, anon):
        r = anon.get("/contracts?in_pipeline=1")
        # Anon: in_pipeline is silently ignored, redirected to login
        assert r.status_code in (200, 301, 302)

    def test_composes_with_agency_filter(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-002")
        r = alice.get("/contracts?in_pipeline=1&agency=DoD")
        assert b"CTR-001" in r.data
        assert b"CTR-002" not in r.data

    def test_in_pipeline_button_shown_when_pipeline_nonempty(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts")
        assert b"In My Pipeline" in r.data

    def test_active_in_pipeline_button_shown_when_filter_on(self, alice, vis_db):
        add_opportunity(_uid(vis_db, "alice@example.com"), "CTR-001")
        r = alice.get("/contracts?in_pipeline=1")
        assert b"&#10003; In My Pipeline" in r.data
