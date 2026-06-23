"""
Tests for the multi-contract comparison insights panel
(Contract Intelligence Tools lane).

Covers:
- compare_insights pure logic (recommended pick + highlights)
- edge cases (fewer than two rows, missing fields)
- /compare route renders the Comparison Insights panel
"""

from unittest.mock import patch, MagicMock
import pytest
import db as db_module
from contract_summary import compare_insights


# ---------------------------------------------------------------------------
# compare_insights — pure logic
# ---------------------------------------------------------------------------

def test_insights_none_for_single_row():
    assert compare_insights([{"internal_id": "A", "value": 100}]) is None


def test_insights_none_for_empty():
    assert compare_insights([]) is None
    assert compare_insights([None, None]) is None


def test_insights_highest_value():
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "value": 1_000_000, "recompete_score": 50},
        {"internal_id": "B", "award_id": "AW-B", "value": 3_000_000, "recompete_score": 60},
    ]
    ins = compare_insights(rows)
    hv = next(h for h in ins["highlights"] if h["title"] == "Highest value")
    assert hv["internal_id"] == "B"
    assert hv["detail"] == "$3,000,000"


def test_insights_best_score():
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "value": 1_000_000, "recompete_score": 95},
        {"internal_id": "B", "award_id": "AW-B", "value": 3_000_000, "recompete_score": 60},
    ]
    ins = compare_insights(rows)
    bs = next(h for h in ins["highlights"] if h["title"] == "Best recompete score")
    assert bs["internal_id"] == "A"
    assert bs["detail"] == "95/100"


def test_insights_soonest_recompete_only_active():
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "days_remaining": 200, "recompete_score": 50},
        {"internal_id": "B", "award_id": "AW-B", "days_remaining": 30, "recompete_score": 50},
        {"internal_id": "C", "award_id": "AW-C", "days_remaining": -5, "recompete_score": 50},
    ]
    ins = compare_insights(rows)
    soon = next(h for h in ins["highlights"] if h["title"] == "Soonest recompete")
    assert soon["internal_id"] == "B"
    assert soon["detail"] == "30 days remaining"


def test_insights_no_soonest_when_none_active():
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "days_remaining": -1, "recompete_score": 50},
        {"internal_id": "B", "award_id": "AW-B", "days_remaining": 0, "recompete_score": 50},
    ]
    ins = compare_insights(rows)
    titles = {h["title"] for h in ins["highlights"]}
    assert "Soonest recompete" not in titles


def test_insights_recommended_by_score():
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "value": 1_000_000, "recompete_score": 95, "days_remaining": 100},
        {"internal_id": "B", "award_id": "AW-B", "value": 3_000_000, "recompete_score": 60, "days_remaining": 20},
    ]
    ins = compare_insights(rows)
    assert ins["recommended"]["internal_id"] == "A"
    assert "highest recompete score" in ins["recommended"]["reason"]


def test_insights_recommended_tiebreak_urgency():
    # Equal scores → soonest active recompete wins.
    rows = [
        {"internal_id": "A", "award_id": "AW-A", "recompete_score": 80, "days_remaining": 200},
        {"internal_id": "B", "award_id": "AW-B", "recompete_score": 80, "days_remaining": 45},
    ]
    ins = compare_insights(rows)
    assert ins["recommended"]["internal_id"] == "B"


def test_insights_handles_missing_fields():
    rows = [
        {"internal_id": "A", "award_id": "AW-A"},
        {"internal_id": "B", "award_id": "AW-B"},
    ]
    ins = compare_insights(rows)
    # No value/score/days → no highlights, but still a recommended pick + reason
    assert ins["recommended"]["label"] in ("AW-A", "AW-B")
    assert ins["recommended"]["reason"]


def test_insights_label_falls_back_to_internal_id():
    rows = [
        {"internal_id": "A", "value": 100, "recompete_score": 90},
        {"internal_id": "B", "value": 200, "recompete_score": 50},
    ]
    ins = compare_insights(rows)
    assert ins["recommended"]["label"] == "A"


# ---------------------------------------------------------------------------
# /compare route rendering
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "ci_insights.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts (internal_id, award_id, vendor, agency, value, "
            "end_date, days_remaining, priority, recompete_score) "
            "VALUES ('IN1','AW-1','Acme','DOD',1000000,'2026-12-31',120,'HIGH',95)"
        )
        con.execute(
            "INSERT INTO contracts (internal_id, award_id, vendor, agency, value, "
            "end_date, days_remaining, priority, recompete_score) "
            "VALUES ('IN2','AW-2','Beta','DHS',3000000,'2026-06-30',20,'CRITICAL',70)"
        )
        con.commit()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "ci-insights-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            rv = c.post("/register", data={
                "email": "insights@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        assert rv.status_code in (200, 302)
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


def test_compare_renders_insights_panel(client):
    rv = client.get("/compare?a=IN1&b=IN2")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert 'data-testid="compare-insights"' in body
    assert "Comparison Insights" in body
    assert "Recommended" in body
    # IN1 has the best score (95) → recommended
    assert "AW-1" in body


def test_compare_insights_absent_for_single_contract(client):
    rv = client.get("/compare?a=IN1")
    assert rv.status_code == 200
    # Only one contract found → no insights panel
    assert b'data-testid="compare-insights"' not in rv.data


def test_compare_insights_shows_highlights(client):
    rv = client.get("/compare?a=IN1&b=IN2")
    body = rv.data.decode()
    assert "Highest value" in body
    assert "Best recompete score" in body
    assert "Soonest recompete" in body
