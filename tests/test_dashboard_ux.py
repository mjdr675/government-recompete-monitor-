"""Regression tests for the dashboard/contracts UX audit fixes:

- Dashboard sections that display a stored `priority` column directly must
  route it through `lifecycle.effective_priority()` (like contracts.html
  already does) so a stale CRITICAL/HIGH on a near-expired row is never
  displayed — matching the "closed/expired contracts cannot present
  actionable urgency" invariant.
- "Current Awards" is really "awards matched to your company identity" (UEI
  or fuzzy vendor-name match), not a verified ownership registry — renamed to
  "Matched Awards".
- Recommended Opportunities shows a procurement-status badge alongside the
  priority badge so awards and open solicitations are visually distinguishable.
- The Recent Updates empty state gives actionable guidance instead of a bare
  statement.
"""
import sqlite3

import pytest

import db as db_module
from db import save_company_profile, upsert_contract


@pytest.fixture()
def uxdb(tmp_path, monkeypatch):
    db_path = str(tmp_path / "ux_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    import users as users_module
    users_module.create_user("uxtest@example.com", "password123")
    yield db_path


def _uid(db_path):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email = 'uxtest@example.com'").fetchone()[0]
    con.close()
    return uid


@pytest.fixture()
def client(uxdb):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        c.post("/login", data={"email": "uxtest@example.com", "password": "password123"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


class TestMatchedAwardsTitleAndPriorityGuard:
    """"Current Awards" renamed to "Matched Awards"; stale stored priority on
    a near-expired matched contract must display the lifecycle-guarded value.
    """

    def test_heading_renamed_to_matched_awards(self, client, uxdb):
        uid = _uid(uxdb)
        save_company_profile(uid, {"company_name": "Acme Co", "vendor_name": "Acme Corp"})
        upsert_contract({
            "internal_id": "MA1", "award_id": "A1", "vendor": "Acme Corp",
            "agency": "DOD", "value": 1_000_000, "days_remaining": 200,
            "priority": "HIGH", "recompete_score": 50,
        })
        body = client.get("/dashboard").get_data(as_text=True)
        assert "Matched Awards" in body
        assert "Current Awards" not in body

    def test_near_expired_matched_award_never_shows_critical_or_high(self, client, uxdb):
        # Stored priority is stale CRITICAL, but days_remaining=5 is Too Late
        # (hidden_by_default) — effective_priority must downgrade this to LOW
        # wherever it is displayed, per the "awarded/expired contracts cannot
        # present actionable urgency" invariant.
        uid = _uid(uxdb)
        save_company_profile(uid, {"company_name": "Acme Co", "vendor_name": "Acme Corp"})
        upsert_contract({
            "internal_id": "MA2", "award_id": "A2", "vendor": "Acme Corp",
            "agency": "DOD", "value": 1_000_000, "days_remaining": 5,
            "priority": "CRITICAL", "recompete_score": 50,
        })
        body = client.get("/dashboard").get_data(as_text=True)
        assert "priority-low" in body
        assert "priority-critical" not in body


class TestUpcomingExpirationsPriorityGuard:
    def test_near_expired_upcoming_row_never_shows_critical(self, client, uxdb):
        upsert_contract({
            "internal_id": "UE1", "award_id": "A3", "vendor": "Beta LLC",
            "agency": "DHS", "value": 500_000, "days_remaining": 10,
            "priority": "CRITICAL", "recompete_score": 40,
        })
        body = client.get("/dashboard").get_data(as_text=True)
        assert "priority-low" in body
        assert "priority-critical" not in body


class TestRecommendedOpportunitiesBadgeAndPriorityGuard:
    def test_shows_procurement_badge_distinguishing_closed_award(self, client, uxdb):
        # High recompete_score wins it a slot in opportunity_recommendations()
        # via the "Highest recompete score" category regardless of days.
        upsert_contract({
            "internal_id": "RO1", "award_id": "A4", "vendor": "Gamma Inc",
            "agency": "GSA", "value": 2_000_000, "days_remaining": 200,
            "priority": "HIGH", "recompete_score": 99,
        })
        body = client.get("/dashboard").get_data(as_text=True)
        assert "Recommended Opportunities" in body
        assert "proc-badge" in body
        assert 'aria-label="Procurement status: Closed (Awarded)"' in body

    def test_near_expired_recommendation_never_shows_critical(self, client, uxdb):
        upsert_contract({
            "internal_id": "RO2", "award_id": "A5", "vendor": "Delta Co",
            "agency": "VA", "value": 3_000_000, "days_remaining": 3,
            "priority": "CRITICAL", "recompete_score": 98,
        })
        body = client.get("/dashboard").get_data(as_text=True)
        assert "priority-low" in body
        assert "priority-critical" not in body


class TestRecentUpdatesEmptyState:
    def test_empty_state_gives_actionable_guidance(self, client, uxdb):
        body = client.get("/dashboard").get_data(as_text=True)
        assert "Recent Updates" in body
        assert "browse contracts" in body.lower()
