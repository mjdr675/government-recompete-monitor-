"""Tests for Task 063 — Redis provision and Celery skeleton."""

import os
import importlib
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# tasks.py — imports and configuration
# ---------------------------------------------------------------------------

class TestTasksModule:
    def test_imports_without_redis_url(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        import tasks as tasks_module
        assert tasks_module.tasks is not None

    def test_imports_with_redis_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
        import tasks as tasks_module
        assert tasks_module.tasks is not None

    def test_celery_app_name(self):
        import tasks as tasks_module
        assert tasks_module.tasks.main == "recompete"

    def test_task_serializer_is_json(self):
        import tasks as tasks_module
        assert tasks_module.tasks.conf.task_serializer == "json"

    def test_task_acks_late(self):
        import tasks as tasks_module
        assert tasks_module.tasks.conf.task_acks_late is True

    def test_task_reject_on_worker_lost(self):
        import tasks as tasks_module
        assert tasks_module.tasks.conf.task_reject_on_worker_lost is True

    def test_broker_defaults_to_localhost(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        import tasks as tasks_module
        broker_url = str(tasks_module.tasks.conf.broker_url)
        assert "localhost" in broker_url or "redis" in broker_url

    def test_broker_uses_redis_url_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://myhost:6380/2")
        # Reload module to pick up new env var
        import tasks as tasks_module
        importlib.reload(tasks_module)
        broker_url = str(tasks_module.tasks.conf.broker_url)
        assert "myhost" in broker_url or "6380" in broker_url


# ---------------------------------------------------------------------------
# app.py — startup Redis ping is gracefully degraded
# ---------------------------------------------------------------------------

class TestRedisStartupPing:
    def test_app_starts_when_redis_unavailable(self, tmp_path, monkeypatch):
        """App must not raise if Redis PING fails."""
        import db as db_module
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()

        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        mock_redis_module.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            import app as flask_app
            # If we get here without exception, the test passes
            assert flask_app.app is not None

        db_module._cached_engine.cache_clear()

    def test_health_returns_200_without_redis(self, tmp_path, monkeypatch):
        """GET /health must return 200 even when Redis is down."""
        import db as db_module
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()

        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Redis down")
        mock_redis_module.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            import app as flask_app
            flask_app.app.config["TESTING"] = True
            flask_app.app.secret_key = "test-secret"
            with flask_app.app.test_client() as c:
                rv = c.get("/health")
            assert rv.status_code == 200

        db_module._cached_engine.cache_clear()

    def test_check_redis_logs_warning_on_failure(self, caplog, monkeypatch):
        import logging
        import app as flask_app

        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("down")
        mock_redis_module.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            with caplog.at_level(logging.WARNING):
                flask_app._check_redis()

        assert any("Redis" in r.getMessage() or "redis" in r.getMessage().lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# _check_redis — unit tests for the ping helper
# ---------------------------------------------------------------------------

class TestCheckRedisHelper:
    def test_no_exception_on_connection_error(self, monkeypatch):
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = OSError("network error")
        mock_redis_module.from_url.return_value = mock_client

        import app as flask_app
        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            flask_app._check_redis()  # must not raise

    def test_no_exception_on_success(self, monkeypatch):
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.from_url.return_value = mock_client

        import app as flask_app
        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            flask_app._check_redis()  # must not raise

    def test_uses_redis_url_env_var(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://customhost:1234/0")
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.from_url.return_value = mock_client

        import app as flask_app
        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            flask_app._check_redis()

        call_args = mock_redis_module.from_url.call_args
        assert "customhost" in str(call_args) or "1234" in str(call_args)
