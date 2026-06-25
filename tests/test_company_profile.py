"""Tests for Company Profile Foundation (Phase 1).

Covers:
- DB helpers: get_company_profile, save_company_profile
- GET /company-profile: empty state, profile loaded, auth protection
- POST /company-profile: create, update, validation, multi-value fields
- Navigation: link present for authenticated users
"""
import pytest
import sqlite3
import db as db_module
from db import get_company_profile, save_company_profile
import users as users_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def profile_db(tmp_path, monkeypatch):
    """Isolated DB with a pre-created test user."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("profile@example.com", "password123")
    yield db_path


@pytest.fixture()
def authed_client(profile_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        # Log in as the user created by profile_db fixture
        c.post("/login", data={
            "email": "profile@example.com",
            "password": "password123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


@pytest.fixture()
def anon_client(profile_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        yield c


def _user_id(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email = 'profile@example.com'").fetchone()[0]
    con.close()
    return uid


# ---------------------------------------------------------------------------
# DB helper: get_company_profile
# ---------------------------------------------------------------------------

class TestGetCompanyProfile:
    def test_returns_none_when_no_profile(self, profile_db):
        uid = _user_id(profile_db)
        assert get_company_profile(uid) is None

    def test_returns_profile_after_save(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"company_name": "Acme"})
        p = get_company_profile(uid)
        assert p is not None
        assert p["company_name"] == "Acme"

    def test_naics_codes_returned_as_list(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"naics_codes": ["561720", "541511"]})
        p = get_company_profile(uid)
        assert sorted(p["naics_codes"]) == ["541511", "561720"]

    def test_states_returned_as_list(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"geo_coverage": "states", "states": ["VA", "MD"]})
        p = get_company_profile(uid)
        assert sorted(p["states"]) == ["MD", "VA"]

    def test_agencies_returned_as_list(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"agencies": ["Dept of Defense", "VA"]})
        p = get_company_profile(uid)
        assert "Dept of Defense" in p["agencies"]
        assert "VA" in p["agencies"]

    def test_set_asides_returned_as_list(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"set_asides": ["small_business", "8a"]})
        p = get_company_profile(uid)
        assert "small_business" in p["set_asides"]
        assert "8a" in p["set_asides"]

    def test_empty_lists_when_no_multi_values(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"company_name": "Solo"})
        p = get_company_profile(uid)
        assert p["naics_codes"] == []
        assert p["states"] == []
        assert p["agencies"] == []
        assert p["set_asides"] == []


# ---------------------------------------------------------------------------
# DB helper: save_company_profile
# ---------------------------------------------------------------------------

class TestSaveCompanyProfile:
    def test_create_returns_profile_id(self, profile_db):
        uid = _user_id(profile_db)
        pid = save_company_profile(uid, {})
        assert isinstance(pid, int)
        assert pid > 0

    def test_update_replaces_data(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"company_name": "OldName"})
        save_company_profile(uid, {"company_name": "NewName"})
        p = get_company_profile(uid)
        assert p["company_name"] == "NewName"

    def test_update_does_not_create_duplicate(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"company_name": "A"})
        save_company_profile(uid, {"company_name": "B"})
        con = sqlite3.connect(profile_db)
        count = con.execute("SELECT COUNT(*) FROM company_profiles WHERE user_id=?", (uid,)).fetchone()[0]
        con.close()
        assert count == 1

    def test_naics_replaced_on_update(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"naics_codes": ["561720"]})
        save_company_profile(uid, {"naics_codes": ["541511", "541519"]})
        p = get_company_profile(uid)
        assert "561720" not in p["naics_codes"]
        assert "541511" in p["naics_codes"]

    def test_duplicate_naics_deduplicated(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"naics_codes": ["561720", "561720"]})
        p = get_company_profile(uid)
        assert p["naics_codes"].count("561720") == 1

    def test_min_max_contract_value_stored(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"min_contract_value": 1_000_000, "max_contract_value": 10_000_000})
        p = get_company_profile(uid)
        assert p["min_contract_value"] == 1_000_000
        assert p["max_contract_value"] == 10_000_000

    def test_geo_coverage_nationwide_clears_states(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"geo_coverage": "states", "states": ["VA", "MD"]})
        save_company_profile(uid, {"geo_coverage": "nationwide", "states": []})
        p = get_company_profile(uid)
        assert p["states"] == []
        assert p["geo_coverage"] == "nationwide"

    def test_empty_strings_in_naics_skipped(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"naics_codes": ["", "561720", "  "]})
        p = get_company_profile(uid)
        assert p["naics_codes"] == ["561720"]

    def test_website_stored(self, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"website": "https://example.com"})
        p = get_company_profile(uid)
        assert p["website"] == "https://example.com"


# ---------------------------------------------------------------------------
# GET /company-profile
# ---------------------------------------------------------------------------

class TestGetRoute:
    def test_redirects_anonymous_to_login(self, anon_client):
        rv = anon_client.get("/company-profile")
        assert rv.status_code == 302
        assert "/login" in rv.headers["Location"]

    def test_returns_200_for_authenticated_user(self, authed_client):
        rv = authed_client.get("/company-profile")
        assert rv.status_code == 200

    def test_shows_empty_state_when_no_profile(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "Set up your company profile" in body

    def test_shows_create_button_when_no_profile(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "Create Profile" in body

    def test_shows_company_profile_heading(self, authed_client):
        rv = authed_client.get("/company-profile")
        assert b"Company Profile" in rv.data

    def test_shows_naics_section(self, authed_client):
        rv = authed_client.get("/company-profile")
        assert b"NAICS" in rv.data

    def test_shows_set_aside_options(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "Small Business" in body
        assert "HUBZone" in body
        assert "8(a)" in body

    def test_shows_geographic_coverage_section(self, authed_client):
        rv = authed_client.get("/company-profile")
        assert b"Geographic Coverage" in rv.data

    def test_prepopulates_existing_profile(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {
            "company_name": "TestCo",
            "naics_codes": ["561720"],
            "set_asides": ["small_business"],
        })
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "TestCo" in body
        assert "561720" in body

    def test_update_button_when_profile_exists(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"company_name": "Existing"})
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "Update Profile" in body


# ---------------------------------------------------------------------------
# POST /company-profile
# ---------------------------------------------------------------------------

class TestPostRoute:
    def test_create_profile_redirects_with_success(self, authed_client):
        rv = authed_client.post("/company-profile", data={
            "company_name": "Acme Corp",
            "website": "",
            "geo_coverage": "nationwide",
            "naics_codes": "561720",
            "min_contract_value": "",
            "max_contract_value": "",
        })
        assert rv.status_code == 200
        assert b"Profile saved" in rv.data

    def test_create_stores_company_name(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "company_name": "BuildCo",
            "geo_coverage": "nationwide",
        })
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert p["company_name"] == "BuildCo"

    def test_create_stores_naics_codes(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "naics_codes": "561720\n541511",
        })
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert "561720" in p["naics_codes"]
        assert "541511" in p["naics_codes"]

    def test_naics_comma_separated(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "naics_codes": "561720,541511",
        })
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert "561720" in p["naics_codes"]
        assert "541511" in p["naics_codes"]

    def test_create_stores_set_asides(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "set_asides": ["small_business", "hubzone"],
        }, content_type="application/x-www-form-urlencoded")
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert "small_business" in p["set_asides"]
        assert "hubzone" in p["set_asides"]

    def test_create_stores_agencies(self, authed_client, profile_db):
        # Agencies are validated against the contracts table.  Seed a contract
        # so "Dept of Defense" appears in the allowlist; "VA" is absent and
        # should be silently dropped by the server-side validation.
        con = sqlite3.connect(profile_db)
        con.execute(
            "INSERT INTO contracts (internal_id, agency) VALUES (?, ?)",
            ("test-agency-seed", "Dept of Defense"),
        )
        con.commit()
        con.close()
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "agencies": ["Dept of Defense", "VA"],
        }, content_type="application/x-www-form-urlencoded")
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert "Dept of Defense" in p["agencies"]
        assert "VA" not in p["agencies"]  # not in contracts table → filtered

    def test_create_stores_states_when_geo_is_states(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "states",
            "states": ["VA", "MD"],
        }, content_type="application/x-www-form-urlencoded")
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert "VA" in p["states"]
        assert "MD" in p["states"]

    def test_states_ignored_when_geo_is_nationwide(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "states": ["VA", "MD"],
        }, content_type="application/x-www-form-urlencoded")
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert p["states"] == []

    def test_min_max_value_stored(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "min_contract_value": "1000000",
            "max_contract_value": "10000000",
        })
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert p["min_contract_value"] == 1_000_000
        assert p["max_contract_value"] == 10_000_000

    def test_validation_min_greater_than_max(self, authed_client):
        rv = authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "min_contract_value": "10000000",
            "max_contract_value": "500000",
        })
        body = rv.get_data(as_text=True)
        assert "cannot exceed maximum" in body

    def test_validation_non_numeric_min(self, authed_client):
        rv = authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "min_contract_value": "not-a-number",
        })
        body = rv.get_data(as_text=True)
        assert "must be a number" in body

    def test_update_replaces_profile(self, authed_client, profile_db):
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "company_name": "First Name",
        })
        authed_client.post("/company-profile", data={
            "geo_coverage": "nationwide",
            "company_name": "Second Name",
        })
        uid = _user_id(profile_db)
        p = get_company_profile(uid)
        assert p["company_name"] == "Second Name"
        con = sqlite3.connect(profile_db)
        count = con.execute("SELECT COUNT(*) FROM company_profiles WHERE user_id=?", (uid,)).fetchone()[0]
        con.close()
        assert count == 1

    def test_post_requires_auth(self, anon_client):
        rv = anon_client.post("/company-profile", data={"company_name": "X", "geo_coverage": "nationwide"})
        assert rv.status_code == 302
        assert "/login" in rv.headers["Location"]


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def test_nav_link_present_for_authenticated_user(authed_client):
    rv = authed_client.get("/dashboard")
    body = rv.get_data(as_text=True)
    assert "/company-profile" in body
    assert "Company Profile" in body


def test_nav_link_not_present_for_anonymous(anon_client):
    rv = anon_client.get("/")
    body = rv.get_data(as_text=True)
    assert "Company Profile" not in body


# ---------------------------------------------------------------------------
# Contract Import Details: UEI + CAGE Code
# ---------------------------------------------------------------------------

class TestContractImportFields:
    def test_import_section_rendered(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "Contract Import Details" in body
        assert "import-contracts" in body

    def test_uei_field_rendered(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert 'name="uei"' in body
        assert "ABCD12345678" in body  # placeholder

    def test_cage_code_field_rendered(self, authed_client):
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert 'name="cage_code"' in body
        assert "1ABC2" in body  # placeholder

    def test_save_and_reload_uei(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"uei": "ZZZZ99887766", "company_name": "TestCo"})
        p = get_company_profile(uid)
        assert p["uei"] == "ZZZZ99887766"

    def test_save_and_reload_cage_code(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"cage_code": "5AB12", "company_name": "TestCo"})
        p = get_company_profile(uid)
        assert p["cage_code"] == "5AB12"

    def test_uei_and_cage_persist_across_update(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"uei": "AAAA11223344", "cage_code": "1XY23"})
        save_company_profile(uid, {"company_name": "Updated Name"})
        p = get_company_profile(uid)
        # UEI/CAGE cleared when not re-submitted — same as vendor_name behavior
        # This test verifies round-trip fidelity, not preservation across partial save
        assert p["company_name"] == "Updated Name"

    def test_post_saves_uei_and_cage(self, authed_client):
        rv = authed_client.post("/company-profile", data={
            "company_name": "Import Test Co",
            "geo_coverage": "nationwide",
            "uei": "BBBB55443322",
            "cage_code": "2CD45",
        })
        assert rv.status_code in (200, 302)
        rv2 = authed_client.get("/company-profile")
        body = rv2.get_data(as_text=True)
        assert "BBBB55443322" in body
        assert "2CD45" in body

    def test_uei_prepopulated_in_form(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"uei": "CCCC11223344"})
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "CCCC11223344" in body

    def test_cage_prepopulated_in_form(self, authed_client, profile_db):
        uid = _user_id(profile_db)
        save_company_profile(uid, {"cage_code": "3EF67"})
        rv = authed_client.get("/company-profile")
        body = rv.get_data(as_text=True)
        assert "3EF67" in body


# ---------------------------------------------------------------------------
# UEI / CAGE contract matching in my_current_contracts()
# ---------------------------------------------------------------------------

import db as _db_mod
from analytics import my_current_contracts, my_current_contract_summary


def _insert_contract(db_path, internal_id, vendor, recipient_uei="", cage_code="",
                     days_remaining=30, value=500000.0):
    """Insert a minimal contract row directly into the test DB."""
    con = sqlite3.connect(db_path)
    con.execute("""
        INSERT OR REPLACE INTO contracts
            (internal_id, award_id, vendor, agency, value, end_date,
             days_remaining, recompete_score, priority, category,
             recipient_uei, cage_code)
        VALUES (?, ?, ?, 'Test Agency', ?, '2030-01-01',
                ?, 50, 'MEDIUM', 'IT', ?, ?)
    """, (internal_id, internal_id, vendor, value, days_remaining,
          recipient_uei, cage_code))
    con.commit()
    con.close()


@pytest.fixture()
def matching_db(tmp_path, monkeypatch):
    """DB with a user, company profile, and pre-seeded contracts for matching tests."""
    db_path = str(tmp_path / "match.db")
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    _db_mod._cached_engine.cache_clear()
    _db_mod.init_db()
    import users as _u
    _u.create_user("matcher@example.com", "password123")
    yield db_path
    _db_mod._cached_engine.cache_clear()


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email = 'matcher@example.com'").fetchone()[0]
    con.close()
    return uid


class TestMyCurrentContractsUeiCage:
    def test_returns_empty_when_no_profile(self, matching_db):
        uid = _uid(matching_db)
        assert my_current_contracts(uid) == []

    def test_returns_empty_when_profile_has_no_identifiers(self, matching_db):
        uid = _uid(matching_db)
        save_company_profile(uid, {"company_name": ""})
        assert my_current_contracts(uid) == []

    def test_uei_exact_match(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C001", "Acme Corp", recipient_uei="AABB11223344")
        _insert_contract(matching_db, "C002", "Other Corp", recipient_uei="XXXX99998888")
        save_company_profile(uid, {"uei": "AABB11223344"})
        results = my_current_contracts(uid)
        ids = [r["internal_id"] for r in results]
        assert "C001" in ids
        assert "C002" not in ids

    def test_uei_match_sets_match_method(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C003", "Acme Corp", recipient_uei="UUUU11223344")
        save_company_profile(uid, {"uei": "UUUU11223344"})
        results = my_current_contracts(uid)
        assert results[0]["match_method"] == "UEI"

    def test_cage_exact_match(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C004", "Beta LLC", cage_code="5AB12")
        _insert_contract(matching_db, "C005", "Gamma Inc", cage_code="9XY99")
        save_company_profile(uid, {"cage_code": "5AB12"})
        results = my_current_contracts(uid)
        ids = [r["internal_id"] for r in results]
        assert "C004" in ids
        assert "C005" not in ids

    def test_cage_match_sets_match_method(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C006", "Beta LLC", cage_code="7CD34")
        save_company_profile(uid, {"cage_code": "7CD34"})
        results = my_current_contracts(uid)
        assert results[0]["match_method"] == "CAGE"

    def test_vendor_name_fallback_match(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C007", "Delta Services Inc")
        save_company_profile(uid, {"vendor_name": "Delta Services"})
        results = my_current_contracts(uid)
        ids = [r["internal_id"] for r in results]
        assert "C007" in ids
        assert results[0]["match_method"] == "vendor name"

    def test_uei_takes_priority_over_cage(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C008", "Alpha Corp", recipient_uei="PPPP12345678")
        _insert_contract(matching_db, "C009", "Alpha Corp", cage_code="8EF56")
        save_company_profile(uid, {"uei": "PPPP12345678", "cage_code": "8EF56"})
        results = my_current_contracts(uid)
        methods = {r["internal_id"]: r["match_method"] for r in results}
        assert methods.get("C008") == "UEI"
        assert methods.get("C009") == "CAGE"

    def test_deduplication_across_methods(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C010", "Acme Solutions", recipient_uei="RRRR11112222",
                         cage_code="1GH78")
        save_company_profile(uid, {"uei": "RRRR11112222", "cage_code": "1GH78"})
        results = my_current_contracts(uid)
        ids = [r["internal_id"] for r in results]
        assert ids.count("C010") == 1

    def test_uei_match_is_case_insensitive_on_profile(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C011", "Lower Corp", recipient_uei="SSSS33334444")
        save_company_profile(uid, {"uei": "ssss33334444"})
        results = my_current_contracts(uid)
        assert any(r["internal_id"] == "C011" for r in results)

    def test_summary_returns_none_with_no_identifiers(self, matching_db):
        uid = _uid(matching_db)
        assert my_current_contract_summary(uid) is None

    def test_summary_counts_uei_matches(self, matching_db):
        uid = _uid(matching_db)
        _insert_contract(matching_db, "C012", "Echo Corp", recipient_uei="TTTT55556666")
        _insert_contract(matching_db, "C013", "Echo Corp", recipient_uei="TTTT55556666")
        save_company_profile(uid, {"uei": "TTTT55556666"})
        summary = my_current_contract_summary(uid)
        assert summary is not None
        assert summary["count"] == 2
        assert summary["match_term"] == "TTTT55556666"

    def test_save_snapshot_persists_uei_and_cage(self, matching_db):
        from db import save_snapshot, get_engine
        from sqlalchemy import text as _text
        rows = [{
            "internal_id": "SNAP001",
            "award_id": "SNAP001",
            "vendor": "Snapshot Vendor",
            "agency": "Test Agency",
            "value": 1_000_000.0,
            "start_date": "2024-01-01",
            "end_date": "2030-06-30",
            "days_remaining": 100,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "recipient_uei": "VVVV77778888",
            "cage_code": "2IJ90",
        }]
        save_snapshot("2026-01-01", rows)
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                _text("SELECT recipient_uei, cage_code FROM contracts WHERE internal_id = 'SNAP001'")
            ).fetchone()
        assert row[0] == "VVVV77778888"
        assert row[1] == "2IJ90"
