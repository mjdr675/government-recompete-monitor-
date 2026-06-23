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
