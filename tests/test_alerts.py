"""Tests for Email Alerts — alert body builder and HTTP route."""

from unittest.mock import MagicMock, patch
import pytest

import db as db_module
import alerts as alerts_module
from app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.init_watchlist_table()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.secret_key = "test-secret-key"
    with flask_app.test_client() as c:
        c.post("/register", data={
            "email": "testuser@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


def _seed(internal_id="C1", priority="HIGH", value=500_000):
    db_module.upsert_contract({
        "internal_id": internal_id,
        "vendor": f"Vendor {internal_id}",
        "agency": "TEST AGENCY",
        "value": value,
        "priority": priority,
        "recompete_score": 70,
    })


# ---------------------------------------------------------------------------
# build_alert_body
# ---------------------------------------------------------------------------

class TestBuildAlertBody:
    def test_no_data_returns_no_activity_message(self, tmp_db):
        body = alerts_module.build_alert_body("2026-06-18")
        assert "No watched contracts" in body

    def test_watched_contracts_appear_in_body(self, tmp_db):
        _seed("C1")
        db_module.watch_contract("C1")
        body = alerts_module.build_alert_body("2026-06-18")
        assert "WATCHED CONTRACTS" in body
        assert "Vendor C1" in body

    def test_body_contains_run_date(self, tmp_db):
        body = alerts_module.build_alert_body("2026-01-15")
        assert "2026-01-15" in body

    def test_multiple_watched_contracts(self, tmp_db):
        for i in range(3):
            _seed(f"C{i}")
            db_module.watch_contract(f"C{i}")
        body = alerts_module.build_alert_body("2026-06-18")
        assert "WATCHED CONTRACTS (3)" in body


# ---------------------------------------------------------------------------
# send_alert
# ---------------------------------------------------------------------------

class TestSendAlert:
    def test_skips_when_alert_to_not_set(self, tmp_db, monkeypatch):
        monkeypatch.delenv("ALERT_TO", raising=False)
        result = alerts_module.send_alert("2026-06-18")
        assert result["sent"] is False
        assert "ALERT_TO" in result["reason"]

    def test_sends_when_configured(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALERT_TO", "test@example.com")
        monkeypatch.setenv("SMTP_HOST", "localhost")
        monkeypatch.setenv("SMTP_PORT", "587")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            result = alerts_module.send_alert("2026-06-18")

        assert result["sent"] is True
        mock_smtp.sendmail.assert_called_once()

    def test_returns_false_on_smtp_error(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALERT_TO", "test@example.com")

        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
            result = alerts_module.send_alert("2026-06-18")

        assert result["sent"] is False
        assert "refused" in result["reason"]

    def test_email_subject_contains_date(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALERT_TO", "test@example.com")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            alerts_module.send_alert("2026-06-18")

        call_args = mock_smtp.sendmail.call_args
        raw_message = call_args[0][2]
        assert "2026-06-18" in raw_message

    def test_uses_starttls_when_credentials_provided(self, tmp_db, monkeypatch):
        monkeypatch.setenv("ALERT_TO", "test@example.com")
        monkeypatch.setenv("SMTP_USER", "user@example.com")
        monkeypatch.setenv("SMTP_PASS", "secret")

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            alerts_module.send_alert("2026-06-18")

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------

class TestAlertsRoute:
    def test_alerts_page_loads(self, client):
        resp = client.get("/settings/alerts")
        assert resp.status_code == 200
        assert b"Alert Settings" in resp.data

    def test_alerts_page_shows_config(self, client):
        resp = client.get("/settings/alerts")
        assert b"Enable watchlist expiry alerts" in resp.data
        assert b"expiry_days" in resp.data

    def test_alerts_page_shows_not_configured_warning(self, client, monkeypatch):
        monkeypatch.delenv("ALERT_TO", raising=False)
        resp = client.get("/settings/alerts")
        assert b"expiry_days" in resp.data

    def test_post_send_shows_result(self, client, tmp_db, monkeypatch):
        resp = client.post(
            "/settings/alerts",
            data={"expiry_days": "30", "enabled": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Alert Settings" in resp.data

    def test_post_send_shows_error_when_no_recipient(self, client, monkeypatch):
        monkeypatch.delenv("ALERT_TO", raising=False)
        resp = client.post(
            "/settings/alerts",
            data={"expiry_days": "30"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Alert Settings" in resp.data

    def test_alerts_nav_link_present(self, client):
        resp = client.get("/settings/alerts")
        assert b'href="/settings/alerts"' in resp.data
