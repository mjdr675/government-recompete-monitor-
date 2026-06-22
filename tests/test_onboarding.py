"""Tests for onboarding flows.

Covers:
- Original watchlist-based onboarding banner (R-05)
- Phase 3 profile-based onboarding wizard:
  - profile_completeness() all branches
  - profile_completion_hints() all hint types
  - Dashboard first-login redirect to /onboarding
  - Dashboard no redirect for users with profiles
  - Dashboard no redirect after onboarding skip
  - Skip endpoint sets session flag and redirects to dashboard
  - Onboarding step 1/2/3 GET renders form
  - Onboarding step 1/2/3 POST stores to session and redirects
  - Step 3 POST saves profile and redirects to /onboarding/complete
  - /onboarding/complete renders with matching opportunities
  - Unauthenticated access redirects to login
  - Invalid step parameter defaults to step 1
  - Profile completeness indicator on company_profile page
  - Dashboard completion hints section
"""

import pytest
import db as db_module
import users as users_module
from users import set_trial
from business_match import profile_completeness, profile_completion_hints


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_full_profile(**kwargs):
    base = {
        "company_name": "Acme Gov",
        "website": "",
        "naics_codes": ["541511"],
        "agencies": ["Department of Defense"],
        "min_contract_value": 500_000.0,
        "max_contract_value": 10_000_000.0,
        "set_asides": ["small_business"],
        "states": [],
        "geo_coverage": "nationwide",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Fixtures (original banner tests)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(db):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


def _login(client, db):
    user = users_module.create_user("onboard@example.com", "password123")
    set_trial(user["id"], days=14)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        # Bypass the Phase 3 first-login redirect so banner tests still work.
        sess["onboarding_skipped"] = "1"
    return user


# ---------------------------------------------------------------------------
# Original: watchlist-based onboarding banner (R-05)
# ---------------------------------------------------------------------------

class TestOnboardingBanner:
    def test_banner_shown_to_new_user(self, db, client):
        _login(client, db)
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "get started" in body.lower() or "Welcome" in body

    def test_banner_hidden_after_dismiss(self, db, client):
        _login(client, db)
        client.post("/onboarding/dismiss")
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "here's how to get started" not in body.lower()

    def test_dismiss_redirects_to_dashboard(self, db, client):
        _login(client, db)
        resp = client.post("/onboarding/dismiss")
        assert resp.status_code in (301, 302)
        assert "/dashboard" in resp.headers["Location"]

    def test_dismiss_sets_session_flag(self, db, client):
        _login(client, db)
        client.post("/onboarding/dismiss")
        with client.session_transaction() as sess:
            assert sess.get("onboarding_dismissed") == "1"

    def test_banner_not_shown_when_dismissed(self, db, client):
        _login(client, db)
        with client.session_transaction() as sess:
            sess["onboarding_dismissed"] = "1"
        resp = client.get("/dashboard")
        body = resp.data.decode()
        assert "here's how to get started" not in body.lower()

    def test_dismiss_requires_post(self, db, client):
        _login(client, db)
        resp = client.get("/onboarding/dismiss")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Phase 3 fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ob_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    users_module.create_user("ob@example.com", "password123")
    yield db_path


@pytest.fixture()
def ob_client(ob_db):
    import app as flask_app
    flask_app.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SECRET_KEY="test",
    )
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "ob@example.com", "password": "password123"})
        yield c


@pytest.fixture()
def ob_client_with_profile(ob_db):
    import app as flask_app
    flask_app.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SECRET_KEY="test",
    )
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "ob@example.com", "password": "password123"})
        user = users_module.get_user_by_email("ob@example.com")
        db_module.save_company_profile(user["id"], _make_full_profile())
        yield c


# ---------------------------------------------------------------------------
# Unit: profile_completeness()
# ---------------------------------------------------------------------------

class TestProfileCompleteness:
    def test_none_returns_zero(self):
        assert profile_completeness(None) == 0

    def test_empty_dict_low_score(self):
        assert profile_completeness({}) == 0

    def test_full_profile_returns_100(self):
        assert profile_completeness(_make_full_profile()) == 100

    def test_partial_no_naics(self):
        score = profile_completeness(_make_full_profile(naics_codes=[]))
        assert 0 < score < 100

    def test_partial_no_agencies(self):
        score = profile_completeness(_make_full_profile(agencies=[]))
        assert 0 < score < 100

    def test_partial_no_values(self):
        score = profile_completeness(_make_full_profile(min_contract_value=None, max_contract_value=None))
        assert 0 < score < 100

    def test_partial_no_set_asides(self):
        score = profile_completeness(_make_full_profile(set_asides=[]))
        assert 0 < score < 100

    def test_geo_nationwide_counts_complete(self):
        p = _make_full_profile(geo_coverage="nationwide", states=[])
        assert profile_completeness(p) == 100

    def test_geo_states_with_states_complete(self):
        p = _make_full_profile(geo_coverage="states", states=["VA", "MD"])
        assert profile_completeness(p) == 100

    def test_geo_states_empty_not_complete(self):
        p = _make_full_profile(geo_coverage="states", states=[])
        assert profile_completeness(p) < 100

    def test_returns_integer(self):
        assert isinstance(profile_completeness(_make_full_profile()), int)

    def test_bounds(self):
        assert 0 <= profile_completeness(None) <= 100
        assert 0 <= profile_completeness({}) <= 100
        assert 0 <= profile_completeness(_make_full_profile()) <= 100


# ---------------------------------------------------------------------------
# Unit: profile_completion_hints()
# ---------------------------------------------------------------------------

class TestProfileCompletionHints:
    def test_none_returns_create_hint(self):
        hints = profile_completion_hints(None)
        assert len(hints) >= 1
        text = hints[0].lower()
        assert "create" in text or "company profile" in text

    def test_no_naics_yields_naics_hint(self):
        hints = profile_completion_hints(_make_full_profile(naics_codes=[]))
        assert any("NAICS" in h for h in hints)

    def test_no_agencies_yields_agencies_hint(self):
        hints = profile_completion_hints(_make_full_profile(agencies=[]))
        assert any("agenc" in h.lower() for h in hints)

    def test_no_values_yields_size_hint(self):
        hints = profile_completion_hints(_make_full_profile(min_contract_value=None, max_contract_value=None))
        assert any("size" in h.lower() or "range" in h.lower() for h in hints)

    def test_no_set_asides_yields_hint(self):
        hints = profile_completion_hints(_make_full_profile(set_asides=[]))
        assert any("set-aside" in h.lower() or "certif" in h.lower() for h in hints)

    def test_full_profile_no_hints(self):
        assert profile_completion_hints(_make_full_profile()) == []

    def test_hints_are_strings(self):
        for h in profile_completion_hints(_make_full_profile(naics_codes=[])):
            assert isinstance(h, str)

    def test_only_min_value_set_no_size_hint(self):
        p = _make_full_profile(min_contract_value=100_000, max_contract_value=None)
        hints = profile_completion_hints(p)
        assert not any("size" in h.lower() or "range" in h.lower() for h in hints)

    def test_only_max_value_set_no_size_hint(self):
        p = _make_full_profile(min_contract_value=None, max_contract_value=5_000_000)
        hints = profile_completion_hints(p)
        assert not any("size" in h.lower() or "range" in h.lower() for h in hints)


# ---------------------------------------------------------------------------
# Integration: first-login redirect
# ---------------------------------------------------------------------------

class TestFirstLoginRedirect:
    def test_dashboard_redirects_new_user_to_onboarding(self, ob_client):
        resp = ob_client.get("/dashboard")
        assert resp.status_code == 302
        assert "/onboarding" in resp.headers["Location"]

    def test_dashboard_no_redirect_with_profile(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_no_redirect_after_skip(self, ob_client):
        ob_client.get("/onboarding/skip")
        resp = ob_client.get("/dashboard")
        assert resp.status_code == 200

    def test_skip_redirects_to_dashboard(self, ob_client):
        resp = ob_client.get("/onboarding/skip")
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Integration: onboarding wizard steps
# ---------------------------------------------------------------------------

class TestOnboardingSteps:
    def test_step_1_get_renders_form(self, ob_client):
        resp = ob_client.get("/onboarding")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "About Your Business" in body
        assert 'name="company_name"' in body
        assert 'name="naics_codes"' in body

    def test_step_2_get_renders_form(self, ob_client):
        resp = ob_client.get("/onboarding?step=2")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Where do you perform work" in body
        assert 'name="geo_coverage"' in body

    def test_step_3_get_renders_form(self, ob_client):
        resp = ob_client.get("/onboarding?step=3")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Contract Preferences" in body
        assert 'name="min_contract_value"' in body

    def test_invalid_step_defaults_to_1(self, ob_client):
        resp = ob_client.get("/onboarding?step=99")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "About Your Business" in body

    def test_step_1_post_redirects_to_step_2(self, ob_client):
        resp = ob_client.post("/onboarding?step=1", data={
            "step": "1",
            "company_name": "Acme Corp",
            "naics_codes": "541511\n561720",
        })
        assert resp.status_code == 302
        assert "step=2" in resp.headers["Location"]

    def test_step_2_post_redirects_to_step_3(self, ob_client):
        resp = ob_client.post("/onboarding?step=2", data={
            "step": "2",
            "geo_coverage": "nationwide",
        })
        assert resp.status_code == 302
        assert "step=3" in resp.headers["Location"]

    def test_step_2_states_coverage_redirects_to_step_3(self, ob_client):
        resp = ob_client.post("/onboarding?step=2", data={
            "step": "2",
            "geo_coverage": "states",
            "states": ["VA", "MD"],
        })
        assert resp.status_code == 302
        assert "step=3" in resp.headers["Location"]

    def test_step_3_post_redirects_to_complete(self, ob_client):
        ob_client.post("/onboarding?step=1", data={"step": "1", "company_name": "Acme", "naics_codes": "541511"})
        ob_client.post("/onboarding?step=2", data={"step": "2", "geo_coverage": "nationwide"})
        resp = ob_client.post("/onboarding?step=3", data={
            "step": "3",
            "min_contract_value": "500000",
            "max_contract_value": "10000000",
        })
        assert resp.status_code == 302
        assert "/onboarding/complete" in resp.headers["Location"]

    def test_step_3_creates_profile(self, ob_db, ob_client):
        ob_client.post("/onboarding?step=1", data={"step": "1", "company_name": "Test Co", "naics_codes": "541511"})
        ob_client.post("/onboarding?step=2", data={"step": "2", "geo_coverage": "nationwide"})
        ob_client.post("/onboarding?step=3", data={"step": "3", "min_contract_value": "", "max_contract_value": ""})
        user = users_module.get_user_by_email("ob@example.com")
        profile = db_module.get_company_profile(user["id"])
        assert profile is not None
        assert profile["company_name"] == "Test Co"
        assert "541511" in profile["naics_codes"]

    def test_naics_carries_from_step_1_to_saved_profile(self, ob_db, ob_client):
        ob_client.post("/onboarding?step=1", data={"step": "1", "company_name": "Carry", "naics_codes": "561720,541511"})
        ob_client.post("/onboarding?step=2", data={"step": "2", "geo_coverage": "nationwide"})
        ob_client.post("/onboarding?step=3", data={"step": "3", "min_contract_value": "", "max_contract_value": ""})
        user = users_module.get_user_by_email("ob@example.com")
        profile = db_module.get_company_profile(user["id"])
        assert "561720" in profile["naics_codes"]
        assert "541511" in profile["naics_codes"]

    def test_invalid_naics_filtered_out(self, ob_db, ob_client):
        ob_client.post("/onboarding?step=1", data={
            "step": "1",
            "company_name": "Filter",
            "naics_codes": "541511\nnot-a-code\n9999999",
        })
        ob_client.post("/onboarding?step=2", data={"step": "2", "geo_coverage": "nationwide"})
        ob_client.post("/onboarding?step=3", data={"step": "3", "min_contract_value": "", "max_contract_value": ""})
        user = users_module.get_user_by_email("ob@example.com")
        profile = db_module.get_company_profile(user["id"])
        assert "541511" in profile["naics_codes"]
        assert "not-a-code" not in profile["naics_codes"]
        assert "9999999" not in profile["naics_codes"]

    def test_dashboard_no_redirect_after_completing_wizard(self, ob_client):
        ob_client.post("/onboarding?step=1", data={"step": "1", "company_name": "", "naics_codes": ""})
        ob_client.post("/onboarding?step=2", data={"step": "2", "geo_coverage": "nationwide"})
        ob_client.post("/onboarding?step=3", data={"step": "3", "min_contract_value": "", "max_contract_value": ""})
        resp = ob_client.get("/dashboard")
        assert resp.status_code == 200

    def test_progress_indicator_shows_current_step(self, ob_client):
        resp = ob_client.get("/onboarding?step=2")
        body = resp.data.decode()
        assert "Step 2 of 3" in body

    def test_skip_link_on_step_1(self, ob_client):
        resp = ob_client.get("/onboarding")
        body = resp.data.decode()
        assert "/onboarding/skip" in body

    def test_back_link_on_step_2(self, ob_client):
        resp = ob_client.get("/onboarding?step=2")
        body = resp.data.decode()
        assert "step=1" in body

    def test_back_link_on_step_3(self, ob_client):
        resp = ob_client.get("/onboarding?step=3")
        body = resp.data.decode()
        assert "step=2" in body


# ---------------------------------------------------------------------------
# Integration: /onboarding/complete
# ---------------------------------------------------------------------------

class TestOnboardingComplete:
    def test_complete_page_renders(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/onboarding/complete")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Your profile is ready" in body

    def test_complete_page_has_dashboard_link(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/onboarding/complete")
        assert "/dashboard" in resp.data.decode()

    def test_complete_page_has_opportunities_link(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/onboarding/complete")
        assert "for_my_business=1" in resp.data.decode()

    def test_complete_unauthenticated_redirects(self, ob_db):
        import app as flask_app
        flask_app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False, SECRET_KEY="test")
        with flask_app.app.test_client() as c:
            resp = c.get("/onboarding/complete")
            assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Integration: unauthenticated access
# ---------------------------------------------------------------------------

class TestOnboardingUnauthenticated:
    def test_onboarding_requires_login(self, ob_db):
        import app as flask_app
        flask_app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False, SECRET_KEY="test")
        with flask_app.app.test_client() as c:
            resp = c.get("/onboarding")
            assert resp.status_code == 302
            assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Integration: profile page completeness indicator
# ---------------------------------------------------------------------------

class TestProfileCompletenessUI:
    def test_completeness_bar_shown_on_profile_page(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/company-profile")
        assert resp.status_code == 200
        assert "Profile completion" in resp.data.decode()

    def test_completeness_100_shown(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/company-profile")
        assert "100%" in resp.data.decode()

    def test_no_completeness_bar_for_new_user(self, ob_client):
        # New user who skipped — no profile saved yet
        ob_client.get("/onboarding/skip")
        resp = ob_client.get("/company-profile")
        assert "Profile completion" not in resp.data.decode()


# ---------------------------------------------------------------------------
# Integration: dashboard completion hints
# ---------------------------------------------------------------------------

class TestDashboardHints:
    def test_hints_shown_for_incomplete_profile(self, ob_db, ob_client):
        user = users_module.get_user_by_email("ob@example.com")
        db_module.save_company_profile(user["id"], {
            "company_name": "Test",
            "website": "",
            "geo_coverage": "nationwide",
            "naics_codes": [],
            "agencies": [],
            "min_contract_value": None,
            "max_contract_value": None,
            "set_asides": [],
            "states": [],
        })
        resp = ob_client.get("/dashboard")
        assert resp.status_code == 200
        assert "Complete your profile" in resp.data.decode()

    def test_hints_not_shown_for_complete_profile(self, ob_client_with_profile):
        resp = ob_client_with_profile.get("/dashboard")
        assert resp.status_code == 200
        assert "Complete your profile" not in resp.data.decode()

    def test_empty_state_cta_links_to_onboarding(self, ob_db, ob_client):
        ob_client.get("/onboarding/skip")
        resp = ob_client.get("/dashboard")
        assert resp.status_code == 200
        assert "/onboarding" in resp.data.decode()
