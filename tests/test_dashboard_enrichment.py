"""Integration tests for dashboard For My Business row enrichment.

Verifies that personalized_for_business() attaches work_label, location_label,
length_label, match_summary, and action_signal to each matched row, and that
generic "Agency contract" text is not the sole match summary shown.

Note: upsert_contract() always calls infer_category() which overwrites any
``category`` value passed in the dict. Tests that assert on category-derived
work_label must use description/NAICS values that infer_category() maps to a
known non-"Other" category.
"""

import sqlite3
import pytest
import db as db_module
from db import get_company_profile, save_company_profile, upsert_contract
import users as users_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def edb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "enrich_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("enrichtest@example.com", "password123")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute(
        "SELECT id FROM users WHERE email = 'enrichtest@example.com'"
    ).fetchone()[0]
    con.close()
    return uid


def _insert(edb, **kwargs):
    """Insert a contract via upsert_contract. category is set by infer_category()."""
    base = {
        "internal_id": "C1", "award_id": "A1", "vendor": "ACME Corp",
        "agency": "DEPARTMENT OF DEFENSE",
        "description": "Grounds maintenance and mowing services",
        "value": 2_500_000, "days_remaining": 90, "recompete_score": 80,
        "priority": "HIGH", "naics_code": "561730",
        "place_of_performance_state": "TX",
        "start_date": "2024-01-01", "end_date": "2025-01-01",
        "competition_type": "FULL AND OPEN COMPETITION",
    }
    base.update(kwargs)
    upsert_contract(base)


def _insert_direct(edb, **kwargs):
    """Bypass upsert_contract to set category directly (for testing fallback paths)."""
    import sqlite3 as _sqlite3
    con = _sqlite3.connect(edb)
    fields = {
        "internal_id": "C2", "award_id": "A2", "vendor": "Direct Inc",
        "agency": "DEPARTMENT OF DEFENSE", "description": None,
        "value": 1_000_000, "days_remaining": 60, "recompete_score": 70,
        "priority": "MEDIUM", "naics_code": None, "category": "Other",
        "place_of_performance_state": None,
        "start_date": None, "end_date": None,
        "competition_type": None,
    }
    fields.update(kwargs)
    con.execute("""
        INSERT OR REPLACE INTO contracts (
            internal_id, award_id, vendor, agency, description,
            value, days_remaining, recompete_score, priority, naics_code, category,
            place_of_performance_state, start_date, end_date, competition_type
        ) VALUES (
            :internal_id, :award_id, :vendor, :agency, :description,
            :value, :days_remaining, :recompete_score, :priority, :naics_code, :category,
            :place_of_performance_state, :start_date, :end_date, :competition_type
        )
    """, fields)
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Enriched field presence on every matched row
# ---------------------------------------------------------------------------

class TestEnrichedFieldsPresent:
    def _setup(self, edb):
        uid = _uid(edb)
        save_company_profile(uid, {
            "company_name": "Test Co",
            "agencies": ["DEPARTMENT OF DEFENSE"],
        })
        _insert(edb)
        return uid, get_company_profile(uid)

    def _result(self, edb):
        from analytics import personalized_for_business
        uid, profile = self._setup(edb)
        return personalized_for_business(uid, profile, limit=10)

    def test_work_label_attached(self, edb):
        rows = self._result(edb)
        assert len(rows) >= 1
        assert "work_label" in rows[0]

    def test_location_label_attached(self, edb):
        rows = self._result(edb)
        assert "location_label" in rows[0]

    def test_length_label_attached(self, edb):
        rows = self._result(edb)
        assert "length_label" in rows[0]

    def test_match_summary_attached(self, edb):
        rows = self._result(edb)
        assert "match_summary" in rows[0]

    def test_action_signal_attached(self, edb):
        rows = self._result(edb)
        assert "action_signal" in rows[0]


# ---------------------------------------------------------------------------
# Work label content
# ---------------------------------------------------------------------------

class TestWorkLabelContent:
    def test_inferred_category_used_as_work_label(self, edb):
        """infer_category("Grounds maintenance...", "561730") → "Grounds"; work_label returns that."""
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "GreenCo", "agencies": ["DEPARTMENT OF DEFENSE"]})
        # NAICS 561730 + this description → infer_category returns "Grounds"
        _insert(edb, description="Grounds maintenance and mowing services", naics_code="561730")
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["work_label"] == "Grounds"

    def test_description_used_when_category_is_other(self, edb):
        """When stored category is 'Other', work_label falls back to description text."""
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        profile = get_company_profile(uid)
        # Insert with category="Other" directly and a description
        _insert_direct(edb, category="Other", description="Pest control for federal buildings")
        result = personalized_for_business(uid, profile, limit=10)
        assert len(result) >= 1
        r2 = next((r for r in result if r["internal_id"] == "C2"), None)
        assert r2 is not None
        assert "Pest" in r2["work_label"]

    def test_fallback_when_category_other_and_no_description(self, edb):
        """When category is 'Other' and description is None, work_label is 'Contract services'."""
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        profile = get_company_profile(uid)
        _insert_direct(edb, category="Other", description=None)
        result = personalized_for_business(uid, profile, limit=10)
        r2 = next((r for r in result if r["internal_id"] == "C2"), None)
        assert r2 is not None
        assert r2["work_label"] == "Contract services"


# ---------------------------------------------------------------------------
# Location label
# ---------------------------------------------------------------------------

class TestLocationLabelContent:
    def test_state_shown_when_available(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, place_of_performance_state="VA")
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["location_label"] == "VA"

    def test_fallback_when_no_state(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, place_of_performance_state=None)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["location_label"] == "Location not listed"


# ---------------------------------------------------------------------------
# Contract length label
# ---------------------------------------------------------------------------

class TestLengthLabelContent:
    def test_length_computed_from_dates(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, start_date="2024-01-01", end_date="2025-01-01")
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        label = result[0]["length_label"]
        assert "year" in label or "month" in label

    def test_fallback_when_no_dates(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, start_date=None, end_date=None)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["length_label"] == "Length not listed"


# ---------------------------------------------------------------------------
# match_summary — no bare generic agency-only text
# ---------------------------------------------------------------------------

class TestMatchSummaryNotGeneric:
    def test_agency_only_string_not_used_as_sole_summary(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        summary = result[0]["match_summary"]
        assert summary != "DEPARTMENT OF DEFENSE contract"
        assert summary != "Department of Defense contract"

    def test_match_summary_is_non_empty(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["match_summary"]

    def test_match_reason_still_preserved_for_backward_compat(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert "match_reason" in result[0]


# ---------------------------------------------------------------------------
# Action signal
# ---------------------------------------------------------------------------

class TestActionSignalContent:
    def test_urgent_expiry_for_imminent_contract(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, days_remaining=15, recompete_score=60)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["action_signal"] == "Review: urgent expiry"

    def test_click_for_high_score(self, edb):
        from analytics import personalized_for_business
        uid = _uid(edb)
        save_company_profile(uid, {"company_name": "Test Co", "agencies": ["DEPARTMENT OF DEFENSE"]})
        _insert(edb, days_remaining=120, recompete_score=80)
        result = personalized_for_business(uid, get_company_profile(uid), limit=10)
        assert result[0]["action_signal"] == "Click: high fit"


# ---------------------------------------------------------------------------
# Dashboard template renders enriched table columns
# ---------------------------------------------------------------------------

class TestDashboardTemplateEnrichment:
    @pytest.fixture()
    def authed_client(self, edb):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        flask_app.app.config["WTF_CSRF_ENABLED"] = False
        flask_app.app.config["RATELIMIT_ENABLED"] = False
        flask_app.app.secret_key = "test-secret"
        with flask_app.app.test_client() as c:
            c.post("/login", data={
                "email": "enrichtest@example.com",
                "password": "password123",
            })
            with c.session_transaction() as sess:
                sess["onboarding_skipped"] = "1"
            yield c

    def test_dashboard_renders_successfully(self, authed_client, edb):
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200

    def test_dashboard_shows_for_business_table_when_matches_exist(self, authed_client, edb):
        uid = _uid(edb)
        save_company_profile(uid, {
            "company_name": "Grounds Co",
            "agencies": ["DEPARTMENT OF DEFENSE"],
        })
        _insert(edb, description="Grounds maintenance and mowing services", naics_code="561730")
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200
        assert b"For My Business" in rv.data

    def test_dashboard_shows_work_column_header(self, authed_client, edb):
        uid = _uid(edb)
        save_company_profile(uid, {
            "company_name": "Grounds Co",
            "agencies": ["DEPARTMENT OF DEFENSE"],
        })
        _insert(edb)
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200
        # The enriched table includes a "Work" column header
        assert b">Work<" in rv.data or b"Work" in rv.data

    def test_dashboard_shows_location_column_header(self, authed_client, edb):
        uid = _uid(edb)
        save_company_profile(uid, {
            "company_name": "Grounds Co",
            "agencies": ["DEPARTMENT OF DEFENSE"],
        })
        _insert(edb)
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200
        assert b"Location" in rv.data

    def test_dashboard_renders_without_for_business_when_no_profile(self, authed_client, edb):
        """Dashboard loads fine even with no company profile (no for_business section)."""
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200
        # Without a profile, no "For My Business" section
        assert b"for-business-table" not in rv.data
