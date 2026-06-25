"""Tests for Task 065 — Celery ingest task and status endpoint."""

import json
import os
import sentry_sdk
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fix@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ---------------------------------------------------------------------------
# tasks.py — run_ingest registered and scheduled
# ---------------------------------------------------------------------------

class TestRunIngestTask:
    def test_run_ingest_in_beat_schedule(self):
        import tasks as tasks_module
        task_names = [v["task"] for v in tasks_module.tasks.conf.beat_schedule.values()]
        assert "tasks.run_ingest" in task_names

    def test_nightly_schedule_crontab(self):
        import tasks as tasks_module
        from celery.schedules import crontab
        entry = next(
            v for v in tasks_module.tasks.conf.beat_schedule.values()
            if v["task"] == "tasks.run_ingest"
        )
        assert isinstance(entry["schedule"], crontab)

    def test_nightly_schedule_hour_is_2(self):
        import tasks as tasks_module
        entry = next(
            v for v in tasks_module.tasks.conf.beat_schedule.values()
            if v["task"] == "tasks.run_ingest"
        )
        assert entry["schedule"].hour == frozenset([2])

    def test_run_ingest_logs_on_success(self, test_db, caplog, monkeypatch):
        import logging
        import sqlite3
        import tasks as tasks_module

        # Pre-populate enough contracts so the quality-alert threshold is not crossed
        con = sqlite3.connect(test_db)
        for i in range(15):
            con.execute(
                "INSERT OR IGNORE INTO contracts"
                " (internal_id, vendor, agency, value, days_remaining, recompete_score, priority, updated_at)"
                " VALUES (?, 'V', 'A', 0, 0, 0, 'LOW', '2026-01-01')",
                (f"C{i:04d}",),
            )
        con.commit()
        con.close()

        mock_main = MagicMock(return_value=None)
        monkeypatch.setattr(
            "recompete_report.main",
            mock_main,
            raising=False,
        )

        with caplog.at_level(logging.ERROR, logger="tasks"):
            tasks_module.run_ingest.apply()

        assert not any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_run_ingest_writes_running_then_success(self, test_db, monkeypatch):
        import tasks as tasks_module
        from sqlalchemy import text

        mock_main = MagicMock(return_value=None)
        monkeypatch.setattr(
            "recompete_report.main",
            mock_main,
            raising=False,
        )

        tasks_module.run_ingest.apply()

        engine = db_module.get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT task_name, status FROM celery_task_log"
            )).fetchall()

        statuses = {r[1] for r in rows}
        assert "SUCCESS" in statuses

    def test_run_ingest_writes_failure_on_exception(self, test_db, monkeypatch):
        import tasks as tasks_module
        from sqlalchemy import text

        def boom():
            raise RuntimeError("SAM.gov unreachable")

        monkeypatch.setattr(
            "recompete_report.main",
            boom,
            raising=False,
        )

        result = tasks_module.run_ingest.apply()
        # apply() captures exceptions without re-raising; check via result
        assert result.failed()

        engine = db_module.get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT status FROM celery_task_log WHERE status='FAILURE'"
            )).fetchall()
        assert len(rows) >= 1

    def test_run_ingest_calls_main(self, test_db, monkeypatch):
        import tasks as tasks_module

        mock_main = MagicMock(return_value=None)
        monkeypatch.setattr(
            "recompete_report.main",
            mock_main,
            raising=False,
        )

        tasks_module.run_ingest.apply()
        mock_main.assert_called_once()


# ---------------------------------------------------------------------------
# POST /ingest (action=api) → JSON with task_id
# ---------------------------------------------------------------------------

class TestPostIngestApiAction:
    def test_returns_json_with_task_id(self, client):
        mock_job = MagicMock()
        mock_job.id = "abc-123-task"

        with patch("tasks.run_ingest") as mock_task:
            mock_task.delay.return_value = mock_job
            rv = client.post("/ingest", data={"action": "api"})

        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert "task_id" in data
        assert data["task_id"] == "abc-123-task"

    def test_returns_json_content_type(self, client):
        mock_job = MagicMock()
        mock_job.id = "xyz-456"

        with patch("tasks.run_ingest") as mock_task:
            mock_task.delay.return_value = mock_job
            rv = client.post("/ingest", data={"action": "api"})

        assert "application/json" in rv.content_type

    def test_no_subprocess_popen_used(self, client):
        mock_job = MagicMock()
        mock_job.id = "no-popen-task"

        with patch("tasks.run_ingest") as mock_task:
            mock_task.delay.return_value = mock_job
            with patch("subprocess.Popen") as mock_popen:
                client.post("/ingest", data={"action": "api"})
                mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# GET /ingest/status?task_id=<id> → JSON
# ---------------------------------------------------------------------------

class TestGetIngestStatusWithTaskId:
    def _mock_result(self, status, retval=None, failed=False):
        r = MagicMock()
        r.status = status
        r.successful.return_value = (status == "SUCCESS")
        r.failed.return_value = failed
        r.ready.return_value = status in ("SUCCESS", "FAILURE")
        r.result = retval
        return r

    def test_returns_json_for_task_id(self, client):
        mock_result = self._mock_result("PENDING")
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=abc-123")

        assert rv.status_code == 200
        assert "application/json" in rv.content_type

    def test_success_status_returns_100_progress(self, client):
        mock_result = self._mock_result("SUCCESS")
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=abc-123")
        data = json.loads(rv.data)
        assert data["progress"] == 100
        assert data["status"] == "SUCCESS"

    def test_failure_status_returns_0_progress(self, client):
        mock_result = self._mock_result("FAILURE", failed=True)
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=abc-123")
        data = json.loads(rv.data)
        assert data["progress"] == 0
        assert data["status"] == "FAILURE"

    def test_pending_status_returns_50_progress(self, client):
        mock_result = self._mock_result("PENDING")
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=abc-123")
        data = json.loads(rv.data)
        assert data["progress"] == 50

    def test_task_id_echoed_in_response(self, client):
        mock_result = self._mock_result("PENDING")
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=my-task-42")
        data = json.loads(rv.data)
        assert data["task_id"] == "my-task-42"

    def test_returns_200_when_celery_unavailable(self, client):
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.side_effect = Exception("Redis down")
            rv = client.get("/ingest/status?task_id=any-id")
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert data["status"] == "UNKNOWN"

    def test_message_field_present(self, client):
        mock_result = self._mock_result("PENDING")
        with patch("tasks.tasks") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            rv = client.get("/ingest/status?task_id=abc")
        data = json.loads(rv.data)
        assert "message" in data


# ---------------------------------------------------------------------------
# GET /ingest/status (no task_id) — legacy log tail
# ---------------------------------------------------------------------------

class TestGetIngestStatusLegacy:
    def test_no_task_id_returns_text_plain(self, client):
        rv = client.get("/ingest/status")
        assert "text/plain" in rv.content_type

    def test_no_task_id_returns_200(self, client):
        rv = client.get("/ingest/status")
        assert rv.status_code == 200


# ---------------------------------------------------------------------------
# ingest_log table (Task 083)
# ---------------------------------------------------------------------------

class TestIngestLog:
    def test_success_writes_ingest_log_row(self, test_db, monkeypatch):
        import tasks as tasks_module
        from sqlalchemy import text

        monkeypatch.setattr("recompete_report.main", MagicMock(), raising=False)
        tasks_module.run_ingest.apply()

        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT status, source, duration_seconds FROM ingest_log WHERE status='success'"
            )).fetchone()

        assert row is not None
        assert row[0] == "success"
        assert row[1] == "usaspending"
        assert row[2] >= 0

    def test_failure_writes_ingest_log_row_with_error(self, test_db, monkeypatch):
        import tasks as tasks_module
        from sqlalchemy import text

        def boom():
            raise RuntimeError("network timeout")

        monkeypatch.setattr("recompete_report.main", boom, raising=False)
        result = tasks_module.run_ingest.apply()
        assert result.failed()

        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT status, error_message FROM ingest_log WHERE status='failure'"
            )).fetchone()

        assert row is not None
        assert row[0] == "failure"
        assert "network timeout" in row[1]

    def test_ingest_log_table_exists_after_init_db(self, test_db):
        import sqlite3
        con = sqlite3.connect(test_db)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        assert "ingest_log" in tables


# ---------------------------------------------------------------------------
# Data quality alert (Task 093)
# ---------------------------------------------------------------------------

class TestIngestQualityAlert:
    def _insert_contracts(self, test_db, n):
        import sqlite3
        con = sqlite3.connect(test_db)
        for i in range(n):
            con.execute(
                "INSERT OR IGNORE INTO contracts"
                " (internal_id, vendor, agency, value, days_remaining, recompete_score, priority, updated_at)"
                " VALUES (?, 'V', 'A', 0, 0, 0, 'LOW', '2026-01-01')",
                (f"C{i:04d}",),
            )
        con.commit()
        con.close()

    def test_low_record_count_logs_error(self, test_db, monkeypatch, caplog):
        import logging
        import tasks as tasks_module

        self._insert_contracts(test_db, 2)
        monkeypatch.setattr("recompete_report.main", MagicMock(), raising=False)

        with caplog.at_level(logging.ERROR, logger="tasks"):
            tasks_module.run_ingest.apply()

        assert any("suspiciously low record count" in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)

    def test_normal_record_count_no_quality_error(self, test_db, monkeypatch, caplog):
        import logging
        import tasks as tasks_module

        self._insert_contracts(test_db, 15)
        monkeypatch.setattr("recompete_report.main", MagicMock(), raising=False)

        with caplog.at_level(logging.ERROR, logger="tasks"):
            tasks_module.run_ingest.apply()

        assert not any("suspiciously low record count" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Sentry capture_exception in run_ingest (Task 107)
# ---------------------------------------------------------------------------

def test_sentry_capture_called_on_ingest_failure(test_db, monkeypatch):
    import tasks as tasks_module

    def boom():
        raise RuntimeError("SAM.gov unreachable")

    monkeypatch.setattr("recompete_report.main", boom, raising=False)
    captured = []
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda exc: captured.append(exc))

    result = tasks_module.run_ingest.apply()
    assert result.failed()
    assert len(captured) >= 1
    assert isinstance(captured[0], RuntimeError)
