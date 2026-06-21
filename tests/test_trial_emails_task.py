"""Tests for send_trial_emails Celery task (tasks F-10/11/12)."""
import pytest
from datetime import datetime, timedelta, timezone
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
    return users_module.create_user("trial@example.com", "pass123")


def _set_trial_ends_in(user_id, days):
    ends_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET trial_ends_at = :t WHERE id = :id"),
                     {"t": ends_at, "id": user_id})
    return ends_at


def _run_task(monkeypatch):
    sent = []

    def fake_delay(to, subject, html_body, text_body=""):
        sent.append({"to": to, "subject": subject})

    import tasks as tasks_module
    monkeypatch.setattr(tasks_module.send_email_task, "delay", fake_delay)
    tasks_module.send_trial_emails()
    return sent


class TestSendTrialEmails:
    def test_day3_email_sent_when_11_days_remain(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 11)
        sent = _run_task(monkeypatch)
        assert len(sent) == 1
        assert "trial" in sent[0]["subject"].lower() or "making" in sent[0]["subject"].lower()

    def test_day10_email_sent_when_4_days_remain(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 4)
        sent = _run_task(monkeypatch)
        assert len(sent) == 1
        assert "4 days" in sent[0]["subject"].lower() or "ends" in sent[0]["subject"].lower()

    def test_day14_email_sent_when_trial_just_ended(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 0)
        sent = _run_task(monkeypatch)
        assert len(sent) == 1
        assert "ended" in sent[0]["subject"].lower() or "trial" in sent[0]["subject"].lower()

    def test_no_email_when_trial_active_not_at_milestone(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 7)  # 7 days left — no stage matches
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_deduplication_prevents_repeat_day3(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 11)
        engine = db_module.get_engine()
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)
                VALUES (:uid, '', 'trial_day3', :now)
            """), {"uid": user["id"], "now": now})
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_active_subscriber_skipped(self, db, user, monkeypatch):
        _set_trial_ends_in(user["id"], 11)
        users_module.set_subscription(user["id"], "cus_sub", "active")
        sent = _run_task(monkeypatch)
        assert sent == []

    def test_user_without_trial_skipped(self, db, user, monkeypatch):
        # trial_ends_at is NULL (default) — should be skipped
        sent = _run_task(monkeypatch)
        assert sent == []
