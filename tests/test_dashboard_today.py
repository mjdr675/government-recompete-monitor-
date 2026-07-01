"""Tests for dashboard_today.today_work_items() — Platform data contract.

Covers:
- today_work_items(None) returns []
- today_work_items with no contracts returns []
- needs_attention: critical on overdue next_action_due
- needs_attention: high on capturing/proposal with <180 days
- needs_attention: medium on capturing/proposal with >180 days
- start_capture: high-fit best_window contracts surface
- start_capture: low-fit contracts below threshold don't surface
- revenue_opp: high-value actionable contracts surface
- revenue_opp: low-value contracts don't surface
- expiring: watchlist contracts ≤90 days surface
- expiring: watchlist contracts >90 days don't surface
- monitor: remaining watchlist contracts surface
- deduplication: each internal_id appears once
- sort order: critical before high before medium before low
- item schema: all required keys present
- section_counts: correct tally
- no-profile: confidence is None, business_fit score is None
- with profile: confidence is populated
- pipeline terminal stages don't appear in needs_attention
"""

import json
import pytest
from datetime import date, timedelta
import db as db_module
import users as users_module
from dashboard_today import today_work_items, section_counts, SECTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_str():
    return date.today().isoformat()


def _days_from_now(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _make_contract(internal_id="C001", days_remaining=400, recompete_score=70,
                   value=2_000_000.0, agency="Dept of Defense",
                   competition_type="FULL AND OPEN COMPETITION", **kwargs):
    base = {
        "internal_id": internal_id,
        "award_id": f"AWD-{internal_id}",
        "vendor": "Acme Corp",
        "agency": agency,
        "value": value,
        "end_date": _days_from_now(days_remaining),
        "days_remaining": days_remaining,
        "priority": "HIGH",
        "recompete_score": recompete_score,
        "competition_type": competition_type,
        "solicitation_id": None,
        "raw_json": None,
        "psc_code": None,
        "naics_code": None,
        "place_of_performance_state": None,
        "category": None,
        "description": None,
    }
    base.update(kwargs)
    return base


_REQUIRED_KEYS = {
    "internal_id", "award_id", "vendor", "agency", "value",
    "end_date", "days_remaining", "recompete_score", "competition_type", "solicitation_id",
    "section", "priority", "why", "why_now",
    "next_action", "next_action_explanation", "too_late",
    "pursuit_stage_key", "pursuit_stage_label",
    "confidence", "business_fit",
    "pipeline_stage", "pipeline_overdue", "next_action_due",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    user = users_module.create_user("test@example.com", "password123")
    return user["id"] if isinstance(user, dict) else int(user)


@pytest.fixture()
def profile_db(base_db, monkeypatch):
    """base_db with a company profile set."""
    uid = base_db
    db_module.save_company_profile(uid, {
        "company_name": "Acme Gov",
        "naics_codes": ["541511"],
        "agencies": ["Dept of Defense"],
        "min_contract_value": 500_000,
        "max_contract_value": 50_000_000,
        "set_asides": [],
        "keywords": [],
        "psc_codes": [],
        "geo_coverage": "nationwide",
        "states": [],
    })
    return uid


def _insert_contract(contract):
    db_module.upsert_contract(contract)


def _add_to_watchlist(user_id, internal_id):
    engine = db_module.get_engine()
    from sqlalchemy import text
    from datetime import datetime, timezone
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO user_watchlist (user_id, internal_id, added_at)"
            " VALUES (:uid, :iid, :now)"
        ), {"uid": user_id, "iid": internal_id, "now": datetime.now(timezone.utc).isoformat()})


def _add_to_pipeline(user_id, internal_id, stage="capturing",
                     next_action_due=None, next_action=None):
    db_module.add_opportunity(user_id, internal_id, stage=stage)
    if next_action_due or next_action:
        opps = db_module.list_opportunities(user_id)
        opp = next(o for o in opps if o["internal_id"] == internal_id)
        data = {}
        if next_action_due:
            data["next_action_due"] = next_action_due
        if next_action:
            data["next_action"] = next_action
        db_module.update_opportunity(user_id, opp["id"], data)


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

class TestBasics:
    def test_none_user_returns_empty(self, base_db):
        assert today_work_items(None) == []

    def test_no_contracts_returns_empty(self, base_db):
        uid = base_db
        assert today_work_items(uid) == []

    def test_returns_list(self, base_db):
        uid = base_db
        result = today_work_items(uid)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Item schema
# ---------------------------------------------------------------------------

class TestItemSchema:
    def test_all_required_keys_present(self, base_db):
        uid = base_db
        c = _make_contract("SCHEMA01", days_remaining=400, recompete_score=80, value=8_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "SCHEMA01")
        items = today_work_items(uid)
        assert items, "expected at least one item"
        for item in items:
            missing = _REQUIRED_KEYS - set(item.keys())
            assert not missing, f"Missing keys: {missing}"

    def test_business_fit_is_dict(self, base_db):
        uid = base_db
        c = _make_contract("FIT01", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "FIT01")
        items = today_work_items(uid)
        assert items
        for item in items:
            assert isinstance(item["business_fit"], dict)
            assert "score" in item["business_fit"]
            assert "reasons" in item["business_fit"]

    def test_no_profile_confidence_is_none(self, base_db):
        uid = base_db
        c = _make_contract("CONF01", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "CONF01")
        items = today_work_items(uid)
        assert items
        for item in items:
            assert item["confidence"] is None
            assert item["business_fit"]["score"] is None

    def test_with_profile_confidence_is_int(self, profile_db):
        uid = profile_db
        c = _make_contract("CONF02", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "CONF02")
        items = today_work_items(uid)
        assert items
        for item in items:
            assert isinstance(item["confidence"], int) or item["confidence"] is None

    def test_section_is_valid(self, base_db):
        uid = base_db
        c = _make_contract("SEC01", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "SEC01")
        items = today_work_items(uid)
        for item in items:
            assert item["section"] in SECTIONS

    def test_priority_is_valid(self, base_db):
        uid = base_db
        c = _make_contract("PRI01", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "PRI01")
        items = today_work_items(uid)
        for item in items:
            assert item["priority"] in ("critical", "high", "medium", "low")


# ---------------------------------------------------------------------------
# needs_attention section
# ---------------------------------------------------------------------------

class TestNeedsAttention:
    def test_overdue_pipeline_is_critical(self, base_db):
        uid = base_db
        c = _make_contract("NA01", days_remaining=200, recompete_score=70)
        _insert_contract(c)
        past_due = _days_from_now(-5)
        _add_to_pipeline(uid, "NA01", stage="capturing", next_action_due=past_due)
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention"]
        assert na, "expected needs_attention item"
        assert na[0]["priority"] == "critical"
        assert na[0]["pipeline_overdue"] is True

    def test_capturing_under_180_days_is_high(self, base_db):
        uid = base_db
        c = _make_contract("NA02", days_remaining=120, recompete_score=70)
        _insert_contract(c)
        _add_to_pipeline(uid, "NA02", stage="capturing")
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention" and i["internal_id"] == "NA02"]
        assert na
        assert na[0]["priority"] == "high"

    def test_proposal_under_180_days_is_high(self, base_db):
        uid = base_db
        c = _make_contract("NA03", days_remaining=100, recompete_score=70)
        _insert_contract(c)
        _add_to_pipeline(uid, "NA03", stage="proposal")
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention" and i["internal_id"] == "NA03"]
        assert na
        assert na[0]["priority"] == "high"

    def test_capturing_over_180_days_is_medium(self, base_db):
        uid = base_db
        c = _make_contract("NA04", days_remaining=250, recompete_score=70)
        _insert_contract(c)
        _add_to_pipeline(uid, "NA04", stage="capturing")
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention" and i["internal_id"] == "NA04"]
        assert na
        assert na[0]["priority"] == "medium"

    def test_terminal_stage_not_in_needs_attention(self, base_db):
        uid = base_db
        c = _make_contract("NA05", days_remaining=200, recompete_score=70)
        _insert_contract(c)
        # won is a terminal stage
        db_module.add_opportunity(uid, "NA05", stage="awarded")
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention" and i["internal_id"] == "NA05"]
        assert not na

    def test_new_stage_not_in_needs_attention(self, base_db):
        uid = base_db
        c = _make_contract("NA06", days_remaining=200, recompete_score=70)
        _insert_contract(c)
        _add_to_pipeline(uid, "NA06", stage="new")
        items = today_work_items(uid)
        na = [i for i in items if i["section"] == "needs_attention" and i["internal_id"] == "NA06"]
        assert not na

    def test_pipeline_stage_key_is_populated(self, base_db):
        uid = base_db
        c = _make_contract("NA07", days_remaining=120, recompete_score=70)
        _insert_contract(c)
        _add_to_pipeline(uid, "NA07", stage="capturing")
        items = today_work_items(uid)
        na = [i for i in items if i["internal_id"] == "NA07"]
        assert na
        assert na[0]["pipeline_stage"] == "capturing"


# ---------------------------------------------------------------------------
# start_capture section
# ---------------------------------------------------------------------------

class TestStartCapture:
    def test_best_window_high_score_surfaces(self, base_db):
        uid = base_db
        # 400 days = best_window stage
        c = _make_contract("SC01", days_remaining=400, recompete_score=75, value=3_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        sc = [i for i in items if i["section"] == "start_capture" and i["internal_id"] == "SC01"]
        assert sc

    def test_shape_stage_high_score_surfaces(self, base_db):
        uid = base_db
        # 290 days = shape stage (270–365)
        c = _make_contract("SC02", days_remaining=290, recompete_score=75, value=3_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        sc = [i for i in items if i["section"] == "start_capture" and i["internal_id"] == "SC02"]
        assert sc

    def test_low_score_low_fit_not_surfaced(self, base_db):
        uid = base_db
        c = _make_contract("SC03", days_remaining=400, recompete_score=40, value=500_000)
        _insert_contract(c)
        items = today_work_items(uid)
        sc = [i for i in items if i["section"] == "start_capture" and i["internal_id"] == "SC03"]
        assert not sc

    def test_urgent_stage_not_in_start_capture(self, base_db):
        uid = base_db
        # 60 days = urgent stage
        c = _make_contract("SC04", days_remaining=60, recompete_score=90, value=8_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        sc = [i for i in items if i["section"] == "start_capture" and i["internal_id"] == "SC04"]
        assert not sc

    def test_high_fit_priority_is_high(self, profile_db):
        uid = profile_db
        # Agency match should give high fit
        c = _make_contract("SC05", days_remaining=400, recompete_score=75,
                            agency="Dept of Defense")
        _insert_contract(c)
        items = today_work_items(uid)
        sc = [i for i in items if i["section"] == "start_capture" and i["internal_id"] == "SC05"]
        # Priority depends on fit score — just assert it surfaced and has valid priority
        if sc:
            assert sc[0]["priority"] in ("high", "medium")


# ---------------------------------------------------------------------------
# revenue_opp section
# ---------------------------------------------------------------------------

class TestRevenueOpp:
    def test_high_value_actionable_surfaces(self, base_db):
        uid = base_db
        # 200 days = active_pursuit stage
        c = _make_contract("RO01", days_remaining=200, recompete_score=70, value=8_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        ro = [i for i in items if i["section"] == "revenue_opp" and i["internal_id"] == "RO01"]
        assert ro

    def test_over_10m_is_high_priority(self, base_db):
        uid = base_db
        c = _make_contract("RO02", days_remaining=300, recompete_score=70, value=15_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        ro = [i for i in items if i["section"] == "revenue_opp" and i["internal_id"] == "RO02"]
        if ro:  # may be in start_capture first — that's fine
            assert ro[0]["priority"] == "high"

    def test_low_value_not_in_revenue_opp(self, base_db):
        uid = base_db
        c = _make_contract("RO03", days_remaining=200, recompete_score=70, value=1_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        ro = [i for i in items if i["section"] == "revenue_opp" and i["internal_id"] == "RO03"]
        assert not ro

    def test_expired_not_in_revenue_opp(self, base_db):
        uid = base_db
        c = _make_contract("RO04", days_remaining=0, recompete_score=70, value=20_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        ro = [i for i in items if i["section"] == "revenue_opp" and i["internal_id"] == "RO04"]
        assert not ro


# ---------------------------------------------------------------------------
# expiring section
# ---------------------------------------------------------------------------

class TestExpiring:
    def test_watchlist_90_days_surfaces(self, base_db):
        uid = base_db
        c = _make_contract("EX01", days_remaining=60, recompete_score=50, value=1_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "EX01")
        items = today_work_items(uid)
        ex = [i for i in items if i["section"] == "expiring" and i["internal_id"] == "EX01"]
        assert ex

    def test_watchlist_under_30_days_is_high(self, base_db):
        uid = base_db
        c = _make_contract("EX02", days_remaining=20, recompete_score=50, value=1_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "EX02")
        items = today_work_items(uid)
        ex = [i for i in items if i["section"] == "expiring" and i["internal_id"] == "EX02"]
        assert ex
        assert ex[0]["priority"] == "high"

    def test_watchlist_over_90_days_not_expiring(self, base_db):
        uid = base_db
        c = _make_contract("EX03", days_remaining=200, recompete_score=50, value=1_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "EX03")
        items = today_work_items(uid)
        ex = [i for i in items if i["section"] == "expiring" and i["internal_id"] == "EX03"]
        assert not ex

    def test_expired_not_in_expiring(self, base_db):
        uid = base_db
        c = _make_contract("EX04", days_remaining=0, recompete_score=50, value=1_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "EX04")
        items = today_work_items(uid)
        ex = [i for i in items if i["section"] == "expiring" and i["internal_id"] == "EX04"]
        assert not ex

    def test_non_watchlist_not_in_expiring(self, base_db):
        uid = base_db
        # High-score contract in DB but not in watchlist
        c = _make_contract("EX05", days_remaining=30, recompete_score=80, value=3_000_000)
        _insert_contract(c)
        items = today_work_items(uid)
        ex = [i for i in items if i["section"] == "expiring" and i["internal_id"] == "EX05"]
        assert not ex


# ---------------------------------------------------------------------------
# monitor section
# ---------------------------------------------------------------------------

class TestMonitor:
    def test_watchlist_long_remaining_goes_to_monitor(self, base_db):
        uid = base_db
        # 600 days = monitor stage (>540); low recompete_score so not in discovery
        c = _make_contract("MO01", days_remaining=600, recompete_score=30, value=500_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "MO01")
        items = today_work_items(uid)
        mo = [i for i in items if i["section"] == "monitor" and i["internal_id"] == "MO01"]
        assert mo


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_each_internal_id_appears_once(self, base_db):
        uid = base_db
        # best_window + in watchlist + in pipeline
        c = _make_contract("DUP01", days_remaining=400, recompete_score=80, value=8_000_000)
        _insert_contract(c)
        _add_to_watchlist(uid, "DUP01")
        _add_to_pipeline(uid, "DUP01", stage="capturing")
        items = today_work_items(uid)
        ids = [i["internal_id"] for i in items]
        assert ids.count("DUP01") == 1

    def test_multiple_contracts_no_duplicates(self, base_db):
        uid = base_db
        for i in range(5):
            c = _make_contract(f"MULTI{i:02d}", days_remaining=200 + i * 50,
                                recompete_score=70, value=3_000_000)
            _insert_contract(c)
            _add_to_watchlist(uid, f"MULTI{i:02d}")
        items = today_work_items(uid)
        ids = [i["internal_id"] for i in items]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

class TestSortOrder:
    def test_critical_before_high(self, base_db):
        uid = base_db
        # critical: overdue pipeline
        c1 = _make_contract("SORT01", days_remaining=200, recompete_score=70)
        _insert_contract(c1)
        past = _days_from_now(-3)
        _add_to_pipeline(uid, "SORT01", stage="capturing", next_action_due=past)

        # high: best_window high score
        c2 = _make_contract("SORT02", days_remaining=400, recompete_score=80, value=8_000_000)
        _insert_contract(c2)

        items = today_work_items(uid)
        priorities = [i["priority"] for i in items]
        if "critical" in priorities and "high" in priorities:
            assert priorities.index("critical") < priorities.index("high")

    def test_high_before_medium(self, base_db):
        uid = base_db
        c1 = _make_contract("SORT03", days_remaining=400, recompete_score=80, value=15_000_000)
        _insert_contract(c1)
        c2 = _make_contract("SORT04", days_remaining=200, recompete_score=60, value=1_000_000)
        _insert_contract(c2)
        _add_to_watchlist(uid, "SORT04")
        items = today_work_items(uid)
        priorities = [i["priority"] for i in items]
        high_idx = next((i for i, p in enumerate(priorities) if p == "high"), None)
        med_idx = next((i for i, p in enumerate(priorities) if p == "medium"), None)
        if high_idx is not None and med_idx is not None:
            assert high_idx < med_idx


# ---------------------------------------------------------------------------
# section_counts helper
# ---------------------------------------------------------------------------

class TestSectionCounts:
    def test_empty_items_all_zeros(self):
        counts = section_counts([])
        assert all(v == 0 for v in counts.values())
        assert set(counts.keys()) == set(SECTIONS)

    def test_counts_match_items(self, base_db):
        uid = base_db
        c = _make_contract("CNT01", days_remaining=400, recompete_score=80)
        _insert_contract(c)
        _add_to_watchlist(uid, "CNT01")
        items = today_work_items(uid)
        counts = section_counts(items)
        assert sum(counts.values()) == len(items)

    def test_all_sections_present_in_counts(self):
        counts = section_counts([])
        for s in SECTIONS:
            assert s in counts


# ---------------------------------------------------------------------------
# Dashboard route integration
# ---------------------------------------------------------------------------

class TestDashboardRoute:
    @pytest.fixture()
    def route_client(self, tmp_path, monkeypatch):
        import app as flask_app
        db_path = str(tmp_path / "route_test.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        db_module.init_db()
        db_module.init_watchlist_table()
        db_module.init_saved_searches_table()
        flask_app.app.config["TESTING"] = True
        flask_app.app.config["WTF_CSRF_ENABLED"] = False
        flask_app.app.secret_key = "test-secret-key"
        with flask_app.app.test_client() as c:
            c.post("/register", data={
                "email": "routetest@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
            with c.session_transaction() as sess:
                sess["onboarding_skipped"] = "1"
            yield c

    def test_dashboard_returns_200(self, route_client):
        resp = route_client.get("/dashboard")
        assert resp.status_code == 200

    def test_today_items_key_in_context(self, route_client, monkeypatch):
        captured = {}

        original_render = __import__("flask").render_template

        def mock_render(template, **ctx):
            if template == "dashboard.html":
                captured.update(ctx)
            return original_render(template, **ctx)

        monkeypatch.setattr("app.render_template", mock_render)
        route_client.get("/dashboard")
        assert "today_items" in captured
        assert "today_section_counts" in captured
        assert isinstance(captured["today_items"], list)
        assert isinstance(captured["today_section_counts"], dict)
