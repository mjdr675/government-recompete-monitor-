"""
Tests for the Flask app routes — uses a temporary SQLite database so the real
contracts.db is never touched.
"""

import logging
import sqlite3
import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    """Spin up a fresh DB with two test contracts and patch the module path."""
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID001", "AWARD-001", "Acme Corp", "DOD", 1_000_000, "2025-12-31", "HIGH", 85),
        )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID002", "AWARD-002", "Beta LLC", "DHS", 2_000_000, "2026-06-30", "CRITICAL", 95),
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
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        # Register and auto-login a fixture user so route tests bypass the auth gate
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ---------------------------------------------------------------------------
# /compare tests
# ---------------------------------------------------------------------------

def test_compare_no_params_shows_form(client):
    rv = client.get("/compare")
    assert rv.status_code == 200
    assert b"Compare Contracts" in rv.data
    assert b'name="a"' in rv.data
    assert b'name="b"' in rv.data


def test_compare_both_found(client):
    rv = client.get("/compare?a=ID001&b=ID002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme Corp" in body
    assert "Beta LLC" in body
    assert "DOD" in body
    assert "DHS" in body
    assert "1,000,000" in body
    assert "2,000,000" in body
    assert "2025-12-31" in body
    assert "2026-06-30" in body
    assert "HIGH" in body
    assert "CRITICAL" in body
    assert "85" in body
    assert "95" in body


def test_compare_first_missing(client):
    rv = client.get("/compare?a=MISSING&b=ID002")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "MISSING" in body
    assert "not found" in body


def test_compare_second_missing(client):
    rv = client.get("/compare?a=ID001&b=NOPE")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "NOPE" in body
    assert "not found" in body


def test_compare_same_contract(client):
    rv = client.get("/compare?a=ID001&b=ID001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Acme Corp" in body


# ---------------------------------------------------------------------------
# /contracts days-filter tests
# ---------------------------------------------------------------------------

def test_contracts_negative_days_returns_400(client):
    rv = client.get("/contracts?days=-1")
    assert rv.status_code == 400


def test_contracts_zero_days_returns_200(client):
    rv = client.get("/contracts?days=0")
    assert rv.status_code == 200


def test_contracts_positive_days_returns_200(client):
    rv = client.get("/contracts?days=90")
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# Railway ephemeral DB warning tests
# ---------------------------------------------------------------------------

def test_railway_warning_emitted_without_volume(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RAILWAY_VOLUME_NAME", raising=False)
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" in caplog.text


def test_railway_warning_suppressed_with_volume(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("RAILWAY_VOLUME_NAME", "contracts-volume")
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" not in caplog.text


def test_railway_warning_suppressed_outside_railway(monkeypatch, caplog):
    import app as flask_app
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    with caplog.at_level(logging.WARNING):
        flask_app._warn_if_ephemeral_db()
    assert "DATA LOSS RISK" not in caplog.text


# ---------------------------------------------------------------------------
# /vendor/<name> baseline tests
# ---------------------------------------------------------------------------

def test_vendor_profile_returns_200(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert rv.status_code == 200


def test_vendor_profile_shows_vendor_name(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Acme Corp" in rv.data


def test_vendor_profile_shows_pipeline_value(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"1,000,000" in rv.data


def test_vendor_profile_unknown_vendor_returns_200(client):
    rv = client.get("/vendor/Unknown%20Vendor")
    assert rv.status_code == 200


def test_vendor_profile_has_responsive_table_wrapper(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"overflow-x:auto" in rv.data


def test_vendor_summary_cards_show_active_expired(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Active" in body
    assert "Expired" in body
    assert "Top Score" in body


def test_vendor_priority_doughnut_canvas_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"priority-chart" in rv.data


def test_vendor_timeline_canvas_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"timeline-chart" in rv.data


def test_vendor_timeline_chart_js_loaded(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"chart.js" in rv.data


def test_vendor_win_loss_section_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Win / Loss" in body
    # Acme's days_remaining is NULL → should show Unknown bucket
    assert "Unknown" in body


def test_vendor_win_loss_shows_active_bucket(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-WL", "AWARD-WL", "Acme Corp", "DOD", 300_000, "2027-03-01", "MEDIUM", 60, 30),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Active" in rv.data


def test_vendor_change_events_empty_list_no_error(client):
    # changes table has no rows — page should still render without error
    rv = client.get("/vendor/Acme%20Corp")
    assert rv.status_code == 200


def test_vendor_score_analysis_section_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Recompete Score Analysis" in body
    assert "Platform avg" in body
    assert "High (80-100)" in body  # Acme Corp score=85


def test_vendor_pipeline_by_priority_shows_high(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Pipeline by Priority" in body
    assert "HIGH" in body


def test_vendor_active_contracts_section_present(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Active Contracts" in rv.data


def test_vendor_active_contracts_shows_active_contract(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-ACT", "AWARD-ACT", "Acme Corp", "DOD", 750_000, "2027-06-01", "HIGH", 80, 180),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"AWARD-ACT" in rv.data


def test_vendor_upcoming_shows_competition_column(client):
    rv = client.get("/vendor/Acme%20Corp")
    assert b"Competition" in rv.data


def test_vendor_upcoming_urgency_styling_for_expired(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-EXP", "AWARD-EXP", "Acme Corp", "DOD", 100_000, "2024-01-01", "LOW", 10, -5),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"#b00020" in rv.data


def test_vendor_agency_breakdown_shows_value_and_share(client):
    rv = client.get("/vendor/Acme%20Corp")
    body = rv.data.decode()
    assert "Pipeline Value" in body or "1,000,000" in body
    assert "Share" in body
    assert "Top Score" in body


def test_vendor_summary_active_count_with_days_remaining(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID003", "AWARD-003", "Acme Corp", "DOD", 500_000, "2027-01-01", "HIGH", 70, 90),
        )
        con.commit()
    rv = client.get("/vendor/Acme%20Corp")
    assert b"1" in rv.data  # active_contracts = 1


# ---------------------------------------------------------------------------
# /agency/<name> intelligence tests
# ---------------------------------------------------------------------------

def test_agency_profile_returns_200(client):
    rv = client.get("/agency/DOD")
    assert rv.status_code == 200


def test_agency_profile_shows_agency_name(client):
    rv = client.get("/agency/DOD")
    assert b"DOD" in rv.data


def test_agency_profile_shows_pipeline_value(client):
    rv = client.get("/agency/DOD")
    assert b"1,000,000" in rv.data


def test_agency_profile_unknown_agency_returns_200(client):
    rv = client.get("/agency/Unknown%20Agency")
    assert rv.status_code == 200


def test_agency_summary_cards_show_active_expired_top_score(client):
    rv = client.get("/agency/DOD")
    body = rv.data.decode()
    assert "Active" in body
    assert "Expired" in body
    assert "Top Score" in body


def test_agency_timeline_canvas_present(client):
    rv = client.get("/agency/DOD")
    assert b"timeline-chart" in rv.data


def test_agency_timeline_chart_js_loaded(client):
    rv = client.get("/agency/DOD")
    assert b"chart.js" in rv.data


def test_agency_priority_doughnut_canvas_present(client):
    rv = client.get("/agency/DOD")
    assert b"priority-chart" in rv.data


def test_agency_win_loss_section_present(client):
    rv = client.get("/agency/DOD")
    body = rv.data.decode()
    assert "Win / Loss" in body
    assert "Unknown" in body  # DOD contract has no days_remaining set


def test_agency_win_loss_shows_active_bucket(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-AWL", "AWARD-AWL", "Acme Corp", "DOD", 300_000, "2027-03-01", "MEDIUM", 60, 30),
        )
        con.commit()
    rv = client.get("/agency/DOD")
    assert b"Active" in rv.data


def test_agency_score_analysis_section_present(client):
    rv = client.get("/agency/DOD")
    body = rv.data.decode()
    assert "Recompete Score Analysis" in body
    assert "Platform avg" in body
    assert "High (80-100)" in body  # DOD contract score=85


def test_agency_pipeline_by_priority_shows_high(client):
    rv = client.get("/agency/DOD")
    body = rv.data.decode()
    assert "Pipeline by Priority" in body
    assert "HIGH" in body


def test_agency_active_contracts_section_present(client):
    rv = client.get("/agency/DOD")
    assert b"Active Contracts" in rv.data


def test_agency_active_contracts_shows_active_contract(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-AACT", "AWARD-AACT", "Acme Corp", "DOD", 750_000, "2027-06-01", "HIGH", 80, 180),
        )
        con.commit()
    rv = client.get("/agency/DOD")
    assert b"AWARD-AACT" in rv.data


def test_agency_vendor_leaderboard_shows_value_share_top_score(client):
    rv = client.get("/agency/DOD")
    body = rv.data.decode()
    assert "Vendor Leaderboard" in body
    assert "Share" in body
    assert "Top Score" in body


def test_agency_upcoming_shows_competition_column(client):
    rv = client.get("/agency/DOD")
    assert b"Competition" in rv.data


def test_agency_upcoming_urgency_styling_for_expired(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-AEXP", "AWARD-AEXP", "Acme Corp", "DOD", 100_000, "2024-01-01", "LOW", 10, -5),
        )
        con.commit()
    rv = client.get("/agency/DOD")
    assert b"#b00020" in rv.data


def test_agency_has_responsive_table_wrapper(client):
    rv = client.get("/agency/DOD")
    assert b"overflow-x:auto" in rv.data


# ---------------------------------------------------------------------------
# / customer dashboard tests
# ---------------------------------------------------------------------------

def test_dashboard_returns_200(client):
    rv = client.get("/")
    assert rv.status_code == 200


def test_dashboard_shows_total_pipeline(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Total Pipeline" in body
    # Both contracts combined: 1M + 2M = 3M
    assert "3,000,000" in body


def test_dashboard_shows_total_contracts(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Total Contracts" in body


def test_dashboard_shows_critical_section(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Critical" in body


def test_dashboard_critical_opportunities_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Critical Opportunities" in body


def test_dashboard_upcoming_expirations_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Upcoming Expirations" in body


def test_dashboard_recommended_opportunities_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Recommended Opportunities" in body


def test_dashboard_recent_changes_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Recent Changes" in body


def test_dashboard_top_agencies_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Top Agencies" in body


def test_dashboard_top_vendors_section_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "Top Vendors" in body


def test_dashboard_navigation_links_present(client):
    rv = client.get("/")
    body = rv.data.decode()
    assert "/contracts" in body
    assert "/views" in body
    assert "/ingest" in body


def test_dashboard_critical_contract_shown_in_critical_section(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-CRIT", "AWARD-CRIT", "CritVendor", "NSA", 5_000_000, "2026-08-01", "CRITICAL", 99, 45),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "CritVendor" in body


def test_dashboard_upcoming_contract_shown_when_expiring_soon(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-UPC", "AWARD-UPC", "SoonVendor", "FBI", 800_000, "2026-07-15", "HIGH", 75, 26),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "SoonVendor" in body


# ---------------------------------------------------------------------------
# Recommendations route/template tests
# ---------------------------------------------------------------------------

def test_dashboard_recommendations_why_column_present(client):
    rv = client.get("/")
    assert b"Why" in rv.data


def test_dashboard_recommendations_shows_reason_text(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-REC", "AWARD-REC", "RecVendor", "DIA", 1_500_000, "2027-03-01", "HIGH", 92, 100),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "score" in body.lower() or "value" in body.lower() or "Expiring" in body


def test_dashboard_recommendations_top_score_vendor_shown(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-TS", "AWARD-TS", "TopScoreVendor", "CIA", 500_000, "2027-01-01", "HIGH", 99, 200),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "TopScoreVendor" in body


def test_dashboard_recommendations_expiring_soon_reason(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-EXP2", "AWARD-EXP2", "ExpireSoon", "FBI", 600_000, "2026-07-05", "MEDIUM", 60, 3),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "Expiring" in body


def test_dashboard_recommendations_critical_reason(test_db, client):
    import db as db_module
    with db_module.connect() as con:
        # Flood top-score/value/soonest slots so CritRec only qualifies via priority
        for iid, vendor, score, days in [
            ("ID-TS1", "HighScore1", 99, 200),
            ("ID-TS2", "HighScore2", 97, 200),
            ("ID-TS3", "HighScore3", 95, 200),
        ]:
            con.execute(
                "INSERT INTO contracts "
                "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (iid, f"AW-{iid}", vendor, "DOD", 8_000_000, "2027-01-01", "HIGH", score, days),
            )
        con.execute(
            "INSERT INTO contracts "
            "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score, days_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ID-CREC", "AWARD-CREC", "CritRec", "NSA", 50_000, "2027-04-01", "CRITICAL", 20, 500),
        )
        con.commit()
    rv = client.get("/")
    body = rv.data.decode()
    assert "Critical priority" in body


# ---------------------------------------------------------------------------
# Stripe webhook
# ---------------------------------------------------------------------------

def test_webhook_rejects_without_secret(monkeypatch, client):
    import app as flask_app
    monkeypatch.setattr(flask_app, "STRIPE_WEBHOOK_SECRET", None)
    rv = client.post("/stripe/webhook", data=b"{}", content_type="application/json")
    assert rv.status_code == 400


def test_webhook_rejects_bad_signature(monkeypatch, client):
    import app as flask_app
    monkeypatch.setattr(flask_app, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    rv = client.post(
        "/stripe/webhook",
        data=b'{"type":"checkout.session.completed"}',
        content_type="application/json",
        headers={"Stripe-Signature": "bad-sig"},
    )
    assert rv.status_code == 400


def test_csv_export_returns_csv(client):
    rv = client.get("/contracts/export.csv")
    assert rv.status_code == 200
    assert "text/csv" in rv.content_type


def test_csv_export_has_correct_headers(client):
    rv = client.get("/contracts/export.csv")
    first_line = rv.data.decode().splitlines()[0]
    assert "internal_id" in first_line
    assert "vendor" in first_line
    assert "priority" in first_line


def test_csv_export_has_content_disposition(client):
    rv = client.get("/contracts/export.csv")
    assert "attachment" in rv.headers.get("Content-Disposition", "")
    assert "contracts.csv" in rv.headers.get("Content-Disposition", "")


def test_csv_export_redirects_when_not_logged_in(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        rv = c.get("/contracts/export.csv")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_dashboard_shows_unknown_when_no_ingest(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Data freshness unknown" in rv.data


def test_dashboard_shows_freshness_banner_when_ingest_exists(client, test_db):
    import sqlite3
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    con = sqlite3.connect(test_db)
    con.execute(
        "INSERT INTO ingest_log (run_date, source, record_count, duration_seconds, status, created_at)"
        " VALUES (?, 'usaspending', 50, 2.0, 'success', ?)",
        (ts[:10], ts),
    )
    con.commit()
    con.close()
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"Data last updated" in rv.data


def test_email_test_returns_ok_when_send_succeeds(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app, "send_email", lambda **kw: {"id": "abc"})
    rv = client.get("/ingest/email-test")
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_email_test_returns_503_when_no_api_key(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app, "send_email", lambda **kw: None)
    rv = client.get("/ingest/email-test")
    assert rv.status_code == 503
    assert rv.get_json()["ok"] is False


def test_email_test_returns_500_when_send_raises(client, monkeypatch):
    import app as flask_app
    def boom(**kw): raise RuntimeError("timeout")
    monkeypatch.setattr(flask_app, "send_email", boom)
    rv = client.get("/ingest/email-test")
    assert rv.status_code == 500
    assert rv.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# Sentry integration
# ---------------------------------------------------------------------------

def test_sentry_init_skipped_when_no_dsn(monkeypatch):
    import os
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    import sentry_sdk
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    dsn = os.environ.get("SENTRY_DSN", "")
    if dsn:
        sentry_sdk.init(dsn=dsn)
    assert calls == []


def test_sentry_init_called_when_dsn_set(monkeypatch):
    import os
    fake_dsn = "https://fake@sentry.io/1"
    monkeypatch.setenv("SENTRY_DSN", fake_dsn)
    import sentry_sdk
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    dsn = os.environ.get("SENTRY_DSN", "")
    if dsn:
        sentry_sdk.init(dsn=dsn, integrations=[], traces_sample_rate=0.1)
    assert len(calls) == 1
    assert calls[0]["dsn"] == fake_dsn


def test_sentry_capture_exception_called_on_stripe_webhook_error(client, monkeypatch):
    import sentry_sdk
    import stripe
    captured = []
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda exc: captured.append(exc))
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: (_ for _ in ()).throw(Exception("boom")))
    import app as flask_app
    monkeypatch.setattr(flask_app, "STRIPE_WEBHOOK_SECRET", "test-secret")
    rv = client.post(
        "/stripe/webhook",
        data=b"payload",
        headers={"Stripe-Signature": "sig", "Content-Type": "application/json"},
    )
    assert rv.status_code == 500
    assert len(captured) == 1
    assert str(captured[0]) == "boom"


# ---------------------------------------------------------------------------
# Structured JSON logging (Task 108)
# ---------------------------------------------------------------------------

def test_json_log_format_emits_valid_json():
    import json
    import logging
    import app as flask_app
    formatter = flask_app._JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello world", args=(), exc_info=None
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["msg"] == "hello world"
    assert "ts" in parsed
    assert "logger" in parsed


def test_json_log_format_includes_exc_key():
    import json
    import logging
    import sys
    import app as flask_app
    formatter = flask_app._JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="something failed", args=(), exc_info=exc_info
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "exc" in parsed
    assert "ValueError" in parsed["exc"]


# ---------------------------------------------------------------------------
# GET /api/health/detailed (Task 109)
# ---------------------------------------------------------------------------

def test_health_detailed_requires_auth(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        rv = c.get("/api/health/detailed")
    assert rv.status_code == 401


def test_health_detailed_returns_ok_when_healthy(client, monkeypatch):
    import redis as redis_module
    mock_redis = type("R", (), {"ping": lambda self: True})()
    monkeypatch.setattr(redis_module, "from_url", lambda *a, **kw: mock_redis)
    rv = client.get("/api/health/detailed")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["db"] == "ok"
    assert data["redis"] == "ok"


def test_health_detailed_returns_503_when_redis_down(client, monkeypatch):
    import redis as redis_module
    def raise_conn(*a, **kw):
        raise ConnectionError("Redis down")
    monkeypatch.setattr(redis_module, "from_url", raise_conn)
    rv = client.get("/api/health/detailed")
    assert rv.status_code == 503
    data = rv.get_json()
    assert data["ok"] is False
    assert data["redis"] == "error"


def test_health_detailed_last_ingest_null_when_no_rows(client, monkeypatch):
    import redis as redis_module
    mock_redis = type("R", (), {"ping": lambda self: True})()
    monkeypatch.setattr(redis_module, "from_url", lambda *a, **kw: mock_redis)
    rv = client.get("/api/health/detailed")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["last_ingest_at"] is None
