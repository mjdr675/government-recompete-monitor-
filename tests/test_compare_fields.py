"""
Tests for NAICS + state fields in the multi-contract compare view
(Contract Intelligence Tools lane).

Verifies the side-by-side compare renders NAICS and state for up to 5
contracts, alongside the existing value/agency/vendor/score/end-date rows.
"""

from unittest.mock import patch, MagicMock
import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "cmp_test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    # Five contracts with distinct NAICS + state values.
    specs = [
        ("CMP1", "AW-1", "Acme Corp", "DOD", 1_000_000, "2026-12-31", "HIGH", 85, "541512", "VA"),
        ("CMP2", "AW-2", "Beta LLC", "DHS", 2_000_000, "2026-06-30", "CRITICAL", 95, "561720", "TX"),
        ("CMP3", "AW-3", "Gamma Inc", "GSA", 500_000, "2027-01-15", "MEDIUM", 70, "238210", "CA"),
        ("CMP4", "AW-4", "Delta Co", "VA", 750_000, "2026-09-01", "HIGH", 80, "561730", "FL"),
        ("CMP5", "AW-5", "Epsilon Ltd", "DOE", 3_000_000, "2027-03-01", "CRITICAL", 92, "541330", "WA"),
    ]
    with db_module.connect() as con:
        for s in specs:
            con.execute(
                "INSERT INTO contracts "
                "(internal_id, award_id, vendor, agency, value, end_date, priority, "
                " recompete_score, naics_code, place_of_performance_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                s,
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
    flask_app.app.secret_key = "cmp-test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=None)
        with patch("tasks.send_email_task", mock_task):
            rv = c.post("/register", data={
                "email": "cmpfields@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        assert rv.status_code in (200, 302)
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


def test_compare_two_shows_naics_and_state(client):
    rv = client.get("/compare?a=CMP1&b=CMP2")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "NAICS" in body
    assert "State" in body
    assert "541512" in body and "561720" in body
    assert "VA" in body and "TX" in body


def test_compare_five_shows_all_naics_and_states(client):
    rv = client.get("/compare?a=CMP1&b=CMP2&c=CMP3&d=CMP4&e=CMP5")
    assert rv.status_code == 200
    body = rv.data.decode()
    for naics in ("541512", "561720", "238210", "561730", "541330"):
        assert naics in body, f"missing NAICS {naics}"
    for state in ("VA", "TX", "CA", "FL", "WA"):
        assert state in body, f"missing state {state}"


def test_compare_still_shows_core_fields(client):
    # NAICS/state are additive — the existing fields must still render.
    rv = client.get("/compare?a=CMP1&b=CMP2")
    body = rv.data.decode()
    assert "Acme Corp" in body and "Beta LLC" in body   # vendor
    assert "DOD" in body and "DHS" in body               # agency
    assert "1,000,000" in body and "2,000,000" in body   # value
    assert "85" in body and "95" in body                 # recompete score
    assert "2026-12-31" in body and "2026-06-30" in body # end date


def test_compare_missing_naics_state_renders_dash(client):
    # A contract without NAICS/state should show the em-dash placeholder.
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts (internal_id, award_id, vendor, agency) "
            "VALUES ('CMP0', 'AW-0', 'NoData Co', 'DOD')"
        )
        con.commit()
    rv = client.get("/compare?a=CMP0&b=CMP1")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "NoData Co" in body
    assert "541512" in body  # CMP1's NAICS still present
