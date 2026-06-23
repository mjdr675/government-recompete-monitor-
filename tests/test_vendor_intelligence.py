"""
Comprehensive tests for Vendor Intelligence dashboard.

Covers:
  - charts.py helper functions
  - analytics.vendor_profile_analytics (all sub-dicts)
  - /vendor/<name> HTTP route
"""

import pytest
import sqlite3

import db as db_module
from db import connect
import charts
from analytics import vendor_profile_analytics
from app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield db_path


def _contract(internal_id, vendor, agency, value, priority, score, days, end_date=None):
    db_module.upsert_contract({
        "internal_id": internal_id,
        "award_id": f"AW-{internal_id}",
        "vendor": vendor,
        "agency": agency,
        "value": value,
        "priority": priority,
        "recompete_score": score,
        "days_remaining": days,
        "end_date": end_date or "2026-12-31",
    })


def _seed_vendor(tmp_db, vendor="Acme Corp"):
    """Seed a realistic vendor with 5 contracts across 2 agencies."""
    _contract("A1", vendor, "DEFENSE", 5_000_000, "CRITICAL", 90, 45,  "2026-08-14")
    _contract("A2", vendor, "DEFENSE", 2_000_000, "HIGH",     75, 120, "2026-10-28")
    _contract("A3", vendor, "DEFENSE", 3_000_000, "MEDIUM",   60, 365, "2027-06-18")
    _contract("A4", vendor, "NASA",    1_000_000, "HIGH",     70, 60,  "2026-09-17")
    _contract("A5", vendor, "NASA",    4_000_000, "CRITICAL", 85, 30,  "2026-07-18")


@pytest.fixture()
def seeded_db(tmp_db):
    _seed_vendor(tmp_db)
    return tmp_db


@pytest.fixture()
def con(seeded_db):
    c = sqlite3.connect(seeded_db)
    yield c
    c.close()


@pytest.fixture()
def profile(con):
    return vendor_profile_analytics(con, "Acme Corp")


@pytest.fixture()
def client(tmp_db):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# charts.py unit tests
# ---------------------------------------------------------------------------

class TestChartsHelpers:
    def test_bar_chart_structure(self):
        d = charts.bar_chart(["A", "B"], [10, 20], label="Test")
        assert d["labels"] == ["A", "B"]
        assert len(d["datasets"]) == 1
        assert d["datasets"][0]["data"] == [10, 20]
        assert d["datasets"][0]["label"] == "Test"

    def test_bar_chart_default_color(self):
        d = charts.bar_chart(["X"], [1])
        assert d["datasets"][0]["backgroundColor"] == "#1f4f8f"

    def test_bar_chart_custom_color(self):
        d = charts.bar_chart(["X"], [1], color="#ff0000")
        assert d["datasets"][0]["backgroundColor"] == "#ff0000"

    def test_pie_chart_structure(self):
        d = charts.pie_chart(["A", "B", "C"], [1, 2, 3])
        assert d["labels"] == ["A", "B", "C"]
        assert d["datasets"][0]["data"] == [1, 2, 3]
        assert len(d["datasets"][0]["backgroundColor"]) == 3

    def test_pie_chart_custom_colors(self):
        colors = ["#aaa", "#bbb"]
        d = charts.pie_chart(["X", "Y"], [5, 10], colors=colors)
        assert d["datasets"][0]["backgroundColor"] == colors

    def test_priority_pie_canonical_order(self):
        counts = {"LOW": 1, "CRITICAL": 3, "HIGH": 2}
        d = charts.priority_pie(counts)
        assert d["labels"] == ["CRITICAL", "HIGH", "LOW"]
        assert d["datasets"][0]["data"] == [3, 2, 1]

    def test_priority_pie_uses_priority_colors(self):
        d = charts.priority_pie({"CRITICAL": 1})
        assert d["datasets"][0]["backgroundColor"][0] == charts.PRIORITY_COLORS["CRITICAL"]

    def test_priority_pie_skips_zero_counts(self):
        d = charts.priority_pie({"CRITICAL": 2, "LOW": 0})
        assert "LOW" not in d["labels"]

    def test_agency_bar_output(self):
        d = charts.agency_bar([("DoD", 1_000_000), ("NASA", 500_000)])
        assert d["labels"] == ["DoD", "NASA"]
        assert d["datasets"][0]["data"] == [1_000_000, 500_000]

    def test_monthly_bar_output(self):
        d = charts.monthly_bar([("2026-07", 3), ("2026-08", 2)])
        assert d["labels"] == ["2026-07", "2026-08"]
        assert d["datasets"][0]["data"] == [3, 2]

    def test_empty_inputs(self):
        assert charts.bar_chart([], []) == {
            "labels": [],
            "datasets": [{"label": "", "data": [], "backgroundColor": "#1f4f8f",
                          "borderRadius": 4, "borderSkipped": False}],
        }


# ---------------------------------------------------------------------------
# vendor_profile_analytics — summary
# ---------------------------------------------------------------------------

class TestVendorSummary:
    def test_contract_count(self, profile):
        assert profile["summary"]["contracts"] == 5

    def test_pipeline_value(self, profile):
        assert profile["summary"]["pipeline_value"] == 15_000_000

    def test_critical_count(self, profile):
        assert profile["summary"]["critical_contracts"] == 2

    def test_avg_score(self, profile):
        assert round(profile["summary"]["avg_score"], 1) == 76.0

    def test_avg_days_remaining(self, profile):
        assert profile["summary"]["avg_days_remaining"] == pytest.approx(124.0)

    def test_earliest_expiration(self, profile):
        assert profile["summary"]["earliest_expiration"] == "2026-07-18"

    def test_latest_expiration(self, profile):
        assert profile["summary"]["latest_expiration"] == "2027-06-18"

    def test_unknown_vendor_zeros(self, con):
        p = vendor_profile_analytics(con, "No Such Vendor")
        assert p["summary"]["contracts"] == 0
        assert p["summary"]["pipeline_value"] == 0


# ---------------------------------------------------------------------------
# vendor_profile_analytics — agency breakdown
# ---------------------------------------------------------------------------

class TestAgencyBreakdown:
    def test_agencies_present(self, profile):
        names = [a["agency"] for a in profile["agencies"]]
        assert "DEFENSE" in names
        assert "NASA" in names

    def test_sorted_by_pipeline_value_desc(self, profile):
        values = [a["pipeline_value"] for a in profile["agencies"]]
        assert values == sorted(values, reverse=True)

    def test_defense_pipeline_value(self, profile):
        defense = next(a for a in profile["agencies"] if a["agency"] == "DEFENSE")
        assert defense["pipeline_value"] == 10_000_000
        assert defense["contracts"] == 3

    def test_agency_avg_score_present(self, profile):
        for a in profile["agencies"]:
            assert "avg_score" in a
            assert a["avg_score"] >= 0


# ---------------------------------------------------------------------------
# vendor_profile_analytics — upcoming recompetes
# ---------------------------------------------------------------------------

class TestUpcomingRecompetes:
    def test_all_contracts_returned(self, profile):
        assert len(profile["upcoming"]) == 5

    def test_sorted_by_days_remaining_asc(self, profile):
        days = [r["days_remaining"] for r in profile["upcoming"]]
        assert days == sorted(days)

    def test_soonest_first(self, profile):
        assert profile["upcoming"][0]["days_remaining"] == 30

    def test_fields_present(self, profile):
        for r in profile["upcoming"]:
            for field in ("internal_id", "award_id", "agency", "value",
                          "end_date", "days_remaining", "priority", "recompete_score"):
                assert field in r


# ---------------------------------------------------------------------------
# vendor_profile_analytics — charts
# ---------------------------------------------------------------------------

class TestChartData:
    def test_charts_keys_present(self, profile):
        assert "priority" in profile["charts"]
        assert "pipeline_by_agency" in profile["charts"]
        assert "expiring_by_month" in profile["charts"]

    def test_priority_chart_has_critical(self, profile):
        assert "CRITICAL" in profile["charts"]["priority"]["labels"]

    def test_pipeline_by_agency_has_data(self, profile):
        d = profile["charts"]["pipeline_by_agency"]
        assert len(d["labels"]) == 2
        assert max(d["datasets"][0]["data"]) == 10_000_000

    def test_expiring_by_month_is_chronological(self, profile):
        labels = profile["charts"]["expiring_by_month"]["labels"]
        assert labels == sorted(labels)

    def test_chart_data_serialisable(self, profile):
        import json
        json.dumps(profile["charts"])  # must not raise


# ---------------------------------------------------------------------------
# vendor_profile_analytics — risk indicators
# ---------------------------------------------------------------------------

class TestRiskIndicators:
    def test_expiring_soon_count(self, profile):
        # A1=45d, A4=60d, A5=30d are all <90
        assert len(profile["risk"]["expiring_soon"]) == 3

    def test_critical_contracts_count(self, profile):
        assert len(profile["risk"]["critical"]) == 2

    def test_largest_contract(self, profile):
        assert profile["risk"]["largest_contract"]["internal_id"] == "A1"
        assert profile["risk"]["largest_contract"]["value"] == 5_000_000

    def test_multi_recompete_agencies(self, profile):
        # Both DEFENSE (A1=45d, A2=120d... wait A2=120d >180? no, within 180d)
        # DEFENSE: A1=45, A2=120 → 2 within 180 ✓
        # NASA: A4=60, A5=30 → 2 within 180 ✓
        multi = profile["risk"]["agencies_multi_recompete"]
        assert "DEFENSE" in multi
        assert "NASA" in multi

    def test_no_risk_for_empty_vendor(self, con):
        p = vendor_profile_analytics(con, "Ghost Vendor")
        assert p["risk"]["expiring_soon"] == []
        assert p["risk"]["largest_contract"] is None


# ---------------------------------------------------------------------------
# vendor_profile_analytics — related vendors
# ---------------------------------------------------------------------------

class TestRelatedVendors:
    def test_related_vendor_found(self, seeded_db, con):
        _contract("B1", "Rival Inc", "DEFENSE", 1_000_000, "HIGH", 70, 200)
        p = vendor_profile_analytics(con, "Acme Corp")
        names = [v["vendor"] for v in p["related_vendors"]]
        assert "Rival Inc" in names

    def test_self_not_in_related(self, profile):
        names = [v["vendor"] for v in profile["related_vendors"]]
        assert "Acme Corp" not in names

    def test_shared_agencies_count(self, seeded_db, con):
        _contract("B2", "Rival Inc", "NASA", 500_000, "LOW", 40, 300)
        p = vendor_profile_analytics(con, "Acme Corp")
        rival = next((v for v in p["related_vendors"] if v["vendor"] == "Rival Inc"), None)
        if rival:
            assert rival["shared_agencies"] >= 1


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------

class TestVendorRoute:
    def test_vendor_page_200(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert resp.status_code == 200

    def test_vendor_name_in_response(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Acme Corp" in resp.data

    def test_summary_cards_present(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Pipeline Value" in resp.data
        assert b"Critical Contracts" in resp.data
        assert b"Avg Days Remaining" in resp.data
        assert b"Earliest Expiration" in resp.data

    def test_agency_breakdown_table(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Agency Breakdown" in resp.data
        assert b"DEFENSE" in resp.data
        assert b"NASA" in resp.data

    def test_upcoming_recompetes_table(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Upcoming Recompetes" in resp.data

    def test_timeline_section(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Expiration Timeline" in resp.data

    def test_risk_banner_shown(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Risk Indicators" in resp.data

    def test_chart_canvases_rendered(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"chartAgency" in resp.data
        assert b"chartPriority" in resp.data
        assert b"chartMonthly" in resp.data

    def test_chartjs_script_included(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"chart.js" in resp.data

    def test_related_vendors_link(self, client, seeded_db):
        _contract("R1", "Rival Inc", "DEFENSE", 1_000_000, "HIGH", 70, 200)
        resp = client.get("/vendor/Acme%20Corp")
        assert b"Related Vendors" in resp.data

    def test_unknown_vendor_shows_zero(self, client, seeded_db):
        resp = client.get("/vendor/No%20Such%20Vendor")
        assert resp.status_code == 200
        assert b"0 active" in resp.data

    def test_contract_detail_links(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"/contract/A1" in resp.data

    def test_agency_links(self, client, seeded_db):
        resp = client.get("/vendor/Acme%20Corp")
        assert b"/agency/" in resp.data

    def test_no_risk_banner_when_safe(self, client, tmp_db):
        _contract("S1", "Safe Corp", "DOT", 100_000, "LOW", 10, 500, "2028-01-01")
        resp = client.get("/vendor/Safe%20Corp")
        assert b"Risk Indicators" not in resp.data
