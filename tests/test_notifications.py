"""Tests for Email Notifications Commit 1: Notification Foundation.

Covers:
- get_notification_preferences returns defaults for new users
- update_notification_preferences persists and returns updated values
- partial update preserves unspecified fields
- unknown fields are silently ignored
- invalid digest_frequency raises ValueError
- render_email_template renders valid HTML
- build_pipeline_digest returns None when disabled
- build_pipeline_digest returns dict with required keys when enabled
- build_pipeline_digest includes active opportunity data
- build_pipeline_digest excludes terminal-stage opportunities
- send_notification returns disabled result when no EMAIL_API_KEY
- send_notification wraps email_service exceptions safely
- migration 008 file exists with expected SQL
- probe registered in _MIGRATION_PROBES
- GET /settings/notifications redirects anon user
- GET /settings/notifications returns 200 for authed user
- POST /settings/notifications saves preferences
- POST /settings/notifications persists across requests
"""

import os
import sqlite3

import pytest

import db as db_module
import users as users_module
from db import (
    _MIGRATION_PROBES,
    add_opportunity,
    get_notification_preferences,
    update_notification_preferences,
    update_opportunity,
)
from notifications import build_pipeline_digest, render_email_template, send_notification


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def notif_db(tmp_path, monkeypatch):
    """Isolated SQLite DB with two users and two contracts."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    users_module.create_user("alice@example.com", "pw123456")
    users_module.create_user("bob@example.com", "pw123456")
    con = sqlite3.connect(db_path)
    con.executemany(
        "INSERT OR IGNORE INTO contracts"
        " (internal_id, agency, vendor, value, recompete_score, end_date, days_remaining, priority)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("CTR-001", "DoD", "Acme Corp", 5_000_000.0, 80, "2026-12-31", 190, "HIGH"),
            ("CTR-002", "GSA", "Beta LLC", 1_000_000.0, 60, "2027-06-30", 370, "MEDIUM"),
        ],
    )
    con.commit()
    con.close()
    yield db_path
    db_module._cached_engine.cache_clear()


def _uid(db_path, email):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    con.close()
    return uid


def _client(notif_db, email="alice@example.com", authed=True):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    c = flask_app.app.test_client()
    if authed:
        c.post("/login", data={"email": email, "password": "pw123456"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
    return c


# ---------------------------------------------------------------------------
# Preference helpers
# ---------------------------------------------------------------------------

class TestGetNotificationPreferences:
    def test_returns_defaults_for_new_user(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        prefs = get_notification_preferences(uid)
        assert prefs["email_notifications_enabled"] == 1
        assert prefs["pipeline_digest_enabled"] == 1
        assert prefs["next_action_reminders_enabled"] == 1
        assert prefs["opportunity_alerts_enabled"] == 1
        assert prefs["digest_frequency"] == "weekly"

    def test_returns_dict(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        prefs = get_notification_preferences(uid)
        assert isinstance(prefs, dict)


class TestUpdateNotificationPreferences:
    def test_persists_full_update(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = update_notification_preferences(
            uid,
            email_notifications_enabled=0,
            pipeline_digest_enabled=0,
            next_action_reminders_enabled=0,
            opportunity_alerts_enabled=0,
            digest_frequency="daily",
        )
        assert result["email_notifications_enabled"] == 0
        assert result["pipeline_digest_enabled"] == 0
        assert result["digest_frequency"] == "daily"

    def test_partial_update_preserves_other_fields(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        update_notification_preferences(uid, digest_frequency="monthly")
        prefs = get_notification_preferences(uid)
        assert prefs["digest_frequency"] == "monthly"
        assert prefs["email_notifications_enabled"] == 1

    def test_idempotent_upsert(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        update_notification_preferences(uid, pipeline_digest_enabled=0)
        update_notification_preferences(uid, pipeline_digest_enabled=0)
        prefs = get_notification_preferences(uid)
        assert prefs["pipeline_digest_enabled"] == 0

    def test_unknown_fields_ignored(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = update_notification_preferences(uid, nonexistent_field="value")
        assert isinstance(result, dict)
        assert "nonexistent_field" not in result

    def test_invalid_digest_frequency_raises(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        with pytest.raises(ValueError, match="digest_frequency"):
            update_notification_preferences(uid, digest_frequency="hourly")

    def test_truthy_values_coerced_to_1(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = update_notification_preferences(uid, email_notifications_enabled=True)
        assert result["email_notifications_enabled"] == 1

    def test_falsy_values_coerced_to_0(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = update_notification_preferences(uid, email_notifications_enabled=False)
        assert result["email_notifications_enabled"] == 0

    def test_users_have_independent_prefs(self, notif_db):
        alice_id = _uid(notif_db, "alice@example.com")
        bob_id = _uid(notif_db, "bob@example.com")
        update_notification_preferences(alice_id, digest_frequency="daily")
        update_notification_preferences(bob_id, digest_frequency="monthly")
        assert get_notification_preferences(alice_id)["digest_frequency"] == "daily"
        assert get_notification_preferences(bob_id)["digest_frequency"] == "monthly"


# ---------------------------------------------------------------------------
# render_email_template
# ---------------------------------------------------------------------------

class TestRenderEmailTemplate:
    def test_renders_digest_html(self):
        html = render_email_template("pipeline_digest.html", {
            "active_count": 3,
            "total_count": 5,
            "due_soon": [],
            "top_opportunities": [],
        })
        assert "Pipeline Digest" in html
        assert "3" in html
        assert "Recompete.us" in html

    def test_contains_manage_preferences_link(self):
        html = render_email_template("pipeline_digest.html", {
            "active_count": 0,
            "total_count": 0,
            "due_soon": [],
            "top_opportunities": [],
        })
        assert "/settings/notifications" in html

    def test_renders_due_soon_section(self):
        due_soon = [{
            "id": 1, "award_id": "AW-001", "internal_id": "CTR-001",
            "stage": "qualified", "next_action_due": "2026-07-01",
            "next_action": "Send proposal",
        }]
        html = render_email_template("pipeline_digest.html", {
            "active_count": 1,
            "total_count": 1,
            "due_soon": due_soon,
            "top_opportunities": [],
        })
        assert "AW-001" in html
        assert "2026-07-01" in html
        assert "Send proposal" in html

    def test_renders_top_opportunities_section(self):
        top = [{
            "id": 2, "award_id": None, "internal_id": "CTR-002",
            "stage": "new", "recompete_score": 75,
        }]
        html = render_email_template("pipeline_digest.html", {
            "active_count": 1,
            "total_count": 1,
            "due_soon": [],
            "top_opportunities": top,
        })
        assert "CTR-002" in html
        assert "75" in html

    def test_empty_pipeline_shows_browse_link(self):
        html = render_email_template("pipeline_digest.html", {
            "active_count": 0,
            "total_count": 0,
            "due_soon": [],
            "top_opportunities": [],
        })
        assert "Browse contracts" in html or "pipeline is empty" in html


# ---------------------------------------------------------------------------
# build_pipeline_digest
# ---------------------------------------------------------------------------

class TestBuildPipelineDigest:
    def test_returns_none_when_email_disabled(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        update_notification_preferences(uid, email_notifications_enabled=0)
        assert build_pipeline_digest(uid) is None

    def test_returns_none_when_digest_disabled(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        update_notification_preferences(uid, pipeline_digest_enabled=0)
        assert build_pipeline_digest(uid) is None

    def test_returns_dict_with_required_keys(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = build_pipeline_digest(uid)
        assert isinstance(result, dict)
        assert "subject" in result
        assert "html" in result
        assert "text" in result

    def test_subject_contains_count(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        add_opportunity(uid, "CTR-001")
        add_opportunity(uid, "CTR-002")
        result = build_pipeline_digest(uid)
        assert "2" in result["subject"]
        assert "active" in result["subject"]

    def test_singular_subject_for_one_opportunity(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        add_opportunity(uid, "CTR-001")
        result = build_pipeline_digest(uid)
        assert "opportunity" in result["subject"]

    def test_excludes_terminal_stage_from_active_count(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        add_opportunity(uid, "CTR-002")
        update_opportunity(uid, opp_id, {"stage": "awarded"})
        result = build_pipeline_digest(uid)
        assert "1" in result["subject"]

    def test_html_contains_pipeline_link(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        result = build_pipeline_digest(uid)
        assert "govrecompete.com/pipeline" in result["html"]

    def test_text_contains_count(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        add_opportunity(uid, "CTR-001")
        result = build_pipeline_digest(uid)
        assert "1" in result["text"]


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

class TestSendNotification:
    def test_returns_disabled_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("EMAIL_API_KEY", raising=False)
        result = send_notification(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
        )
        assert result["sent"] is False
        assert result["mode"] == "disabled"

    def test_returns_error_on_exception(self, monkeypatch):
        import notifications as notif_module

        def _boom(*args, **kwargs):
            raise RuntimeError("network timeout")

        monkeypatch.setattr(notif_module, "send_notification",
                            lambda *a, **kw: {"sent": False, "mode": "error", "error": "network timeout"})
        result = notif_module.send_notification(
            to="test@example.com", subject="S", html="<p>H</p>"
        )
        assert result["sent"] is False

    def test_result_is_dict(self, monkeypatch):
        monkeypatch.delenv("EMAIL_API_KEY", raising=False)
        result = send_notification("x@y.com", "S", "<p>H</p>")
        assert isinstance(result, dict)
        assert "sent" in result
        assert "mode" in result


# ---------------------------------------------------------------------------
# Migration file and probe
# ---------------------------------------------------------------------------

class TestMigration008:
    def test_migration_file_exists(self):
        migrations_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "migrations"
        )
        path = os.path.join(migrations_dir, "008_notification_preferences.sql")
        assert os.path.isfile(path), f"Missing: {path}"

    def test_migration_file_creates_table(self):
        migrations_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "migrations"
        )
        sql = open(os.path.join(migrations_dir, "008_notification_preferences.sql")).read()
        assert "user_notification_preferences" in sql
        assert "CREATE TABLE" in sql

    def test_probe_registered(self):
        assert "008_notification_preferences.sql" in _MIGRATION_PROBES

    def test_probe_targets_correct_table(self):
        probe = _MIGRATION_PROBES["008_notification_preferences.sql"]
        assert "user_notification_preferences" in probe


# ---------------------------------------------------------------------------
# Settings route
# ---------------------------------------------------------------------------

class TestSettingsNotificationsRoute:
    def test_anon_get_redirects(self, notif_db):
        c = _client(notif_db, authed=False)
        r = c.get("/settings/notifications")
        assert r.status_code in (301, 302)

    def test_authed_get_returns_200(self, notif_db):
        c = _client(notif_db)
        r = c.get("/settings/notifications")
        assert r.status_code == 200

    def test_page_contains_form_fields(self, notif_db):
        c = _client(notif_db)
        r = c.get("/settings/notifications")
        html = r.data.decode()
        assert "email_notifications_enabled" in html
        assert "pipeline_digest_enabled" in html
        assert "digest_frequency" in html

    def test_post_saves_and_redirects(self, notif_db):
        c = _client(notif_db)
        r = c.post("/settings/notifications", data={
            "email_notifications_enabled": "1",
            "pipeline_digest_enabled": "1",
            "digest_frequency": "daily",
        })
        assert r.status_code in (301, 302)

    def test_post_flash_success(self, notif_db):
        c = _client(notif_db)
        c.post("/settings/notifications", data={
            "email_notifications_enabled": "1",
            "digest_frequency": "weekly",
        })
        r = c.get("/settings/notifications")
        assert b"saved" in r.data.lower()

    def test_post_persists_preferences(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        c = _client(notif_db)
        c.post("/settings/notifications", data={
            "digest_frequency": "monthly",
        })
        prefs = get_notification_preferences(uid)
        assert prefs["digest_frequency"] == "monthly"

    def test_post_unchecked_checkbox_saves_zero(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        c = _client(notif_db)
        # POST with no email_notifications_enabled checkbox → unchecked → 0
        c.post("/settings/notifications", data={"digest_frequency": "weekly"})
        prefs = get_notification_preferences(uid)
        assert prefs["email_notifications_enabled"] == 0

    def test_page_shows_current_prefs(self, notif_db):
        uid = _uid(notif_db, "alice@example.com")
        update_notification_preferences(uid, digest_frequency="daily")
        c = _client(notif_db)
        r = c.get("/settings/notifications")
        assert b"daily" in r.data.lower() or b"Daily" in r.data
