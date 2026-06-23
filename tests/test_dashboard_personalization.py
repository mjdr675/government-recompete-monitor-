"""Tests for Dashboard Personalization (dashboard-personalization lane).

Covers:
- Keywords: save/get in company profile
- Keyword scoring in business_match.py
- Profile completeness includes keywords dimension
- Profile completion hints include keywords hint
- suggested_matches analytics function
- my_contracts_summary analytics function
- Dashboard route passes my_contracts and suggested_matches to template
- Company profile POST handler saves keywords
- Dashboard title reflects company name
"""
import sqlite3
import pytest
import db as db_module
from db import get_company_profile, save_company_profile
import users as users_module
from business_match import (
    business_match_score,
    business_match_reasons,
    profile_completeness,
    profile_completion_hints,
    _keyword_matches,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pdb(tmp_path, monkeypatch):
    """Isolated DB with a pre-created test user."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("personalization@example.com", "password123")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute(
        "SELECT id FROM users WHERE email = 'personalization@example.com'"
    ).fetchone()[0]
    con.close()
    return uid


@pytest.fixture()
def authed_client(pdb):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        c.post("/login", data={
            "email": "personalization@example.com",
            "password": "password123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


# ---------------------------------------------------------------------------
# Keywords — DB layer
# ---------------------------------------------------------------------------

class TestKeywordsDB:
    def test_keywords_saved_and_retrieved(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["lawn care", "janitorial"]})
        p = get_company_profile(uid)
        assert "lawn care" in p["keywords"]
        assert "janitorial" in p["keywords"]

    def test_keywords_default_empty_list(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"company_name": "TestCo"})
        p = get_company_profile(uid)
        assert p["keywords"] == []

    def test_keywords_replaced_on_update(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["cleaning"]})
        save_company_profile(uid, {"keywords": ["IT support"]})
        p = get_company_profile(uid)
        assert "cleaning" not in p["keywords"]
        assert "it support" in p["keywords"]

    def test_keywords_deduplicated(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["janitorial", "janitorial"]})
        p = get_company_profile(uid)
        assert p["keywords"].count("janitorial") == 1

    def test_keywords_stored_lowercase(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["Lawn Care", "CLEANING"]})
        p = get_company_profile(uid)
        assert "lawn care" in p["keywords"]
        assert "cleaning" in p["keywords"]

    def test_keywords_from_string(self, pdb):
        """save_company_profile accepts a comma-separated string for keywords."""
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": "lawn care, janitorial"})
        p = get_company_profile(uid)
        assert "lawn care" in p["keywords"]
        assert "janitorial" in p["keywords"]

    def test_empty_keyword_strings_skipped(self, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["", "cleaning", "  "]})
        p = get_company_profile(uid)
        assert p["keywords"] == ["cleaning"]


# ---------------------------------------------------------------------------
# Keyword matching — business_match helpers
# ---------------------------------------------------------------------------

class TestKeywordMatches:
    def test_matches_vendor(self):
        contract = {"vendor": "Capitol Lawn Care LLC", "description": None, "award_id": None}
        assert _keyword_matches(contract, ["lawn care"]) == ["lawn care"]

    def test_matches_description(self):
        contract = {"vendor": "ABC Inc", "description": "janitorial services contract", "award_id": None}
        assert _keyword_matches(contract, ["janitorial"]) == ["janitorial"]

    def test_matches_award_id(self):
        contract = {"vendor": None, "description": None, "award_id": "DOD-CLEANING-001"}
        assert _keyword_matches(contract, ["cleaning"]) == ["cleaning"]

    def test_case_insensitive(self):
        contract = {"vendor": "Lawn CARE Inc", "description": None, "award_id": None}
        assert _keyword_matches(contract, ["lawn care"]) == ["lawn care"]

    def test_no_match(self):
        contract = {"vendor": "Defense Contractor LLC", "description": "weapons system", "award_id": None}
        assert _keyword_matches(contract, ["janitorial", "cleaning"]) == []

    def test_partial_match(self):
        contract = {"vendor": "Cleaning Solutions LLC", "description": None, "award_id": None}
        matched = _keyword_matches(contract, ["cleaning", "janitorial"])
        assert "cleaning" in matched
        assert "janitorial" not in matched

    def test_empty_keywords(self):
        contract = {"vendor": "Any Vendor", "description": "any desc", "award_id": None}
        assert _keyword_matches(contract, []) == []

    def test_none_fields(self):
        contract = {"vendor": None, "description": None, "award_id": None}
        assert _keyword_matches(contract, ["cleaning"]) == []


# ---------------------------------------------------------------------------
# Business match score — keyword dimension
# ---------------------------------------------------------------------------

class TestBusinessMatchScoreKeywords:
    def test_keyword_match_increases_score(self):
        profile = {"keywords": ["janitorial"]}
        contract_match = {"vendor": "Acme Janitorial Services", "description": None, "award_id": None}
        contract_no_match = {"vendor": "Defense Systems LLC", "description": None, "award_id": None}
        score_match = business_match_score(contract_match, profile)
        score_no_match = business_match_score(contract_no_match, profile)
        assert score_match > score_no_match

    def test_keyword_match_full_score(self):
        profile = {"keywords": ["lawn care"]}
        contract = {"vendor": "Capitol Lawn Care LLC", "description": None, "award_id": None}
        score = business_match_score(contract, profile)
        assert score == 100

    def test_partial_keyword_match(self):
        profile = {"keywords": ["lawn care", "janitorial", "cleaning"]}
        contract = {"vendor": "Lawn Care Plus", "description": None, "award_id": None}
        # Only "lawn care" matches (1/3 keywords)
        score = business_match_score(contract, profile)
        assert 0 < score <= 100

    def test_no_keyword_dimension_when_profile_has_no_keywords(self):
        profile_no_kw = {"naics_codes": ["561720"]}
        profile_with_kw = {"naics_codes": ["561720"], "keywords": ["cleaning"]}
        contract = {"vendor": "Cleaning Inc", "description": None, "award_id": None,
                    "raw_json": '{"sam_naics": "561720"}'}
        # Both score on NAICS; only with keywords can the keyword dimension run
        score_no_kw = business_match_score(contract, profile_no_kw)
        # With keywords dimension added, score might vary
        score_with_kw = business_match_score(contract, profile_with_kw)
        assert score_no_kw == 100  # Only NAICS dimension, matches -> 100
        assert score_with_kw == 100  # Both NAICS + keyword match -> 100

    def test_score_zero_with_no_profile(self):
        contract = {"vendor": "Janitorial LLC"}
        assert business_match_score(contract, None) == 0

    def test_keyword_reasons_included(self):
        profile = {"keywords": ["janitorial"]}
        contract = {"vendor": "Acme Janitorial Services", "description": None, "award_id": None}
        reasons = business_match_reasons(contract, profile)
        assert any("janitorial" in r.lower() for r in reasons)

    def test_no_keyword_reasons_when_no_match(self):
        profile = {"keywords": ["janitorial"]}
        contract = {"vendor": "Defense Systems LLC", "description": None, "award_id": None}
        reasons = business_match_reasons(contract, profile)
        assert not any("keyword" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Profile completeness — includes keywords
# ---------------------------------------------------------------------------

class TestProfileCompletenessKeywords:
    def test_profile_without_keywords_not_100(self):
        profile = {
            "company_name": "TestCo",
            "naics_codes": ["561720"],
            "agencies": ["Dept of Defense"],
            "min_contract_value": 100000,
            "max_contract_value": 5000000,
            "set_asides": ["small_business"],
            "geo_coverage": "nationwide",
            "states": [],
            "keywords": [],
        }
        assert profile_completeness(profile) < 100

    def test_profile_with_keywords_counts_toward_completion(self):
        profile_no_kw = {
            "company_name": "TestCo",
            "naics_codes": ["561720"],
            "agencies": ["Dept of Defense"],
            "min_contract_value": 100000,
            "max_contract_value": 5000000,
            "set_asides": ["small_business"],
            "geo_coverage": "nationwide",
            "states": [],
            "keywords": [],
        }
        profile_with_kw = dict(profile_no_kw)
        profile_with_kw["keywords"] = ["janitorial"]
        assert profile_completeness(profile_with_kw) > profile_completeness(profile_no_kw)

    def test_keywords_hint_when_missing(self):
        profile = {"keywords": []}
        hints = profile_completion_hints(profile)
        assert any("keyword" in h.lower() for h in hints)

    def test_no_keywords_hint_when_set(self):
        profile = {"keywords": ["janitorial"]}
        hints = profile_completion_hints(profile)
        # Should not mention keywords since they're set
        assert not any(
            "keyword" in h.lower() and "add keyword" in h.lower()
            for h in hints
        )


# ---------------------------------------------------------------------------
# suggested_matches analytics function
# ---------------------------------------------------------------------------

class TestSuggestedMatches:
    def test_returns_empty_when_no_user(self, pdb):
        from analytics import suggested_matches
        assert suggested_matches(None) == []

    def test_returns_empty_when_user_tracks_nothing(self, pdb):
        from analytics import suggested_matches
        uid = _uid(pdb)
        assert suggested_matches(uid) == []

    def test_returns_suggestions_when_user_has_watchlist(self, pdb):
        from analytics import suggested_matches
        uid = _uid(pdb)
        con = sqlite3.connect(pdb)
        # Seed two contracts
        con.execute("INSERT INTO contracts (internal_id, agency, value, days_remaining, recompete_score) VALUES ('c1', 'Dept of Defense', 100000, 30, 80)")
        con.execute("INSERT INTO contracts (internal_id, agency, value, days_remaining, recompete_score) VALUES ('c2', 'Dept of Defense', 90000, 60, 70)")
        # User watches c1
        con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'c1', datetime('now'))", (uid,))
        con.commit()
        con.close()

        result = suggested_matches(uid)
        # c2 is in same agency and not tracked
        assert any(r["internal_id"] == "c2" for r in result)
        # c1 is tracked so not in suggestions
        assert not any(r["internal_id"] == "c1" for r in result)

    def test_suggestions_have_reason(self, pdb):
        from analytics import suggested_matches
        uid = _uid(pdb)
        con = sqlite3.connect(pdb)
        con.execute("INSERT INTO contracts (internal_id, agency, value, days_remaining, recompete_score) VALUES ('c1', 'VA', 100000, 30, 80)")
        con.execute("INSERT INTO contracts (internal_id, agency, value, days_remaining, recompete_score) VALUES ('c2', 'VA', 90000, 60, 70)")
        con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'c1', datetime('now'))", (uid,))
        con.commit()
        con.close()

        result = suggested_matches(uid)
        for r in result:
            assert "suggestion_reason" in r
            assert "VA" in r["suggestion_reason"]


# ---------------------------------------------------------------------------
# my_contracts_summary analytics function
# ---------------------------------------------------------------------------

class TestMyContractsSummary:
    def test_returns_empty_when_no_user(self, pdb):
        from analytics import my_contracts_summary
        r = my_contracts_summary(None)
        assert r["total"] == 0

    def test_returns_watchlist_contracts(self, pdb):
        from analytics import my_contracts_summary
        uid = _uid(pdb)
        con = sqlite3.connect(pdb)
        con.execute("INSERT INTO contracts (internal_id, agency, value, days_remaining) VALUES ('w1', 'GSA', 50000, 45)")
        con.execute("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (?, 'w1', datetime('now'))", (uid,))
        con.commit()
        con.close()

        r = my_contracts_summary(uid)
        assert r["total"] == 1
        assert any(c["internal_id"] == "w1" for c in r["watchlist"])

    def test_empty_when_user_has_nothing(self, pdb):
        from analytics import my_contracts_summary
        uid = _uid(pdb)
        r = my_contracts_summary(uid)
        assert r["total"] == 0
        assert r["watchlist"] == []
        assert r["pipeline"] == []


# ---------------------------------------------------------------------------
# Dashboard route
# ---------------------------------------------------------------------------

class TestDashboardPersonalization:
    def test_dashboard_passes_my_contracts(self, authed_client):
        rv = authed_client.get("/dashboard")
        assert rv.status_code == 200

    def test_dashboard_shows_my_contracts_tab(self, authed_client):
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "My Contracts" in body

    def test_dashboard_shows_discover_tab(self, authed_client):
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "Discover" in body

    def test_dashboard_hides_onboarding_cta_when_profile_exists(
        self, authed_client, pdb
    ):
        uid = _uid(pdb)
        save_company_profile(uid, {
            "naics_codes": ["561720"],
            "company_name": "TestCo",
        })
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        # With a profile set, the "Set Up Your Profile" onboarding CTA should not appear
        assert "Set Up Your Profile" not in body

    def test_dashboard_title_includes_company_name(self, authed_client, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"company_name": "Acme Janitorial"})
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "Acme Janitorial" in body


# ---------------------------------------------------------------------------
# Company profile POST — keywords
# ---------------------------------------------------------------------------

class TestCompanyProfileKeywords:
    def test_post_saves_keywords(self, authed_client, pdb):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "keywords": "janitorial, lawn care",
        })
        uid = _uid(pdb)
        p = get_company_profile(uid)
        assert "janitorial" in p["keywords"]
        assert "lawn care" in p["keywords"]

    def test_post_saves_newline_separated_keywords(self, authed_client, pdb):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "keywords": "janitorial\nfacilities management",
        })
        uid = _uid(pdb)
        p = get_company_profile(uid)
        assert "janitorial" in p["keywords"]
        assert "facilities management" in p["keywords"]

    def test_keywords_shown_on_profile_page(self, authed_client, pdb):
        uid = _uid(pdb)
        save_company_profile(uid, {"keywords": ["IT support"]})
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "it support" in body.lower()


# ---------------------------------------------------------------------------
# Personalized For Business matching
# ---------------------------------------------------------------------------

class TestPersonalizedForBusiness:
    def test_returns_empty_if_no_profile(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        # Insert a contract
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        # No profile → empty result
        result = personalized_for_business(uid, None)
        assert result == []

    def test_returns_empty_if_profile_lacks_criteria(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        # Profile with no NAICS/states/agencies
        save_company_profile(uid, {"company_name": "Empty Profile"})
        profile = get_company_profile(uid)
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        result = personalized_for_business(uid, profile)
        assert result == []

    def test_matches_by_state(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        save_company_profile(uid, {"company_name": "TX Co", "states": ["TX"]})
        profile = get_company_profile(uid)
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        result = personalized_for_business(uid, profile, limit=10)
        assert len(result) == 1
        assert result[0]["internal_id"] == "C1"
        assert "Work in TX" in result[0]["match_reason"]

    def test_matches_by_category(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        save_company_profile(uid, {
            "company_name": "IT Co",
            "naics_codes": ["541512"]  # IT category
        })
        profile = get_company_profile(uid)
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        result = personalized_for_business(uid, profile, limit=10)
        assert len(result) == 1
        assert "IT category" in result[0]["match_reason"]

    def test_matches_by_agency(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        save_company_profile(uid, {
            "company_name": "GSA Co",
            "agencies": ["GSA"]
        })
        profile = get_company_profile(uid)
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        result = personalized_for_business(uid, profile, limit=10)
        assert len(result) == 1
        assert "GSA contract" in result[0]["match_reason"]

    def test_excludes_tracked_contracts(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        import sqlite3
        uid = _uid(pdb)
        save_company_profile(uid, {"company_name": "TX Co", "states": ["TX"]})
        profile = get_company_profile(uid)
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        # Add to watchlist (tracked)
        con = sqlite3.connect(pdb)
        from datetime import datetime
        con.execute(
            "INSERT INTO user_watchlist(user_id, internal_id, added_at) VALUES(?, ?, ?)",
            (uid, "C1", datetime.now().isoformat())
        )
        con.commit()
        con.close()
        result = personalized_for_business(uid, profile, limit=10)
        # Should be excluded
        assert len(result) == 0

    def test_respects_value_range(self, pdb):
        from analytics import personalized_for_business
        from db import upsert_contract
        uid = _uid(pdb)
        save_company_profile(uid, {
            "company_name": "Value Co",
            "states": ["TX"],
            "min_contract_value": 200000,
            "max_contract_value": 300000
        })
        profile = get_company_profile(uid)
        # Below range
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        # In range
        upsert_contract({
            "internal_id": "C2", "award_id": "A2", "vendor": "Test2",
            "agency": "GSA", "description": "", "value": 250000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        result = personalized_for_business(uid, profile, limit=10)
        ids = [r["internal_id"] for r in result]
        assert "C1" not in ids  # Below range
        assert "C2" in ids  # In range

    def test_dashboard_shows_for_business_section(self, authed_client, pdb):
        from db import upsert_contract
        uid = _uid(pdb)
        save_company_profile(uid, {"company_name": "TX Co", "states": ["TX"]})
        upsert_contract({
            "internal_id": "C1", "award_id": "A1", "vendor": "Test",
            "agency": "GSA", "description": "", "value": 100000,
            "days_remaining": 90, "recompete_score": 50, "priority": "MEDIUM",
            "category": "IT", "naics_code": "541512", "place_of_performance_state": "TX"
        })
        rv = authed_client.get("/dashboard")
        body = rv.get_data(as_text=True)
        assert "For My Business" in body
        assert "A1" in body
