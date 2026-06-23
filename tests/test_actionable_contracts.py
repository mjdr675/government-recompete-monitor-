"""Tests for the Actionable Contracts sprint.

Covers:
- recommended_action() — all decision branches
- why_it_matters() — each bullet trigger
- contract_timeline() — date ordering and edge cases
- contract detail page rendering: action card, why card, watch button, timeline
- dashboard: Recommended Actions section via dash_actions
- Edge cases: expired, null dates, low-score, missing fields
"""
import pytest
import db as db_module
from contract_summary import recommended_action, why_it_matters, contract_timeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kwargs):
    base = {
        "internal_id": "TEST001",
        "award_id": "A001",
        "vendor": "Acme Corp",
        "agency": "Dept of Test",
        "value": 500_000,
        "days_remaining": 400,
        "priority": "MEDIUM",
        "recompete_score": 65,
        "solicitation_id": "",
        "competition_type": "",
        "start_date": "2022-01-01",
        "end_date": "2026-06-01",
        "updated_at": "2025-01-15T00:00:00",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# recommended_action
# ---------------------------------------------------------------------------

class TestRecommendedAction:
    def test_expired_contract(self):
        result = recommended_action(_row(days_remaining=0))
        assert result["action"] == "Search for the follow-on award"

    def test_negative_days_is_expired(self):
        result = recommended_action(_row(days_remaining=-5))
        assert result["action"] == "Search for the follow-on award"

    def test_solicitation_on_file_beats_days(self):
        result = recommended_action(_row(days_remaining=45, solicitation_id="SOL-123"))
        assert "solicitation" in result["action"].lower()

    def test_very_imminent_30_days(self):
        result = recommended_action(_row(days_remaining=20))
        assert "immediately" in result["action"].lower()

    def test_within_90_days_contact_office(self):
        result = recommended_action(_row(days_remaining=60))
        assert "contracting office" in result["action"].lower()

    def test_within_180_days_high_score_capture(self):
        result = recommended_action(_row(days_remaining=150, recompete_score=80))
        assert "capture planning" in result["action"].lower()

    def test_within_180_days_low_score_not_capture(self):
        result = recommended_action(_row(days_remaining=150, recompete_score=50))
        # Falls through to teaming (365-day band) or lower — not capture
        assert "capture planning" not in result["action"].lower()

    def test_within_365_days_teaming(self):
        result = recommended_action(_row(days_remaining=300))
        assert "teaming" in result["action"].lower()

    def test_critical_priority_far_out(self):
        result = recommended_action(_row(days_remaining=600, priority="CRITICAL"))
        assert "solicitation" in result["action"].lower()

    def test_high_priority_far_out(self):
        result = recommended_action(_row(days_remaining=600, priority="HIGH"))
        assert "solicitation" in result["action"].lower()

    def test_full_and_open_research_incumbent(self):
        result = recommended_action(_row(
            days_remaining=600, priority="MEDIUM",
            competition_type="FULL AND OPEN COMPETITION"
        ))
        assert "incumbent" in result["action"].lower()

    def test_high_value_review_awards(self):
        result = recommended_action(_row(
            days_remaining=600, priority="MEDIUM",
            competition_type="", value=2_000_000
        ))
        assert "historical awards" in result["action"].lower()

    def test_default_continue_monitoring(self):
        result = recommended_action(_row(
            days_remaining=700, priority="LOW",
            competition_type="", value=50_000
        ))
        assert "monitoring" in result["action"].lower()

    def test_always_returns_action_and_explanation(self):
        for days in [None, -1, 0, 1, 30, 90, 180, 365, 730]:
            result = recommended_action(_row(days_remaining=days))
            assert "action" in result
            assert "explanation" in result
            assert result["action"]
            assert result["explanation"]

    def test_none_days_falls_through_to_default_or_other(self):
        result = recommended_action(_row(days_remaining=None, priority="LOW",
                                         competition_type="", value=10_000))
        assert "action" in result

    def test_string_days_coerced(self):
        result = recommended_action(_row(days_remaining="45"))
        assert result["action"] == "Contact the contracting office"


# ---------------------------------------------------------------------------
# why_it_matters
# ---------------------------------------------------------------------------

class TestWhyItMatters:
    def test_very_high_value(self):
        bullets = why_it_matters(_row(value=15_000_000))
        assert any("Very high contract value" in b for b in bullets)

    def test_high_value(self):
        bullets = why_it_matters(_row(value=2_000_000))
        assert any("High estimated contract value" in b for b in bullets)

    def test_no_value_bullet_below_threshold(self):
        bullets = why_it_matters(_row(value=500_000))
        assert not any("contract value" in b.lower() for b in bullets)

    def test_very_high_score(self):
        bullets = why_it_matters(_row(recompete_score=92))
        assert any("Very high opportunity score" in b for b in bullets)

    def test_high_score(self):
        bullets = why_it_matters(_row(recompete_score=78))
        assert any("High opportunity score" in b for b in bullets)

    def test_critical_priority(self):
        bullets = why_it_matters(_row(priority="CRITICAL"))
        assert any("Critical priority" in b for b in bullets)

    def test_high_priority(self):
        bullets = why_it_matters(_row(priority="HIGH"))
        assert any("High priority" in b for b in bullets)

    def test_very_soon_days(self):
        bullets = why_it_matters(_row(days_remaining=45))
        assert any("very soon" in b for b in bullets)

    def test_within_year_days(self):
        bullets = why_it_matters(_row(days_remaining=200))
        assert any("within the year" in b for b in bullets)

    def test_no_days_bullet_when_far_out(self):
        bullets = why_it_matters(_row(days_remaining=500))
        assert not any("days remaining" in b for b in bullets)

    def test_solicitation_on_file(self):
        bullets = why_it_matters(_row(solicitation_id="SOL-999"))
        assert any("Solicitation" in b for b in bullets)

    def test_dod_agency(self):
        bullets = why_it_matters(_row(agency="Department of Defense"))
        assert any("Defense" in b for b in bullets)

    def test_va_agency(self):
        bullets = why_it_matters(_row(agency="Department of Veterans Affairs"))
        assert any("Veterans Affairs" in b for b in bullets)

    def test_full_open_competition(self):
        bullets = why_it_matters(_row(competition_type="FULL AND OPEN COMPETITION"))
        assert any("Full and open competition" in b for b in bullets)

    def test_always_returns_at_least_one_bullet(self):
        bullets = why_it_matters(_row(value=0, recompete_score=0, priority="",
                                       solicitation_id="", agency="", competition_type=""))
        assert len(bullets) >= 1

    def test_expired_no_days_bullet(self):
        bullets = why_it_matters(_row(days_remaining=-5))
        assert not any("days remaining" in b for b in bullets)


# ---------------------------------------------------------------------------
# contract_timeline
# ---------------------------------------------------------------------------

class TestContractTimeline:
    def test_full_timeline_sorted(self):
        events = contract_timeline(_row(
            start_date="2022-01-01",
            updated_at="2025-06-01T00:00:00",
            end_date="2026-06-01",
            days_remaining=350,
        ))
        dates = [e["date"] for e in events]
        assert dates == sorted(dates)

    def test_start_event_present(self):
        events = contract_timeline(_row(start_date="2022-01-01"))
        assert any(e["type"] == "start" for e in events)

    def test_end_event_labeled_expires(self):
        events = contract_timeline(_row(end_date="2026-06-01", days_remaining=200))
        end = next(e for e in events if e["type"] == "end")
        assert end["event"] == "Contract expires"

    def test_end_event_labeled_expired_when_past(self):
        events = contract_timeline(_row(end_date="2020-01-01", days_remaining=-500))
        end = next(e for e in events if e["type"] == "end")
        assert end["event"] == "Contract expired"

    def test_no_start_date_omits_start(self):
        events = contract_timeline(_row(start_date=""))
        assert not any(e["type"] == "start" for e in events)

    def test_no_end_date_omits_end(self):
        events = contract_timeline(_row(end_date=""))
        assert not any(e["type"] == "end" for e in events)

    def test_update_omitted_when_same_as_start(self):
        events = contract_timeline(_row(
            start_date="2022-01-01",
            updated_at="2022-01-01T12:00:00",
            end_date="",
        ))
        assert not any(e["type"] == "update" for e in events)

    def test_minimal_two_events(self):
        events = contract_timeline(_row(start_date="2022-01-01", updated_at="",
                                         end_date="2026-01-01", days_remaining=100))
        assert len(events) == 2

    def test_empty_row_returns_empty_list(self):
        events = contract_timeline({"internal_id": "X"})
        assert events == []


# ---------------------------------------------------------------------------
# Contract detail page integration
# ---------------------------------------------------------------------------

@pytest.fixture()
def detail_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.upsert_contract({
        "internal_id": "DETAIL001",
        "award_id": "A-DETAIL",
        "vendor": "Test Vendor",
        "agency": "Test Agency",
        "value": 5_000_000,
        "days_remaining": 60,
        "priority": "HIGH",
        "recompete_score": 80,
        "solicitation_id": "",
        "competition_type": "FULL AND OPEN COMPETITION",
        "start_date": "2022-01-01",
        "end_date": "2026-08-01",
        "updated_at": "2025-01-01",
    })
    yield db_path


@pytest.fixture()
def detail_client(detail_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "detail@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        yield c


def test_detail_page_shows_action_card(detail_client):
    rv = detail_client.get("/contract/DETAIL001")
    assert rv.status_code == 200
    assert b"Next Recommended Action" in rv.data


def test_detail_page_shows_why_matters(detail_client):
    rv = detail_client.get("/contract/DETAIL001")
    assert rv.status_code == 200
    assert b"Why This Opportunity Matters" in rv.data


def test_detail_page_shows_watch_button(detail_client):
    rv = detail_client.get("/contract/DETAIL001")
    assert rv.status_code == 200
    assert b"Watch" in rv.data


def test_detail_page_shows_timeline(detail_client):
    rv = detail_client.get("/contract/DETAIL001")
    assert rv.status_code == 200
    assert b"Contract Activity" in rv.data
    assert b"Contract awarded" in rv.data


def test_detail_page_watching_state_after_add(detail_client):
    detail_client.post("/watchlist/add", json={"internal_id": "DETAIL001"})
    rv = detail_client.get("/contract/DETAIL001")
    assert b"Watching" in rv.data


def test_detail_page_action_content_for_high_score_soon(detail_client):
    rv = detail_client.get("/contract/DETAIL001")
    assert rv.status_code == 200
    # days=60, score=80 → "Contact the contracting office"
    assert b"contracting office" in rv.data


# ---------------------------------------------------------------------------
# Dashboard recommended actions
# ---------------------------------------------------------------------------

@pytest.fixture()
def dash_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "dash.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.upsert_contract({
        "internal_id": "DASH001",
        "award_id": "D-001",
        "vendor": "Alpha Corp",
        "agency": "DoD",
        "value": 3_000_000,
        "days_remaining": 120,
        "priority": "CRITICAL",
        "recompete_score": 92,
        "solicitation_id": "",
        "competition_type": "",
        "start_date": "2022-01-01",
        "end_date": "2026-10-01",
    })
    yield db_path


@pytest.fixture()
def dash_client(dash_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "dash@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


def test_dashboard_shows_recommended_actions_section(dash_client):
    rv = dash_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"Recommended Actions" in rv.data


def test_dashboard_recommended_actions_include_contract(dash_client):
    rv = dash_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"Alpha Corp" in rv.data


def test_dashboard_recommended_actions_arrow_prefix(dash_client):
    rv = dash_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"\xe2\x86\x92" in rv.data  # UTF-8 for →


def test_dashboard_watched_contract_gets_star(dash_client):
    dash_client.post("/watchlist/add", json={"internal_id": "DASH001"})
    rv = dash_client.get("/dashboard")
    assert rv.status_code == 200
    assert b"\xe2\x98\x85" in rv.data  # UTF-8 for ★


# ---------------------------------------------------------------------------
# dashboard_recommended_actions function unit tests
# ---------------------------------------------------------------------------

def test_dashboard_recommended_actions_returns_list(dash_db):
    from analytics import dashboard_recommended_actions
    result = dashboard_recommended_actions(user_id=None)
    assert isinstance(result, list)


def test_dashboard_recommended_actions_has_next_action_key(dash_db):
    from analytics import dashboard_recommended_actions
    result = dashboard_recommended_actions(user_id=None)
    for r in result:
        assert "next_action" in r
        assert r["next_action"]


def test_dashboard_recommended_actions_deduplicates(dash_db):
    from analytics import dashboard_recommended_actions
    result = dashboard_recommended_actions(user_id=None)
    ids = [r["internal_id"] for r in result]
    assert len(ids) == len(set(ids))


def test_dashboard_recommended_actions_max_five(dash_db):
    from analytics import dashboard_recommended_actions
    result = dashboard_recommended_actions(user_id=None)
    assert len(result) <= 5
