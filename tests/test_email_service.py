"""Tests for email_service.send_email()."""

import logging
import pytest
from unittest.mock import MagicMock, patch
import requests as req_module


def test_returns_none_when_no_api_key(monkeypatch):
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    from email_service import send_email
    result = send_email("u@example.com", "Subject", "<p>Hi</p>")
    assert result is None


def test_logs_warning_when_no_api_key(monkeypatch, caplog):
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    from email_service import send_email
    with caplog.at_level(logging.WARNING, logger="email_service"):
        send_email("u@example.com", "Subject", "<p>Hi</p>")
    assert any("EMAIL_API_KEY not set" in r.getMessage() for r in caplog.records)


def test_calls_resend_api_when_key_set(monkeypatch):
    monkeypatch.setenv("EMAIL_API_KEY", "re_test_key")
    monkeypatch.setenv("SMTP_FROM", "from@example.com")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "abc123"}
    with patch("email_service.requests.post", return_value=mock_resp) as mock_post:
        from email_service import send_email
        result = send_email("to@example.com", "Hello", "<p>Hello</p>", "Hello")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "resend.com/emails" in call_kwargs[0][0]
    assert call_kwargs[1]["headers"]["Authorization"] == "Bearer re_test_key"
    assert call_kwargs[1]["json"]["to"] == ["to@example.com"]
    assert result == {"id": "abc123"}


def test_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("EMAIL_API_KEY", "re_test_key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req_module.HTTPError("422")
    with patch("email_service.requests.post", return_value=mock_resp):
        from email_service import send_email
        with pytest.raises(req_module.HTTPError):
            send_email("u@example.com", "Subject", "<p>Hi</p>")


def test_uses_subject_as_text_fallback(monkeypatch):
    monkeypatch.setenv("EMAIL_API_KEY", "re_test_key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "x"}
    with patch("email_service.requests.post", return_value=mock_resp) as mock_post:
        from email_service import send_email
        send_email("u@example.com", "My Subject", "<p>Hi</p>")
    assert mock_post.call_args[1]["json"]["text"] == "My Subject"
