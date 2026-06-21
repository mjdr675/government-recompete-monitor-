"""Tests for beat health email alert (Task 110)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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


def _make_redis(health_value=None, alert_sent=False):
    """Build a mock Redis client."""
    store = {}
    if health_value is not None:
        store["beat:health"] = health_value.encode() if isinstance(health_value, str) else health_value
    if alert_sent:
        store["beat:alert_sent"] = b"1"

    r = MagicMock()
    r.get.side_effect = lambda key: store.get(key)
    r.set = MagicMock()
    return r


def test_beat_health_alert_sent_when_stale(test_db, monkeypatch):
    import redis as redis_module
    import tasks as tasks_module

    mock_r = _make_redis(health_value=None)  # key missing → stale
    monkeypatch.setattr(redis_module, "from_url", lambda *a, **kw: mock_r)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")

    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)

    tasks_module.check_beat_health.apply()

    mock_delay.assert_called_once()
    call_kwargs = mock_delay.call_args[1]
    assert call_kwargs["to"] == "admin@example.com"
    assert "Beat scheduler" in call_kwargs["subject"]


def test_beat_health_no_alert_without_admin_email(test_db, monkeypatch):
    import redis as redis_module
    import tasks as tasks_module

    mock_r = _make_redis(health_value=None)
    monkeypatch.setattr(redis_module, "from_url", lambda *a, **kw: mock_r)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)

    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)

    tasks_module.check_beat_health.apply()

    mock_delay.assert_not_called()


def test_beat_health_dedup_prevents_second_email(test_db, monkeypatch):
    import redis as redis_module
    import tasks as tasks_module

    call_count = [0]

    def make_redis(*a, **kw):
        call_count[0] += 1
        # Second call: alert_sent key present
        return _make_redis(health_value=None, alert_sent=(call_count[0] > 1))

    monkeypatch.setattr(redis_module, "from_url", make_redis)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")

    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)

    tasks_module.check_beat_health.apply()
    tasks_module.check_beat_health.apply()

    assert mock_delay.call_count == 1


def test_beat_health_no_alert_when_healthy(test_db, monkeypatch):
    import redis as redis_module
    import tasks as tasks_module

    fresh_ts = datetime.now(timezone.utc).isoformat()
    mock_r = _make_redis(health_value=fresh_ts)
    monkeypatch.setattr(redis_module, "from_url", lambda *a, **kw: mock_r)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")

    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)

    tasks_module.check_beat_health.apply()

    mock_delay.assert_not_called()
