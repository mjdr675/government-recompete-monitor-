"""Tests for check_watchlist_alerts Celery task (tasks E-3/5/7)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import db as db_module
import users as users_module
from sqlalchemy import text


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def user(db):
    return users_module.create_user("alerts@example.com", "pass123")


def _add_contract(engine, internal_id, days_remaining, vendor="ACME Corp"):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT OR IGNORE INTO contracts
            (internal_id, vendor, agency, value, days_remaining, recompete_score, priority, raw_json, updated_at)
            VALUES (:iid, :vendor, 'DoD', 100000, :days, 50, 'HIGH', '{}', CURRENT_TIMESTAMP)
        """), {"iid": internal_id, "vendor": vendor, "days": days_remaining})


def _add_watchlist(engine, user_id, internal_id):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT OR IGNORE INTO user_watchlist (user_id, internal_id, added_at)
            VALUES (:uid, :iid, CURRENT_TIMESTAMP)
        """), {"uid": user_id, "iid": internal_id})


def _run_task(monkeypatch):
    """Run check_watchlist_alerts with send_email_task mocked out."""
    sent = []

    def fake_delay(to, subject, html_body, text_body=""):
        sent.append({"to": to, "subject": subject})

    import tasks as tasks_module
    monkeypatch.setattr(tasks_module.send_email_task, "delay", fake_delay)
    tasks_module.check_watchlist_alerts()
    return sent


class TestCheckWatchlistAlerts:
    def test_sends_alert_when_contract_expiring(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-001", 15)
        _add_watchlist(engine, user["id"], "contract-001")
        sent = _run_task(monkeypatch)
        assert len(sent) == 1
        assert sent[0]["to"] == "alerts@example.com"
        assert "expiring" in sent[0]["subject"].lower() or "alert" in sent[0]["subject"].lower()

    def test_no_alert_when_no_expiring_contracts(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-far", 365)  # 365 days away
        _add_watchlist(engine, user["id"], "contract-far")
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_deduplication_prevents_repeat_alert(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-dup", 10)
        _add_watchlist(engine, user["id"], "contract-dup")
        # Pre-insert alert_log entry to simulate already-sent
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)
                VALUES (:uid, 'contract-dup', 'expiry', :now)
            """), {"uid": user["id"], "now": now})
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_alert_log_written_after_send(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-log", 5)
        _add_watchlist(engine, user["id"], "contract-log")
        _run_task(monkeypatch)
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT internal_id FROM alert_log WHERE user_id = :uid AND alert_type = 'expiry'"
            ), {"uid": user["id"]}).fetchone()
        assert row is not None
        assert row[0] == "contract-log"

    def test_user_with_alerts_disabled_skipped(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-dis", 10)
        _add_watchlist(engine, user["id"], "contract-dis")
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)
                VALUES (:uid, 30, 0, :now)
            """), {"uid": user["id"], "now": now})
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_custom_expiry_threshold_respected(self, db, user, monkeypatch):
        engine = db_module.get_engine()
        _add_contract(engine, "contract-7d", 7)
        _add_watchlist(engine, user["id"], "contract-7d")
        now = datetime.now(timezone.utc).isoformat()
        # Set threshold to 5 days — contract at 7 days should NOT trigger
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)
                VALUES (:uid, 5, 1, :now)
            """), {"uid": user["id"], "now": now})
        sent = _run_task(monkeypatch)
        assert sent == []
