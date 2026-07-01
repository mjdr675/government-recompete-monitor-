"""Tests for Phase 2: Opportunities For Your Business.

Covers:
- business_match_score() all weight branches and edge cases
- business_match_reasons() all reason types
- business_mismatch_reasons() all mismatch types
- profile_filter_for_sql() translation
- For My Business filter on /contracts
- Dashboard Opportunities For Your Business section
- Contract detail business match section
- No-profile CTA on dashboard
- Anonymous user behavior
- Missing-data edge cases (no NAICS, no value, no agencies)
- Existing filters unaffected
"""

import json
import pytest
import db as db_module
import users as users_module
from business_match import (
    business_match_score,
    business_match_reasons,
    business_mismatch_reasons,
    profile_filter_for_sql,
    _naics_from_contract,
    _agency_matches,
    _comp_type_matches_set_aside,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_contract(**kwargs):
    base = {
        "internal_id": "TEST-001",
        "agency": "Department of Defense",
        "value": 2_000_000.0,
        "competition_type": "FULL AND OPEN COMPETITION",
        "recompete_score": 80,
        "days_remaining": 60,
        "raw_json": None,
    }
    base.update(kwargs)
    return base


def _make_profile(**kwargs):
    base = {
        "naics_codes": [],
        "agencies": [],
        "min_contract_value": None,
        "max_contract_value": None,
        "set_asides": [],
        "states": [],
        "geo_coverage": "nationwide",
    }
    base.update(kwargs)
    return base


def _contract_with_naics(naics: str, **kwargs):
    raw = json.dumps({"sam_naics": naics})
    return _make_contract(raw_json=raw, **kwargs)


@pytest.fixture()
def biz_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("biz@example.com", "password123")
    yield db_path


@pytest.fixture()
def authed_client(biz_db):
    import app as flask_app
    flask_app.app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False, SECRET_KEY="test"
    )
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "biz@example.com", "password": "password123"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


@pytest.fixture()
def anon_client(biz_db):
    import app as flask_app
    flask_app.app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False, SECRET_KEY="test"
    )
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# _naics_from_contract
# ---------------------------------------------------------------------------

class TestNaicsFromContract:
    def test_returns_naics_from_raw_json(self):
        c = _contract_with_naics("561720")
        assert _naics_from_contract(c) == "561720"

    def test_returns_none_when_no_raw_json(self):
        c = _make_contract(raw_json=None)
        assert _naics_from_contract(c) is None

    def test_returns_none_when_naics_not_in_json(self):
        c = _make_contract(raw_json=json.dumps({"other_field": "value"}))
        assert _naics_from_contract(c) is None

    def test_handles_invalid_json_gracefully(self):
        c = _make_contract(raw_json="NOT JSON{{{")
        assert _naics_from_contract(c) is None

    def test_returns_naics_code_key_as_fallback(self):
        c = _make_contract(raw_json=json.dumps({"naics_code": "541511"}))
        assert _naics_from_contract(c) == "541511"

    def test_prefers_naics_column_over_raw_json(self):
        c = _make_contract(naics_code="561720", raw_json=json.dumps({"sam_naics": "999999"}))
        assert _naics_from_contract(c) == "561720"

    def test_returns_naics_column_when_raw_json_absent(self):
        c = _make_contract(naics_code="541511", raw_json=None)
        assert _naics_from_contract(c) == "541511"

    def test_falls_back_to_raw_json_when_column_empty(self):
        c = _make_contract(naics_code="", raw_json=json.dumps({"sam_naics": "561720"}))
        assert _naics_from_contract(c) == "561720"

    def test_whitespace_naics_column_treated_as_empty(self):
        c = _make_contract(naics_code="   ", raw_json=json.dumps({"sam_naics": "561720"}))
        assert _naics_from_contract(c) == "561720"


# ---------------------------------------------------------------------------
# _naics_matches (prefix hierarchy)
# ---------------------------------------------------------------------------

class TestNaicsMatches:
    def test_2digit_prefix_matches_6digit_contract(self):
        from business_match import _naics_matches
        assert _naics_matches("561720", ["56"])

    def test_4digit_prefix_matches_6digit_contract(self):
        from business_match import _naics_matches
        assert _naics_matches("561720", ["5617"])

    def test_exact_6digit_match(self):
        from business_match import _naics_matches
        assert _naics_matches("561720", ["561720"])

    def test_unrelated_prefix_does_not_match(self):
        from business_match import _naics_matches
        assert not _naics_matches("561720", ["54", "33"])


# ---------------------------------------------------------------------------
# _comp_type_matches_set_aside
# ---------------------------------------------------------------------------

class TestCompTypeMatchesSetAside:
    def test_small_business_match(self):
        assert _comp_type_matches_set_aside("SMALL BUSINESS SET ASIDE", "small_business")

    def test_full_and_open_match(self):
        assert _comp_type_matches_set_aside("FULL AND OPEN COMPETITION", "full_and_open")

    def test_8a_match(self):
        assert _comp_type_matches_set_aside("8A PROGRAM", "8a")

    def test_hubzone_match(self):
        assert _comp_type_matches_set_aside("HUBZONE SET ASIDE", "hubzone")

    def test_sdvosb_match(self):
        assert _comp_type_matches_set_aside("SERVICE-DISABLED VETERAN OWNED", "sdvosb")

    def test_wosb_match(self):
        assert _comp_type_matches_set_aside("WOMEN-OWNED SMALL BUSINESS", "wosb")

    def test_no_match(self):
        assert not _comp_type_matches_set_aside("FULL AND OPEN", "small_business")

    def test_none_competition_type(self):
        assert not _comp_type_matches_set_aside(None, "small_business")


# ---------------------------------------------------------------------------
# business_match_score
# ---------------------------------------------------------------------------

class TestBusinessMatchScore:
    def test_returns_zero_for_none_profile(self):
        assert business_match_score(_make_contract(), None) == 0

    def test_returns_zero_for_empty_profile(self):
        assert business_match_score(_make_contract(), _make_profile()) == 0

    def test_agency_match_full_score(self):
        profile = _make_profile(agencies=["Department of Defense"])
        contract = _make_contract(agency="Department of Defense")
        score = business_match_score(contract, profile)
        assert score == 100

    def test_agency_no_match(self):
        profile = _make_profile(agencies=["Department of Education"])
        contract = _make_contract(agency="Department of Defense")
        score = business_match_score(contract, profile)
        assert score == 0

    def test_agency_partial_match(self):
        profile = _make_profile(agencies=["Defense"])
        contract = _make_contract(agency="Department of Defense")
        score = business_match_score(contract, profile)
        assert score == 100

    def test_value_in_range_scores_full(self):
        profile = _make_profile(min_contract_value=1_000_000, max_contract_value=5_000_000)
        contract = _make_contract(value=2_000_000)
        score = business_match_score(contract, profile)
        assert score == 100

    def test_value_below_min_scores_zero(self):
        profile = _make_profile(min_contract_value=1_000_000)
        contract = _make_contract(value=500_000)
        score = business_match_score(contract, profile)
        assert score == 0

    def test_value_above_max_scores_zero(self):
        profile = _make_profile(max_contract_value=1_000_000)
        contract = _make_contract(value=2_000_000)
        score = business_match_score(contract, profile)
        assert score == 0

    def test_value_exactly_at_min_boundary(self):
        profile = _make_profile(min_contract_value=1_000_000)
        contract = _make_contract(value=1_000_000)
        score = business_match_score(contract, profile)
        assert score == 100

    def test_value_exactly_at_max_boundary(self):
        profile = _make_profile(max_contract_value=1_000_000)
        contract = _make_contract(value=1_000_000)
        score = business_match_score(contract, profile)
        assert score == 100

    def test_naics_match_full_score(self):
        profile = _make_profile(naics_codes=["561720"])
        contract = _contract_with_naics("561720")
        score = business_match_score(contract, profile)
        assert score == 100

    def test_naics_no_match(self):
        profile = _make_profile(naics_codes=["541511"])
        contract = _contract_with_naics("561720")
        score = business_match_score(contract, profile)
        assert score == 0

    def test_naics_missing_from_contract_skips_dimension(self):
        profile = _make_profile(naics_codes=["561720"], agencies=["Department of Defense"])
        contract = _make_contract(agency="Department of Defense", raw_json=None)
        # NAICS dimension skipped — only agency dimension active
        score = business_match_score(contract, profile)
        assert score == 100

    def test_set_aside_match(self):
        profile = _make_profile(set_asides=["small_business"])
        contract = _make_contract(competition_type="SMALL BUSINESS SET ASIDE")
        score = business_match_score(contract, profile)
        assert score == 100

    def test_set_aside_no_competition_type_skips_dimension(self):
        profile = _make_profile(set_asides=["small_business"], agencies=["Defense"])
        contract = _make_contract(competition_type=None, agency="Department of Defense")
        # set-aside dimension skipped
        score = business_match_score(contract, profile)
        assert score == 100

    def test_partial_match_multiple_dimensions(self):
        profile = _make_profile(
            agencies=["Department of Defense"],
            min_contract_value=1_000_000,
            max_contract_value=5_000_000,
        )
        contract = _make_contract(agency="Department of Defense", value=500_000)
        # agency matches (25 pts), value misses (0/20), possible=45 → round(25/45*100)=56
        score = business_match_score(contract, profile)
        assert score == 56

    def test_contract_value_none_skips_value_dimension(self):
        profile = _make_profile(min_contract_value=1_000_000, agencies=["Defense"])
        contract = _make_contract(value=None, agency="Department of Defense")
        # value dimension skipped (no value on contract)
        score = business_match_score(contract, profile)
        assert score == 100

    def test_score_is_0_to_100(self):
        profile = _make_profile(agencies=["X"], naics_codes=["999999"])
        contract = _contract_with_naics("561720", agency="Other Agency")
        score = business_match_score(contract, profile)
        assert 0 <= score <= 100

    def test_only_min_value_set(self):
        profile = _make_profile(min_contract_value=500_000)
        contract = _make_contract(value=1_000_000)
        score = business_match_score(contract, profile)
        assert score == 100

    def test_only_max_value_set(self):
        profile = _make_profile(max_contract_value=5_000_000)
        contract = _make_contract(value=1_000_000)
        score = business_match_score(contract, profile)
        assert score == 100


# ---------------------------------------------------------------------------
# business_match_reasons
# ---------------------------------------------------------------------------

class TestBusinessMatchReasons:
    def test_empty_for_none_profile(self):
        assert business_match_reasons(_make_contract(), None) == []

    def test_agency_reason(self):
        profile = _make_profile(agencies=["Department of Defense"])
        contract = _make_contract(agency="Department of Defense")
        reasons = business_match_reasons(contract, profile)
        assert any("Agency" in r for r in reasons)

    def test_value_reason(self):
        profile = _make_profile(min_contract_value=1_000_000, max_contract_value=5_000_000)
        contract = _make_contract(value=2_000_000)
        reasons = business_match_reasons(contract, profile)
        assert any("value" in r.lower() for r in reasons)

    def test_naics_reason(self):
        profile = _make_profile(naics_codes=["561720"])
        contract = _contract_with_naics("561720")
        reasons = business_match_reasons(contract, profile)
        assert any("561720" in r for r in reasons)

    def test_set_aside_reason(self):
        profile = _make_profile(set_asides=["small_business"])
        contract = _make_contract(competition_type="SMALL BUSINESS SET ASIDE")
        reasons = business_match_reasons(contract, profile)
        assert any("set-aside" in r.lower() for r in reasons)

    def test_no_reasons_when_no_match(self):
        profile = _make_profile(agencies=["Education"])
        contract = _make_contract(agency="Department of Defense")
        reasons = business_match_reasons(contract, profile)
        assert reasons == []

    def test_multiple_reasons(self):
        profile = _make_profile(
            agencies=["Department of Defense"],
            min_contract_value=1_000_000,
        )
        contract = _make_contract(agency="Department of Defense", value=2_000_000)
        reasons = business_match_reasons(contract, profile)
        assert len(reasons) >= 2


# ---------------------------------------------------------------------------
# business_mismatch_reasons
# ---------------------------------------------------------------------------

class TestBusinessMismatchReasons:
    def test_empty_for_none_profile(self):
        assert business_mismatch_reasons(_make_contract(), None) == []

    def test_agency_mismatch_reason(self):
        profile = _make_profile(agencies=["Department of Education"])
        contract = _make_contract(agency="Department of Defense")
        reasons = business_mismatch_reasons(contract, profile)
        assert any("Agency" in r for r in reasons)

    def test_value_below_min_mismatch(self):
        profile = _make_profile(min_contract_value=5_000_000)
        contract = _make_contract(value=500_000)
        reasons = business_mismatch_reasons(contract, profile)
        assert any("below" in r.lower() for r in reasons)

    def test_value_above_max_mismatch(self):
        profile = _make_profile(max_contract_value=1_000_000)
        contract = _make_contract(value=5_000_000)
        reasons = business_mismatch_reasons(contract, profile)
        assert any("exceed" in r.lower() for r in reasons)

    def test_naics_mismatch_reason(self):
        profile = _make_profile(naics_codes=["541511"])
        contract = _contract_with_naics("561720")
        reasons = business_mismatch_reasons(contract, profile)
        assert any("NAICS" in r for r in reasons)

    def test_no_mismatches_when_all_match(self):
        profile = _make_profile(agencies=["Department of Defense"])
        contract = _make_contract(agency="Department of Defense")
        reasons = business_mismatch_reasons(contract, profile)
        assert reasons == []


# ---------------------------------------------------------------------------
# profile_filter_for_sql
# ---------------------------------------------------------------------------

class TestProfileFilterForSql:
    def test_returns_empty_for_none(self):
        assert profile_filter_for_sql(None) == {}

    def test_agencies_passed_through(self):
        profile = _make_profile(agencies=["DoD", "VA"])
        pf = profile_filter_for_sql(profile)
        assert pf["agencies"] == ["DoD", "VA"]

    def test_min_value_passed_through(self):
        profile = _make_profile(min_contract_value=1_000_000)
        pf = profile_filter_for_sql(profile)
        assert pf["min_value"] == 1_000_000

    def test_max_value_passed_through(self):
        profile = _make_profile(max_contract_value=5_000_000)
        pf = profile_filter_for_sql(profile)
        assert pf["max_value"] == 5_000_000

    def test_set_aside_keywords_expanded(self):
        profile = _make_profile(set_asides=["small_business"])
        pf = profile_filter_for_sql(profile)
        assert "SMALL BUSINESS" in pf["set_aside_keywords"]

    def test_empty_agencies_when_profile_has_none(self):
        profile = _make_profile(agencies=[])
        pf = profile_filter_for_sql(profile)
        assert pf["agencies"] == []


# ---------------------------------------------------------------------------
# /contracts For My Business filter (HTTP integration)
# ---------------------------------------------------------------------------

class TestForMyBusinessFilter:
    def test_contracts_page_loads_without_filter(self, authed_client):
        rv = authed_client.get("/contracts")
        assert rv.status_code == 200

    def test_for_my_business_param_accepted_without_profile(self, authed_client):
        rv = authed_client.get("/contracts?for_my_business=1")
        assert rv.status_code == 200

    def test_for_my_business_shows_toggle_button(self, authed_client):
        rv = authed_client.get("/contracts")
        body = rv.get_data(as_text=True)
        assert "For My Business" in body

    def test_for_my_business_active_state_shown(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Defense"]})
        rv = authed_client.get("/contracts?for_my_business=1")
        body = rv.get_data(as_text=True)
        assert "Show all contracts" in body

    def test_for_my_business_no_profile_shows_cta(self, authed_client):
        rv = authed_client.get("/contracts?for_my_business=1")
        body = rv.get_data(as_text=True)
        assert "Company Profile" in body

    def test_anonymous_contracts_loads_without_toggle(self, anon_client):
        rv = anon_client.get("/contracts")
        assert rv.status_code == 302  # redirect to login

    def test_match_score_column_shown_when_filter_active(self, authed_client, biz_db):
        from db import save_company_profile, upsert_contract
        import sqlite3
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Defense Agency"]})
        upsert_contract({
            "internal_id": "C-MATCH-01",
            "vendor": "TestVendor",
            "agency": "Defense Agency",
            "value": 2_000_000,
            "days_remaining": 90,
            "recompete_score": 80,
            "priority": "HIGH",
            "competition_type": "FULL AND OPEN",
        })
        rv = authed_client.get("/contracts?for_my_business=1")
        body = rv.get_data(as_text=True)
        assert "Match" in body

    def test_existing_filters_still_work(self, authed_client):
        rv = authed_client.get("/contracts?priority=CRITICAL&status=open")
        assert rv.status_code == 200
        body = rv.get_data(as_text=True)
        assert "Contracts" in body


# ---------------------------------------------------------------------------
# Dashboard Opportunities For Your Business
# ---------------------------------------------------------------------------

class TestDashboardBizOpportunities:
    def test_dashboard_loads_without_profile(self, authed_client):
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200

    def test_dashboard_shows_cta_when_no_profile(self, authed_client):
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "Create Company Profile" in body or "Company Profile" in body

    def test_dashboard_shows_opportunities_section_when_profile_matches(self, authed_client, biz_db):
        from db import save_company_profile, upsert_contract
        import sqlite3
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Test Agency X"]})
        upsert_contract({
            "internal_id": "DASH-OPP-01",
            "vendor": "TestVendor",
            "agency": "Test Agency X",
            "value": 2_000_000,
            "days_remaining": 90,
            "recompete_score": 80,
            "priority": "HIGH",
            "competition_type": "FULL AND OPEN",
        })
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "Recommended for your company" in body

    def test_dashboard_no_opportunities_section_with_no_match(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        # Profile with agencies that won't match any contracts in fresh DB
        save_company_profile(uid, {"agencies": ["Nonexistent Agency XYZ"]})
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        # No matching contracts → no opportunities section (CTA may show instead)
        assert "Opportunities For Your Business" not in body or "Create Company Profile" in body


# ---------------------------------------------------------------------------
# Contract detail business match section
# ---------------------------------------------------------------------------

class TestContractDetailBizMatch:
    def _insert_contract(self, biz_db):
        from db import upsert_contract
        upsert_contract({
            "internal_id": "DETAIL-01",
            "vendor": "GovCo",
            "agency": "Department of Defense",
            "value": 2_000_000,
            "days_remaining": 120,
            "recompete_score": 75,
            "priority": "HIGH",
            "competition_type": "FULL AND OPEN COMPETITION",
        })
        return "DETAIL-01"

    def test_detail_no_match_section_when_no_profile(self, authed_client, biz_db):
        iid = self._insert_contract(biz_db)
        rv = authed_client.get(f"/contract/{iid}")
        body = rv.get_data(as_text=True)
        assert "Why this matches your business" not in body

    def test_detail_shows_match_section_when_profile_exists(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        iid = self._insert_contract(biz_db)
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Department of Defense"]})
        rv = authed_client.get(f"/contract/{iid}")
        body = rv.get_data(as_text=True)
        assert "Why this matches your business" in body

    def test_detail_shows_match_score(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        iid = self._insert_contract(biz_db)
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Department of Defense"]})
        rv = authed_client.get(f"/contract/{iid}")
        body = rv.get_data(as_text=True)
        assert "% match" in body

    def test_detail_shows_agency_match_reason(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        iid = self._insert_contract(biz_db)
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"agencies": ["Department of Defense"]})
        rv = authed_client.get(f"/contract/{iid}")
        body = rv.get_data(as_text=True)
        assert "Agency is in your preferred list" in body

    def test_detail_shows_mismatch_for_out_of_range_value(self, authed_client, biz_db):
        from db import save_company_profile
        import sqlite3
        iid = self._insert_contract(biz_db)
        con = sqlite3.connect(biz_db)
        uid = con.execute("SELECT id FROM users WHERE email='biz@example.com'").fetchone()[0]
        con.close()
        save_company_profile(uid, {"min_contract_value": 50_000_000})
        rv = authed_client.get(f"/contract/{iid}")
        body = rv.get_data(as_text=True)
        assert "below your minimum" in body

    def test_detail_no_match_section_for_anonymous(self, anon_client, biz_db):
        self._insert_contract(biz_db)
        rv = anon_client.get("/contract/DETAIL-01")
        assert rv.status_code in (200, 302)
        if rv.status_code == 200:
            body = rv.get_data(as_text=True)
            assert "Why this matches your business" not in body


# ---------------------------------------------------------------------------
# Edge cases with missing data
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_score_is_zero_with_no_profile_fields(self):
        profile = _make_profile()
        assert business_match_score(_make_contract(), profile) == 0

    def test_contract_missing_agency_doesnt_match_profile_agencies(self):
        profile = _make_profile(agencies=["Defense"])
        contract = _make_contract(agency=None)
        assert business_match_score(contract, profile) == 0

    def test_profile_empty_agencies_list_skips_agency_dimension(self):
        profile = _make_profile(agencies=[], min_contract_value=100_000)
        contract = _make_contract(value=500_000)
        # only value dimension active, matches
        assert business_match_score(contract, profile) == 100

    def test_contract_zero_value_doesnt_meet_min(self):
        profile = _make_profile(min_contract_value=500_000)
        contract = _make_contract(value=0.0)
        assert business_match_score(contract, profile) == 0

    def test_profile_both_values_none_skips_value_dimension(self):
        profile = _make_profile(agencies=["Defense"], min_contract_value=None, max_contract_value=None)
        contract = _make_contract(agency="Department of Defense")
        # value dimension skipped — only agency active
        assert business_match_score(contract, profile) == 100

    def test_reasons_empty_when_no_applicable_dimensions(self):
        profile = _make_profile()
        assert business_match_reasons(_make_contract(), profile) == []

    def test_mismatch_reasons_empty_when_no_applicable_dimensions(self):
        profile = _make_profile()
        assert business_mismatch_reasons(_make_contract(), profile) == []

    def test_naics_prefix_matching_works(self):
        profile = _make_profile(naics_codes=["561720"])
        contract = _contract_with_naics("561720")
        assert business_match_score(contract, profile) == 100

    def test_naics_different_6_digit_prefix_no_match(self):
        profile = _make_profile(naics_codes=["561720"])
        contract = _contract_with_naics("541511")
        assert business_match_score(contract, profile) == 0
