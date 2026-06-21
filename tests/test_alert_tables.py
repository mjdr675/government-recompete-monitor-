"""Tests for alert_preferences and alert_log tables (task E-1)."""
import pytest
from datetime import datetime, timezone
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
    return users_module.create_user("alert@example.com", "pass123")


class TestAlertPreferences:
    def test_table_exists(self, db):
        engine = db_module.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_preferences'"
            )).fetchone()
        assert result is not None

    def test_insert_and_retrieve(self, db, user):
        now = datetime.now(timezone.utc).isoformat()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)"
                " VALUES (:uid, :days, 1, :now)"
            ), {"uid": user["id"], "days": 30, "now": now})
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT expiry_days, enabled FROM alert_preferences WHERE user_id = :uid"
            ), {"uid": user["id"]}).fetchone()
        assert row[0] == 30
        assert row[1] == 1

    def test_unique_per_user(self, db, user):
        now = datetime.now(timezone.utc).isoformat()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)"
                " VALUES (:uid, 30, 1, :now)"
            ), {"uid": user["id"], "now": now})
        import pytest as pt
        with pt.raises(Exception):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)"
                    " VALUES (:uid, 60, 1, :now)"
                ), {"uid": user["id"], "now": now})


class TestAlertLog:
    def test_table_exists(self, db):
        engine = db_module.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_log'"
            )).fetchone()
        assert result is not None

    def test_insert_and_retrieve(self, db, user):
        now = datetime.now(timezone.utc).isoformat()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)"
                " VALUES (:uid, 'contract-abc', 'expiry', :now)"
            ), {"uid": user["id"], "now": now})
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT internal_id, alert_type FROM alert_log WHERE user_id = :uid"
            ), {"uid": user["id"]}).fetchone()
        assert row[0] == "contract-abc"
        assert row[1] == "expiry"

    def test_deduplication_unique_constraint(self, db, user):
        now = datetime.now(timezone.utc).isoformat()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)"
                " VALUES (:uid, 'contract-abc', 'expiry', :now)"
            ), {"uid": user["id"], "now": now})
        import pytest as pt
        with pt.raises(Exception):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO alert_log (user_id, internal_id, alert_type, sent_at)"
                    " VALUES (:uid, 'contract-abc', 'expiry', :now)"
                ), {"uid": user["id"], "now": now})
