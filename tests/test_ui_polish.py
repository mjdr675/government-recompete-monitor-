"""UI polish + product education tests — ui-polish-education lane.

Covers:
- Score explainer renders on contract detail
- Score bar renders
- Views page shows descriptions and "how scoring works" section
- Views page shows full label (not bare acronym)
- Contracts page has subtitle
- Saved searches page shows human-readable filters, not raw JSON
- Watchlist page has subtitle
- Mobile layout markers (m-show / m-hide) remain intact
- Key pages still render (200 OK)
"""

import pytest
import db as db_module
from views import SAVED_VIEWS, format_filter_summary


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "ui-polish@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ── SAVED_VIEWS data model ─────────────────────────────────────────────────

class TestSavedViewsModel:
    def test_all_views_have_label(self):
        for key, v in SAVED_VIEWS.items():
            assert "label" in v, f"View '{key}' is missing a label"
            assert v["label"].strip(), f"View '{key}' has an empty label"

    def test_all_views_have_description(self):
        for key, v in SAVED_VIEWS.items():
            assert "description" in v, f"View '{key}' is missing a description"
            assert len(v["description"]) > 20, f"View '{key}' description is too short"

    def test_dod_view_label_spells_out_acronym(self):
        v = SAVED_VIEWS.get("dod-critical", {})
        label = v.get("label", "")
        assert "Defense" in label or "DoD" in label, (
            "dod-critical label should spell out 'Defense' or include 'DoD' in context"
        )
        assert label != "DoD", "Label must not be the bare acronym 'DoD'"

    def test_expiring_soon_view_exists(self):
        assert "expiring-soon" in SAVED_VIEWS

    def test_high_value_view_exists(self):
        assert "high-value-contracts" in SAVED_VIEWS

    def test_views_filters_are_nonempty(self):
        for key, v in SAVED_VIEWS.items():
            assert v.get("filters"), f"View '{key}' has empty filters"


# ── /views page ────────────────────────────────────────────────────────────

class TestViewsPage:
    def test_views_page_renders(self, client):
        rv = client.get("/views")
        assert rv.status_code == 200

    def test_views_page_has_title(self, client):
        rv = client.get("/views")
        assert b"Views" in rv.data

    def test_views_page_shows_dod_label_not_bare_acronym(self, client):
        rv = client.get("/views")
        assert b"Defense" in rv.data or b"DoD" in rv.data
        assert b">DoD<" not in rv.data

    def test_views_page_shows_descriptions(self, client):
        rv = client.get("/views")
        # At least one description text fragment should appear
        body = rv.data.lower()
        assert b"expiring" in body or b"window" in body or b"opportunity" in body

    def test_views_page_shows_how_scoring_works(self, client):
        rv = client.get("/views")
        assert b"Recompete Score" in rv.data

    def test_views_page_shows_priority_tiers(self, client):
        rv = client.get("/views")
        assert b"CRITICAL" in rv.data

    def test_views_page_no_raw_filter_keys(self, client):
        rv = client.get("/views")
        assert b"days: 90" not in rv.data
        assert b'"days"' not in rv.data

    def test_views_page_shows_human_readable_filter_summary(self, client):
        rv = client.get("/views")
        assert b"Expiring within" in rv.data

    def test_views_page_view_card_links_present(self, client):
        rv = client.get("/views")
        for key in SAVED_VIEWS:
            assert f"/views/{key}".encode() in rv.data


# ── /contracts page ────────────────────────────────────────────────────────

class TestContractsPage:
    def test_contracts_page_renders(self, client):
        rv = client.get("/contracts")
        assert rv.status_code == 200

    def test_contracts_page_has_subtitle(self, client):
        rv = client.get("/contracts")
        assert b"page-subtitle" in rv.data

    def test_contracts_page_has_score_column_with_info(self, client):
        rv = client.get("/contracts")
        assert b"Score" in rv.data
        assert b"Recompete Score" in rv.data

    def test_contracts_page_has_mobile_cards(self, client):
        rv = client.get("/contracts")
        assert b"m-show" in rv.data

    def test_contracts_page_has_desktop_table(self, client):
        rv = client.get("/contracts")
        assert b"m-hide" in rv.data

    def test_contracts_empty_state_has_clear_filters_link(self, client):
        rv = client.get("/contracts?agency=NONEXISTENT_AGENCY_XYZ_999")
        assert rv.status_code == 200
        assert b"contracts" in rv.data.lower()


# ── /contract/<id> detail page ─────────────────────────────────────────────

class TestContractDetailScoreExplainer:
    def _create_contract(self, test_db):
        from sqlalchemy import text
        engine = db_module._cached_engine(f"sqlite:///{test_db}")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO contracts
                  (internal_id, vendor, agency, value, end_date,
                   priority, recompete_score, competition_type)
                VALUES
                  ('POLISH-001', 'Acme Corp', 'DEFENSE', 2500000,
                   '2026-12-31', 'HIGH', 82, 'FULL AND OPEN')
            """))
        return "POLISH-001"

    def test_score_explainer_present(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert rv.status_code == 200
        assert b"score-explainer" in rv.data

    def test_score_explainer_explains_components(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert b"Competition type" in rv.data
        assert b"Contract value" in rv.data
        assert b"Time remaining" in rv.data

    def test_score_explainer_shows_priority_tiers(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert b"CRITICAL" in rv.data
        assert b"HIGH" in rv.data
        assert b"MEDIUM" in rv.data

    def test_score_kpi_card_present(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert b"Recompete Score" in rv.data
        assert b"score-kpi" in rv.data

    def test_score_bar_renders(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert b"score-bar" in rv.data

    def test_score_explainer_links_to_views_page(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/POLISH-001")
        assert b"/views" in rv.data


# ── /searches page ─────────────────────────────────────────────────────────

class TestSearchesPage:
    def _save_search(self, client, name, params):
        rv = client.post("/searches/save", json={"name": name, "params": params})
        assert rv.status_code == 200

    def test_searches_page_renders(self, client):
        rv = client.get("/searches")
        assert rv.status_code == 200

    def test_searches_page_has_subtitle(self, client):
        rv = client.get("/searches")
        assert b"page-subtitle" in rv.data

    def test_searches_no_raw_json_in_filter_column(self, client):
        self._save_search(client, "Test Agency", {"agency": "DEFENSE", "priority": "CRITICAL"})
        rv = client.get("/searches")
        assert b'{"agency"' not in rv.data

    def test_searches_shows_human_readable_agency(self, client):
        self._save_search(client, "DoD search", {"agency": "DEFENSE"})
        rv = client.get("/searches")
        assert b"Agency: DEFENSE" in rv.data

    def test_searches_shows_human_readable_priority(self, client):
        self._save_search(client, "Crit search", {"priority": "CRITICAL"})
        rv = client.get("/searches")
        assert b"Priority: Critical" in rv.data

    def test_searches_shows_human_readable_days(self, client):
        self._save_search(client, "Expiring", {"days": "90"})
        rv = client.get("/searches")
        assert b"Expiring within" in rv.data
        assert b"90 days" in rv.data

    def test_searches_shows_human_readable_min_value(self, client):
        self._save_search(client, "Big contracts", {"min_value": "1000000"})
        rv = client.get("/searches")
        assert b"Min value" in rv.data
        assert b"1,000,000" in rv.data

    def test_searches_empty_state_shows_how_to_save(self, client):
        rv = client.get("/searches")
        assert b"Save this search" in rv.data or b"Go to Contracts" in rv.data


# ── /watchlist page ────────────────────────────────────────────────────────

class TestWatchlistPage:
    def test_watchlist_page_renders(self, client):
        rv = client.get("/watchlist")
        assert rv.status_code == 200

    def test_watchlist_page_has_subtitle(self, client):
        rv = client.get("/watchlist")
        assert b"page-subtitle" in rv.data

    def test_watchlist_empty_state_explains_how_to_add(self, client):
        rv = client.get("/watchlist")
        assert b"star" in rv.data.lower() or b"&#9734;" in rv.data or b"Add" in rv.data


# ── mobile layout markers ──────────────────────────────────────────────────

class TestMobileLayoutMarkers:
    def test_contracts_has_m_hide_desktop_table(self, client):
        rv = client.get("/contracts")
        assert b"m-hide" in rv.data

    def test_contracts_has_m_show_mobile_cards(self, client):
        rv = client.get("/contracts")
        assert b"m-show" in rv.data

    def test_views_page_renders_on_small_viewport(self, client):
        rv = client.get("/views")
        assert rv.status_code == 200
        assert b"views-grid" in rv.data


# ── score explanation modal ────────────────────────────────────────────────

class TestScoreModal:
    """The score explainer is upgraded to an accessible modal triggered from
    the info icons on Contracts and Contract Detail."""

    def _create_contract(self, test_db):
        from sqlalchemy import text
        engine = db_module._cached_engine(f"sqlite:///{test_db}")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO contracts
                  (internal_id, vendor, agency, value, end_date,
                   priority, recompete_score, competition_type)
                VALUES
                  ('MODAL-001', 'Acme Corp', 'DEFENSE', 2500000,
                   '2026-12-31', 'HIGH', 82, 'FULL AND OPEN')
            """))
        return "MODAL-001"

    # --- Contracts page ---

    def test_contracts_renders_score_modal(self, client):
        rv = client.get("/contracts")
        assert b'id="scoreModal"' in rv.data

    def test_contracts_modal_is_dialog_role(self, client):
        rv = client.get("/contracts")
        assert b'role="dialog"' in rv.data
        assert b'aria-modal="true"' in rv.data

    def test_contracts_score_icon_is_button_not_bare_span(self, client):
        rv = client.get("/contracts")
        # The Score header info icon now opens the modal via a real button.
        assert b"openScoreModal()" in rv.data
        assert b"score-info-btn" in rv.data

    def test_contracts_modal_has_close_control(self, client):
        rv = client.get("/contracts")
        assert b"closeScoreModal()" in rv.data
        assert b'aria-label="Close"' in rv.data

    def test_contracts_modal_contains_scoring_components(self, client):
        rv = client.get("/contracts")
        assert b"Competition type" in rv.data
        assert b"Contract value" in rv.data
        assert b"Time remaining" in rv.data

    def test_contracts_modal_rendered_once(self, client):
        rv = client.get("/contracts")
        # A single modal instance — IDs must be unique.
        assert rv.data.count(b'id="scoreModal"') == 1

    # --- Contract detail page ---

    def test_detail_renders_score_modal(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/MODAL-001")
        assert b'id="scoreModal"' in rv.data

    def test_detail_score_icon_opens_modal(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/MODAL-001")
        assert b"openScoreModal()" in rv.data

    def test_detail_keeps_no_js_details_fallback(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/MODAL-001")
        # The <details> explainer remains as a no-JS accessible fallback.
        assert b"score-explainer" in rv.data
        assert b"Competition type" in rv.data

    def test_detail_modal_rendered_once(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/MODAL-001")
        assert rv.data.count(b'id="scoreModal"') == 1

    def test_modal_priority_tiers_present(self, client, test_db):
        self._create_contract(test_db)
        rv = client.get("/contract/MODAL-001")
        for tier in (b"CRITICAL", b"HIGH", b"MEDIUM", b"LOW"):
            assert tier in rv.data
