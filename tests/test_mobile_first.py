"""Tests for Mobile-First Phase 1 and Phase 2 experience.

Covers:
- Bottom nav present and contains required links for authenticated users
- Bottom nav absent for anonymous users
- Dashboard mobile greeting section exists
- Dashboard mobile-today / Next Best Action section renders for auth users
- Dashboard quick-stat chips render when data exists
- Dashboard hides low-priority sections with m-hide on mobile
- Contracts page has mobile card section (m-show) alongside desktop table
- Pipeline page has mobile cards section
- Pipeline stage tabs have scrollable wrapper class
- Contract detail page has mobile CTA bar (watch + pipeline actions)
- Watchlist badge in bottom nav when watchlist count > 0
- All primary authenticated routes return 200
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
def mobile_db(tmp_path, monkeypatch):
    """Isolated DB with one user and a pair of contracts."""
    db_path = str(tmp_path / "mobile_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    users_module.create_user("mobile@example.com", "pw123456")
    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT OR IGNORE INTO contracts"
        " (internal_id, agency, vendor, value, recompete_score, end_date, days_remaining, priority)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("MOB-001", "DoD", "Acme Corp", 5_000_000.0, 85, "2026-09-30", 100, "HIGH"),
            ("MOB-002", "GSA", "Beta LLC", 500_000.0, 60, "2027-03-31", 283, "MEDIUM"),
        ],
    )
    con.commit()
    con.close()
    yield db_path
    db_module._cached_engine.cache_clear()


def _authed_client(mobile_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    c = flask_app.app.test_client()
    c.post("/login", data={"email": "mobile@example.com", "password": "pw123456"})
    with c.session_transaction() as sess:
        sess["onboarding_skipped"] = "1"
    return c


def _anon_client(mobile_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    return flask_app.app.test_client()


@pytest.fixture()
def auth(mobile_db):
    return _authed_client(mobile_db)


@pytest.fixture()
def anon(mobile_db):
    return _anon_client(mobile_db)


# ---------------------------------------------------------------------------
# Bottom navigation
# ---------------------------------------------------------------------------

class TestBottomNav:
    def test_bottom_nav_present_for_auth_user(self, auth):
        rv = auth.get("/dashboard")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert 'class="bottom-nav"' in body

    def test_bottom_nav_has_required_links(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'href="/dashboard"' in body
        assert 'href="/contracts"' in body
        assert 'href="/pipeline"' in body
        assert 'href="/watchlist"' in body
        assert 'href="/company-profile"' in body

    def test_bottom_nav_absent_for_anon(self, anon):
        rv = anon.get("/")
        body = rv.data.decode()
        assert 'class="bottom-nav"' not in body

    def test_bottom_nav_active_class_on_dashboard(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'bottom-nav-item active' in body

    def test_bottom_nav_watchlist_badge_when_items_present(self, mobile_db, auth):
        # Add a contract to watchlist so g.watchlist_count > 0
        auth.post(
            "/watchlist/add",
            json={"internal_id": "MOB-001", "csrf_token": ""},
            content_type="application/json",
        )
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert "bottom-nav-badge" in body


# ---------------------------------------------------------------------------
# Dashboard mobile sections
# ---------------------------------------------------------------------------

class TestDashboardMobileSections:
    def test_mobile_greeting_section_present(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'class="mobile-greeting"' in body

    def test_mobile_greeting_text_element(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'id="mobile-greeting-text"' in body

    def test_mobile_today_section_present_for_auth(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'mobile-today' in body
        assert 'm-show' in body

    def test_nba_card_present(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'nba-card' in body

    def test_nba_label_next_best_action(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'Next best action' in body

    def test_dash_quick_stats_container_present(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        assert 'dash-quick-stats' in body

    def test_m_hide_applied_to_low_priority_sections(self, auth):
        rv = auth.get("/dashboard")
        body = rv.data.decode()
        # Recent Changes, Recommended Opportunities, Top Agencies, Top Vendors
        # should be hidden on mobile via m-hide
        assert body.count('m-hide') >= 4

    def test_mobile_sections_absent_for_anon(self, anon):
        rv = anon.get("/")
        body = rv.data.decode()
        # Landing page should not have dashboard mobile sections
        assert 'nba-card' not in body
        assert 'mobile-today' not in body


# ---------------------------------------------------------------------------
# Contracts page mobile cards
# ---------------------------------------------------------------------------

class TestContractsMobileCards:
    def test_mobile_card_section_present(self, auth):
        rv = auth.get("/contracts")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert 'm-show' in body

    def test_desktop_table_hidden_on_mobile(self, auth):
        rv = auth.get("/contracts")
        body = rv.data.decode()
        # Desktop table should have m-hide class
        assert 'm-hide' in body

    def test_mobile_card_class_present(self, auth):
        rv = auth.get("/contracts")
        body = rv.data.decode()
        assert 'mobile-card' in body

    def test_mobile_card_has_title_link(self, auth):
        rv = auth.get("/contracts")
        body = rv.data.decode()
        assert 'mobile-card-title' in body

    def test_mobile_card_has_meta(self, auth):
        rv = auth.get("/contracts")
        body = rv.data.decode()
        assert 'mobile-card-meta' in body


# ---------------------------------------------------------------------------
# Pipeline page mobile cards
# ---------------------------------------------------------------------------

class TestPipelineMobileCards:
    def _add_opp(self, mobile_db):
        import sqlite3
        uid_con = sqlite3.connect(mobile_db)
        uid = uid_con.execute(
            "SELECT id FROM users WHERE email=?", ("mobile@example.com",)
        ).fetchone()[0]
        uid_con.close()
        add_opportunity(uid, "MOB-001")

    def test_pipeline_mobile_cards_section_present(self, mobile_db, auth):
        self._add_opp(mobile_db)
        rv = auth.get("/pipeline")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert 'pipeline-mobile-cards' in body

    def test_pipeline_mobile_cards_m_show(self, mobile_db, auth):
        self._add_opp(mobile_db)
        rv = auth.get("/pipeline")
        body = rv.data.decode()
        assert 'm-show' in body

    def test_pipeline_desktop_table_m_hide(self, mobile_db, auth):
        self._add_opp(mobile_db)
        rv = auth.get("/pipeline")
        body = rv.data.decode()
        assert 'm-hide' in body

    def test_pipeline_stage_tabs_scrollable_wrapper(self, mobile_db, auth):
        rv = auth.get("/pipeline")
        body = rv.data.decode()
        assert 'pipeline-stage-tabs' in body

    def test_pipeline_stage_tab_class(self, mobile_db, auth):
        rv = auth.get("/pipeline")
        body = rv.data.decode()
        assert 'pipeline-stage-tab' in body


# ---------------------------------------------------------------------------
# Contract detail mobile CTA bar
# ---------------------------------------------------------------------------

class TestContractDetailMobileCTA:
    def test_mobile_cta_present_for_auth(self, auth):
        rv = auth.get("/contract/MOB-001")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert 'contract-mobile-cta' in body

    def test_mobile_watch_button_present(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'id="mobile-watch-btn"' in body

    def test_mobile_cta_has_m_show_class(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'contract-mobile-cta m-show' in body

    def test_mobile_cta_has_pipeline_action(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        # Either "Add to Pipeline" or "In Pipeline" link should be present
        assert ('contract-cta-add' in body or 'contract-cta-pipeline' in body)

    def test_mobile_cta_absent_for_anon(self, anon):
        rv = anon.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'contract-mobile-cta' not in body

    def test_desktop_actions_hidden_on_mobile_via_class(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'detail-desktop-actions' in body

    def test_mobile_cta_add_pipeline_action_exists(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'pipeline/add/MOB-001' in body

    def test_watch_toggle_mobile_js_present(self, auth):
        rv = auth.get("/contract/MOB-001")
        body = rv.data.decode()
        assert 'watchToggleMobile' in body


# ---------------------------------------------------------------------------
# Primary routes smoke — no mobile regressions
# ---------------------------------------------------------------------------

class TestPrimaryRoutesNoRegression:
    def test_dashboard_200(self, auth):
        assert auth.get("/dashboard").status_code == 200

    def test_contracts_200(self, auth):
        assert auth.get("/contracts").status_code == 200

    def test_pipeline_200(self, auth):
        assert auth.get("/pipeline").status_code == 200

    def test_watchlist_200(self, auth):
        assert auth.get("/watchlist").status_code == 200

    def test_contract_detail_200(self, auth):
        assert auth.get("/contract/MOB-001").status_code == 200

    def test_company_profile_200(self, auth):
        assert auth.get("/company-profile").status_code == 200

    def test_settings_notifications_200(self, auth):
        assert auth.get("/settings/notifications").status_code == 200

    def test_ingest_200(self, auth):
        assert auth.get("/ingest").status_code == 200
