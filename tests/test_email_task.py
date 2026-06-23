"""Tests for tasks.send_email_task Celery task."""

import pytest
from unittest.mock import MagicMock, patch
import db as db_module


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


def test_send_email_task_is_registered():
    import tasks as tasks_module
    task_names = list(tasks_module.tasks.tasks.keys())
    assert "tasks.send_email_task" in task_names


def test_send_email_task_calls_send_email(test_db, monkeypatch):
    import tasks as tasks_module
    mock_send = MagicMock(return_value={"id": "abc123"})
    monkeypatch.setattr("email_service.send_email", mock_send)
    result = tasks_module.send_email_task.apply(
        args=["to@example.com", "Subject", "<p>Hi</p>", "Hi"]
    )
    assert result.result == {"id": "abc123"}
    mock_send.assert_called_once_with(
        to="to@example.com", subject="Subject",
        html_body="<p>Hi</p>", text_body="Hi"
    )


def test_send_email_task_returns_none_when_no_key(test_db, monkeypatch):
    import tasks as tasks_module
    monkeypatch.setattr("email_service.send_email", lambda **kw: None)
    result = tasks_module.send_email_task.apply(
        args=["to@example.com", "Subject", "<p>Hi</p>"]
    )
    assert result.result is None
    assert not result.failed()
