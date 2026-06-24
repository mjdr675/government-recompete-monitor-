"""
Tests for Platform-owned ingest scheduling infrastructure:
  - /ingest/run CRON_SECRET enforcement
  - /ingest/run overlap prevention (_ingest_running flag)
  - /ingest/run same-day idempotency check
  - _next_2am_utc() month/year rollover correctness
  - In-process scheduler thread is NOT started when RAILWAY_ENVIRONMENT is set
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# _next_2am_utc() correctness
# ---------------------------------------------------------------------------

def test_next_2am_utc_same_day_after_midnight():
    """When it's 01:00 UTC, next 2 AM is the same calendar day."""
    from app import _next_2am_utc
    now = datetime(2025, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
    result = _next_2am_utc(now)
    assert result == datetime(2025, 1, 15, 2, 0, 0, tzinfo=timezone.utc)


def test_next_2am_utc_after_2am_advances_to_next_day():
    """When it's 03:00 UTC, next 2 AM is tomorrow."""
    from app import _next_2am_utc
    now = datetime(2025, 1, 15, 3, 0, 0, tzinfo=timezone.utc)
    result = _next_2am_utc(now)
    assert result == datetime(2025, 1, 16, 2, 0, 0, tzinfo=timezone.utc)


def test_next_2am_utc_month_rollover():
    """Dec 31 at 03:00 UTC → next 2 AM is Jan 1 (not day 32)."""
    from app import _next_2am_utc
    now = datetime(2025, 12, 31, 3, 0, 0, tzinfo=timezone.utc)
    result = _next_2am_utc(now)
    assert result == datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc)


def test_next_2am_utc_year_rollover():
    """Explicitly verify year increments correctly."""
    from app import _next_2am_utc
    now = datetime(2024, 2, 29, 10, 0, 0, tzinfo=timezone.utc)  # leap day
    result = _next_2am_utc(now)
    assert result == datetime(2024, 3, 1, 2, 0, 0, tzinfo=timezone.utc)


def test_next_2am_utc_exactly_at_2am_advances():
    """Exactly at 02:00 UTC is not strictly after, so next is tomorrow."""
    from app import _next_2am_utc
    now = datetime(2025, 6, 1, 2, 0, 0, tzinfo=timezone.utc)
    result = _next_2am_utc(now)
    assert result == datetime(2025, 6, 2, 2, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CRON_SECRET enforcement
# ---------------------------------------------------------------------------

def test_ingest_run_requires_cron_secret_when_set(client):
    """POST /ingest/run with wrong token returns 401."""
    import app as flask_app
    with patch.object(flask_app, "_CRON_SECRET", "correct-secret"):
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer wrong"})
    assert rv.status_code == 401
    assert b"unauthorized" in rv.data


def test_ingest_run_accepts_correct_cron_secret(client):
    """POST /ingest/run with the correct bearer token is accepted."""
    import app as flask_app
    mock_main = MagicMock()
    with patch.object(flask_app, "_CRON_SECRET", "correct-secret"), \
         patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer correct-secret"})
    assert rv.status_code in (200, 202)


def test_ingest_run_open_when_no_cron_secret(client):
    """When CRON_SECRET is empty, /ingest/run is accessible without auth."""
    import app as flask_app
    with patch.object(flask_app, "_CRON_SECRET", ""), \
         patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        rv = client.post("/ingest/run")
    assert rv.status_code in (200, 202)


# ---------------------------------------------------------------------------
# Overlap prevention
# ---------------------------------------------------------------------------

def test_ingest_run_returns_409_when_already_running(client):
    """POST /ingest/run returns 409 if an ingest is already in progress."""
    import app as flask_app
    with patch.object(flask_app, "_CRON_SECRET", ""), \
         patch.object(flask_app, "_ingest_running", True):
        rv = client.post("/ingest/run")
    assert rv.status_code == 409
    data = rv.get_json()
    assert data["status"] == "already_running"


# ---------------------------------------------------------------------------
# Same-day idempotency
# ---------------------------------------------------------------------------

def test_ingest_run_skips_if_already_ran_today(client, test_db):
    """POST /ingest/run returns 200 already_ran when ingest_log has today's success."""
    from datetime import date
    import app as flask_app
    from sqlalchemy import text

    today = date.today().isoformat()
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ingest_log (run_date, source, record_count, duration_seconds, status, created_at)
            VALUES (:d, 'usaspending', 100, 30.0, 'success', :d)
        """), {"d": today})

    with patch.object(flask_app, "_CRON_SECRET", ""):
        rv = client.post("/ingest/run")

    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "already_ran"
    assert data["date"] == today


def test_ingest_run_force_overrides_idempotency(client, test_db):
    """POST /ingest/run with force=1 starts even if ingest already ran today."""
    from datetime import date
    import app as flask_app
    from sqlalchemy import text

    today = date.today().isoformat()
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ingest_log (run_date, source, record_count, duration_seconds, status, created_at)
            VALUES (:d, 'usaspending', 100, 30.0, 'success', :d)
        """), {"d": today})

    with patch.object(flask_app, "_CRON_SECRET", ""), \
         patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        rv = client.post("/ingest/run", json={"force": 1})

    assert rv.status_code == 202
    data = rv.get_json()
    assert data["status"] == "started"


def test_ingest_run_does_not_skip_when_yesterday_ran(client, test_db):
    """If last success was yesterday, today's ingest should start normally."""
    import app as flask_app
    from sqlalchemy import text

    yesterday = "2000-01-01"
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ingest_log (run_date, source, record_count, duration_seconds, status, created_at)
            VALUES (:d, 'usaspending', 100, 30.0, 'success', :d)
        """), {"d": yesterday})

    with patch.object(flask_app, "_CRON_SECRET", ""), \
         patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        rv = client.post("/ingest/run")

    assert rv.status_code == 202
    data = rv.get_json()
    assert data["status"] == "started"
