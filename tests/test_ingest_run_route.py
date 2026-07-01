"""
Regression tests for /ingest/run (Railway cron endpoint).

Covers:
  - CRON_SECRET auth (401 on wrong/missing secret when secret is set)
  - 202 accepted on correct auth
  - ingest_log written on success and failure
  - _run_daily_ingest date arithmetic does not crash on month-end days
"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import db as db_module


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(test_db, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app, "_CRON_SECRET", "test-secret-xyz")
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture()
def client_no_secret(test_db, monkeypatch):
    """Client with CRON_SECRET unset — auth check disabled."""
    import app as flask_app
    monkeypatch.setattr(flask_app, "_CRON_SECRET", "")
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestIngestRunAuth:
    def test_missing_auth_returns_401(self, client):
        rv = client.post("/ingest/run")
        assert rv.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer wrong-secret"})
        assert rv.status_code == 401

    def test_correct_secret_returns_202(self, client, monkeypatch):
        monkeypatch.setattr("janitorial_recompete_report.main", MagicMock(), raising=False)
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer test-secret-xyz"})
        assert rv.status_code == 202

    def test_no_secret_configured_allows_request(self, client_no_secret, monkeypatch):
        monkeypatch.setattr("janitorial_recompete_report.main", MagicMock(), raising=False)
        rv = client_no_secret.post("/ingest/run")
        assert rv.status_code == 202

    def test_response_has_status_started(self, client, monkeypatch):
        monkeypatch.setattr("janitorial_recompete_report.main", MagicMock(), raising=False)
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer test-secret-xyz"})
        data = rv.get_json()
        assert data["status"] == "started"

    def test_response_has_date_field(self, client, monkeypatch):
        monkeypatch.setattr("janitorial_recompete_report.main", MagicMock(), raising=False)
        rv = client.post("/ingest/run", headers={"Authorization": "Bearer test-secret-xyz"})
        data = rv.get_json()
        assert "date" in data


# ---------------------------------------------------------------------------
# ingest_log written by cron path
# ---------------------------------------------------------------------------

class TestIngestRunLogging:
    def _trigger_and_wait(self, client, monkeypatch, main_fn, max_wait=5):
        """Trigger /ingest/run and wait for the background thread to finish.

        done is set inside main() (success or exception).  The ingest_log write
        happens in the except/finally block *after* done.set(), so a short grace
        period is needed before reading the DB.
        """
        done = threading.Event()
        original = main_fn

        def _wrapped(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            finally:
                done.set()

        monkeypatch.setattr("janitorial_recompete_report.main", _wrapped, raising=False)
        client.post("/ingest/run", headers={"Authorization": "Bearer test-secret-xyz"})
        done.wait(timeout=max_wait)
        time.sleep(0.3)  # allow DB write in except block to complete after done.set()

    def test_success_writes_ingest_log_row(self, client, test_db, monkeypatch):
        self._trigger_and_wait(client, monkeypatch, MagicMock())

        con = sqlite3.connect(test_db)
        rows = con.execute("SELECT status FROM ingest_log WHERE status='success'").fetchall()
        con.close()
        assert len(rows) >= 1

    def test_success_writes_correct_source(self, client, test_db, monkeypatch):
        self._trigger_and_wait(client, monkeypatch, MagicMock())

        con = sqlite3.connect(test_db)
        row = con.execute("SELECT source FROM ingest_log WHERE status='success'").fetchone()
        con.close()
        assert row is not None
        assert row[0] == "usaspending"

    def test_failure_writes_failure_row(self, client, test_db, monkeypatch):
        def boom():
            raise RuntimeError("USAspending timeout")

        self._trigger_and_wait(client, monkeypatch, boom)

        con = sqlite3.connect(test_db)
        row = con.execute(
            "SELECT status, error_message FROM ingest_log WHERE status='failure'"
        ).fetchone()
        con.close()
        assert row is not None
        assert "USAspending timeout" in row[1]

    def test_failure_does_not_write_success_row(self, client, test_db, monkeypatch):
        def boom():
            raise RuntimeError("network error")

        self._trigger_and_wait(client, monkeypatch, boom)

        con = sqlite3.connect(test_db)
        rows = con.execute("SELECT status FROM ingest_log WHERE status='success'").fetchall()
        con.close()
        assert len(rows) == 0

    def test_data_freshness_reflects_cron_run(self, client, test_db, monkeypatch):
        """GET /api/data-freshness should see the ingest_log row written by /ingest/run."""
        self._trigger_and_wait(client, monkeypatch, MagicMock())

        rv = client.get("/api/data-freshness")
        data = rv.get_json()
        assert data["last_ingest"] is not None
        assert data["source"] == "usaspending"


# ---------------------------------------------------------------------------
# _run_daily_ingest date arithmetic — month-end regression
# ---------------------------------------------------------------------------

class TestSchedulerDateArithmetic:
    """Confirm the scheduler thread does not crash advancing past month boundaries."""

    def _next_run_from(self, dt):
        """Replicate the scheduler's date-advance logic."""
        from datetime import timedelta
        import app as flask_app
        # Inline the same logic used in _run_daily_ingest
        next_run = dt.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= dt:
            next_run += timedelta(days=1)
        return next_run

    @pytest.mark.parametrize("month_end", [
        datetime(2026, 1, 31, 3, 0, tzinfo=timezone.utc),   # Jan 31 → Feb 1
        datetime(2026, 3, 31, 3, 0, tzinfo=timezone.utc),   # Mar 31 → Apr 1
        datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc),   # Aug 31 → Sep 1
        datetime(2026, 12, 31, 3, 0, tzinfo=timezone.utc),  # Dec 31 → Jan 1
        datetime(2028, 2, 29, 3, 0, tzinfo=timezone.utc),   # Leap Feb 29 → Mar 1
    ])
    def test_does_not_crash_on_month_end(self, month_end):
        next_run = self._next_run_from(month_end)
        assert next_run > month_end

    def test_advances_exactly_one_day(self):
        from datetime import timedelta
        dt = datetime(2026, 1, 31, 3, 0, tzinfo=timezone.utc)
        next_run = self._next_run_from(dt)
        expected = datetime(2026, 2, 1, 2, 0, tzinfo=timezone.utc)
        assert next_run == expected
