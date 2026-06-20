"""Unit tests for analytics.py — opportunity_recommendations and dashboard_analytics."""

import sqlite3
import pytest
import db as db_module
from analytics import opportunity_recommendations, dashboard_analytics, vendor_profile_analytics, agency_profile


@pytest.fixture()
def con(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    c = db_module.connect()
    yield c
    c.close()


def _insert(c, internal_id, vendor, agency, value, priority, recompete_score, days_remaining):
    c.execute(
        "INSERT INTO contracts "
        "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (internal_id, f"AW-{internal_id}", vendor, agency, value,
         "2027-01-01", priority, recompete_score, days_remaining),
    )
    c.commit()


# ---------------------------------------------------------------------------
# opportunity_recommendations
# ---------------------------------------------------------------------------

def test_recommendations_returns_list(con):
    result = opportunity_recommendations(con)
    assert isinstance(result, list)


def test_recommendations_empty_db_returns_empty(con):
    result = opportunity_recommendations(con)
    assert result == []


def test_recommendations_each_entry_has_reason(con):
    _insert(con, "R1", "Alpha", "DOD", 1_000_000, "HIGH", 85, 60)
    result = opportunity_recommendations(con)
    assert len(result) > 0
    for r in result:
        assert "reason" in r
        assert r["reason"]


def test_recommendations_top_score_reason(con):
    _insert(con, "R1", "TopScore", "DOD", 500_000, "HIGH", 95, 60)
    _insert(con, "R2", "LowScore", "DHS", 500_000, "HIGH", 10, 60)
    result = opportunity_recommendations(con)
    reasons = [r["reason"] for r in result]
    assert any("score" in reason.lower() for reason in reasons)
    top = result[0]
    assert top["vendor"] == "TopScore"


def test_recommendations_highest_value_reason(con):
    _insert(con, "R1", "Cheap", "DOD", 100_000, "LOW", 50, 60)
    _insert(con, "R2", "Expensive", "DOD", 9_000_000, "HIGH", 50, 60)
    result = opportunity_recommendations(con)
    reasons = [r["reason"] for r in result]
    assert any("value" in reason.lower() or "Highest" in reason for reason in reasons)


def test_recommendations_soonest_expiration_reason(con):
    # Fill top-score and top-value slots so SoonExpire only qualifies via expiration
    _insert(con, "S1", "HighScore1", "DOD", 9_000_000, "HIGH", 95, 200)
    _insert(con, "S2", "HighScore2", "DOD", 8_000_000, "HIGH", 90, 200)
    _insert(con, "S3", "HighScore3", "DOD", 7_000_000, "HIGH", 85, 200)
    _insert(con, "R1", "SoonExpire", "DOD", 100_000, "LOW", 10, 5)
    result = opportunity_recommendations(con)
    reasons = [r["reason"] for r in result]
    assert any("Expiring" in reason for reason in reasons)
    assert any(r["vendor"] == "SoonExpire" and "Expiring" in r["reason"] for r in result)


def test_recommendations_critical_priority_reason(con):
    # Fill top-score, top-value, soonest-expiration slots so CritVendor only qualifies via priority
    _insert(con, "S1", "HighScore1", "DOD", 9_000_000, "HIGH", 95, 300)
    _insert(con, "S2", "HighScore2", "DOD", 8_000_000, "HIGH", 90, 300)
    _insert(con, "S3", "HighScore3", "DOD", 7_000_000, "HIGH", 85, 300)
    _insert(con, "R1", "CritVendor", "NSA", 200_000, "CRITICAL", 40, 500)
    result = opportunity_recommendations(con)
    reasons = [r["reason"] for r in result]
    assert any("Critical" in reason for reason in reasons)
    assert any(r["vendor"] == "CritVendor" and "Critical" in r["reason"] for r in result)


def test_recommendations_no_duplicates(con):
    _insert(con, "R1", "TopAll", "DOD", 9_999_999, "CRITICAL", 99, 1)
    result = opportunity_recommendations(con)
    ids = [r["internal_id"] for r in result]
    assert len(ids) == len(set(ids))


def test_recommendations_excludes_inactive_contracts(con):
    _insert(con, "R1", "Dead", "DOD", 9_999_999, "CRITICAL", 99, -10)
    _insert(con, "R2", "NoDay", "DHS", 9_000_000, "CRITICAL", 95, None)
    result = opportunity_recommendations(con)
    vendors = [r["vendor"] for r in result]
    assert "Dead" not in vendors


def test_recommendations_no_crash_without_changes_table(con):
    # Drop changes table to simulate fresh DB with no changes
    con.execute("DROP TABLE IF EXISTS changes")
    con.commit()
    _insert(con, "R1", "Alpha", "DOD", 500_000, "HIGH", 80, 30)
    result = opportunity_recommendations(con)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# dashboard_analytics
# ---------------------------------------------------------------------------

def test_dashboard_analytics_returns_expected_keys(con):
    result = dashboard_analytics()
    assert "platform" in result
    assert "upcoming" in result
    assert "critical" in result
    assert "top_agencies" in result
    assert "top_vendors" in result


def test_dashboard_analytics_platform_counts(con):
    _insert(con, "D1", "Alpha", "DOD", 1_000_000, "CRITICAL", 90, 45)
    _insert(con, "D2", "Beta", "DHS", 2_000_000, "HIGH", 70, 120)
    result = dashboard_analytics()
    assert result["platform"]["total_contracts"] == 2
    assert result["platform"]["total_pipeline"] == pytest.approx(3_000_000)
    assert result["platform"]["critical_contracts"] == 1
    assert result["platform"]["active_contracts"] == 2


def test_dashboard_analytics_upcoming_within_90_days(con):
    _insert(con, "D1", "Soon", "DOD", 500_000, "HIGH", 70, 30)
    _insert(con, "D2", "Far", "DHS", 500_000, "HIGH", 70, 200)
    result = dashboard_analytics()
    vendor_names = [r["vendor"] for r in result["upcoming"]]
    assert "Soon" in vendor_names
    assert "Far" not in vendor_names


def test_dashboard_analytics_critical_active_only(con):
    _insert(con, "D1", "CritActive", "DOD", 1_000_000, "CRITICAL", 90, 45)
    _insert(con, "D2", "CritExpired", "DHS", 500_000, "CRITICAL", 80, -5)
    result = dashboard_analytics()
    vendor_names = [r["vendor"] for r in result["critical"]]
    assert "CritActive" in vendor_names
    assert "CritExpired" not in vendor_names


def test_dashboard_analytics_top_agencies_ordered_by_pipeline(con):
    _insert(con, "D1", "V1", "BigAgency", 5_000_000, "HIGH", 70, 100)
    _insert(con, "D2", "V2", "SmallAgency", 100_000, "LOW", 40, 100)
    result = dashboard_analytics()
    agency_names = [r["agency"] for r in result["top_agencies"]]
    assert agency_names[0] == "BigAgency"


# ---------------------------------------------------------------------------
# vendor_profile_analytics
# ---------------------------------------------------------------------------

def test_vendor_profile_returns_expected_keys(con):
    _insert(con, "V1", "AcmeCorp", "DOD", 1_000_000, "HIGH", 80, 60)
    result = vendor_profile_analytics("AcmeCorp")
    for key in ("summary", "agencies", "upcoming", "active", "pipeline_by_priority",
                "score_distribution", "win_loss_summary", "change_events", "timeline"):
        assert key in result


def test_vendor_profile_summary_counts(con):
    _insert(con, "V1", "AcmeCorp", "DOD", 1_000_000, "CRITICAL", 85, 45)
    _insert(con, "V2", "AcmeCorp", "DHS", 500_000, "HIGH", 70, -10)
    result = vendor_profile_analytics("AcmeCorp")
    assert result["summary"]["contracts"] == 2
    assert result["summary"]["active_contracts"] == 1
    assert result["summary"]["critical_contracts"] == 1


def test_vendor_profile_unknown_vendor_returns_empty(con):
    result = vendor_profile_analytics("NoSuchVendor")
    assert result["agencies"] == []
    assert result["upcoming"] == []
    assert result["active"] == []


# ---------------------------------------------------------------------------
# agency_profile
# ---------------------------------------------------------------------------

def test_agency_profile_returns_expected_keys(con):
    _insert(con, "A1", "AcmeCorp", "DOD", 1_000_000, "HIGH", 80, 60)
    result = agency_profile("DOD")
    for key in ("summary", "vendors", "upcoming", "active", "pipeline_by_priority",
                "score_distribution", "win_loss_summary", "change_events", "timeline"):
        assert key in result


def test_agency_profile_summary_counts(con):
    _insert(con, "A1", "Alpha", "DOD", 1_000_000, "CRITICAL", 85, 45)
    _insert(con, "A2", "Beta", "DOD", 500_000, "HIGH", 70, -10)
    result = agency_profile("DOD")
    assert result["summary"]["contracts"] == 2
    assert result["summary"]["active_contracts"] == 1
    assert result["summary"]["critical_contracts"] == 1


def test_agency_profile_unknown_agency_returns_empty(con):
    result = agency_profile("NoSuchAgency")
    assert result["vendors"] == []
    assert result["upcoming"] == []
    assert result["active"] == []
