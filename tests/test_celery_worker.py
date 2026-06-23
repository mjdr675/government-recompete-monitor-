"""Tests for Task 064 — Celery worker, beat scheduler, and heartbeat tasks."""

import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest

import tasks as tasks_module


# ---------------------------------------------------------------------------
# Procfile — worker and beat entries
# ---------------------------------------------------------------------------

class TestProcfile:
    def _content(self):
        path = os.path.join(os.path.dirname(__file__), "..", "Procfile")
        return open(path).read()

    def test_worker_entry_present(self):
        assert "worker:" in self._content()

    def test_beat_entry_present(self):
        assert "beat:" in self._content()

    def test_worker_uses_tasks_app(self):
        content = self._content()
        worker_line = next(l for l in content.splitlines() if l.startswith("worker:"))
        assert "-A tasks" in worker_line

    def test_beat_uses_tasks_app(self):
        content = self._content()
        beat_line = next(l for l in content.splitlines() if l.startswith("beat:"))
        assert "-A tasks" in beat_line

    def test_beat_uses_persistent_scheduler(self):
        content = self._content()
        beat_line = next(l for l in content.splitlines() if l.startswith("beat:"))
        assert "PersistentScheduler" in beat_line


# ---------------------------------------------------------------------------
# Beat schedule registered in tasks.py
# ---------------------------------------------------------------------------

class TestBeatSchedule:
    def test_heartbeat_in_schedule(self):
        schedule = tasks_module.tasks.conf.beat_schedule
        task_names = [v["task"] for v in schedule.values()]
        assert "tasks.heartbeat" in task_names

    def test_check_beat_health_in_schedule(self):
        schedule = tasks_module.tasks.conf.beat_schedule
        task_names = [v["task"] for v in schedule.values()]
        assert "tasks.check_beat_health" in task_names

    def test_heartbeat_interval_is_5_minutes(self):
        schedule = tasks_module.tasks.conf.beat_schedule
        entry = next(v for v in schedule.values() if v["task"] == "tasks.heartbeat")
        assert entry["schedule"] == 300.0

    def test_check_beat_health_interval_is_10_minutes(self):
        schedule = tasks_module.tasks.conf.beat_schedule
        entry = next(v for v in schedule.values() if v["task"] == "tasks.check_beat_health")
        assert entry["schedule"] == 600.0


# ---------------------------------------------------------------------------
# heartbeat task
# ---------------------------------------------------------------------------

class TestHeartbeatTask:
    def _make_mock_redis(self, ping_ok=True):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        if ping_ok:
            mock_client.ping.return_value = True
        else:
            mock_client.ping.side_effect = ConnectionError("down")
        mock_redis_mod.from_url.return_value = mock_client
        return mock_redis_mod, mock_client

    def test_heartbeat_logs_info(self, caplog):
        mock_redis_mod, mock_client = self._make_mock_redis()
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            with caplog.at_level(logging.INFO, logger="tasks"):
                tasks_module.heartbeat()
        assert any("heartbeat" in r.getMessage().lower() for r in caplog.records)

    def test_heartbeat_writes_beat_health_key(self):
        mock_redis_mod, mock_client = self._make_mock_redis()
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            tasks_module.heartbeat()
        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0] == "beat:health"

    def test_heartbeat_sets_ttl_900(self):
        mock_redis_mod, mock_client = self._make_mock_redis()
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            tasks_module.heartbeat()
        call_kwargs = mock_client.set.call_args[1]
        assert call_kwargs.get("ex") == 900

    def test_heartbeat_value_is_iso_timestamp(self):
        mock_redis_mod, mock_client = self._make_mock_redis()
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            tasks_module.heartbeat()
        value = mock_client.set.call_args[0][1]
        # Should be parseable as a datetime
        dt = datetime.fromisoformat(value)
        assert dt is not None

    def test_heartbeat_does_not_raise_on_redis_error(self, caplog):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.set.side_effect = ConnectionError("Redis down")
        mock_redis_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            tasks_module.heartbeat()  # must not raise


# ---------------------------------------------------------------------------
# check_beat_health task
# ---------------------------------------------------------------------------

class TestCheckBeatHealth:
    def _make_redis_with_key(self, value):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        if value is None:
            mock_client.get.return_value = None
        else:
            mock_client.get.return_value = value.encode() if isinstance(value, str) else value
        mock_redis_mod.from_url.return_value = mock_client
        return mock_redis_mod

    def test_no_error_when_key_is_fresh(self, caplog):
        fresh_ts = datetime.now(timezone.utc).isoformat()
        mock_redis_mod = self._make_redis_with_key(fresh_ts)
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            with caplog.at_level(logging.ERROR, logger="tasks"):
                tasks_module.check_beat_health()
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_error_when_key_missing(self, caplog):
        mock_redis_mod = self._make_redis_with_key(None)
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            with caplog.at_level(logging.ERROR, logger="tasks"):
                tasks_module.check_beat_health()
        assert any("missing" in r.getMessage().lower() for r in caplog.records
                   if r.levelno >= logging.ERROR)

    def test_error_when_key_is_stale(self, caplog):
        stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        mock_redis_mod = self._make_redis_with_key(stale_ts)
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            with caplog.at_level(logging.ERROR, logger="tasks"):
                tasks_module.check_beat_health()
        assert any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_no_raise_on_redis_error(self):
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("Redis down")
        mock_redis_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": mock_redis_mod}):
            tasks_module.check_beat_health()  # must not raise


# ---------------------------------------------------------------------------
# celery_task_log table in db
# ---------------------------------------------------------------------------

class TestCeleryTaskLogTable:
    def test_table_created_by_init_db(self, tmp_path, monkeypatch):
        import db as db_module
        from sqlalchemy import inspect
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        eng = db_module.get_engine()
        insp = inspect(eng)
        assert "celery_task_log" in insp.get_table_names()
        db_module._cached_engine.cache_clear()

    def test_table_columns(self, tmp_path, monkeypatch):
        import db as db_module
        from sqlalchemy import inspect
        db_path = str(tmp_path / "tlog.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        eng = db_module.get_engine()
        insp = inspect(eng)
        cols = {c["name"] for c in insp.get_columns("celery_task_log")}
        assert {"id", "task_name", "status", "started_at", "finished_at", "result_json"} <= cols
        db_module._cached_engine.cache_clear()

    def test_celery_task_log_in_migration_file(self):
        path = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql")
        content = open(path).read()
        assert "celery_task_log" in content
