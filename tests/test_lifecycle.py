"""Regression tests for the canonical recompete lifecycle (G1 urgency fix).

Covers:
- Exact bucket boundaries: Too Late / Closing / Pursue / Prepare / Early /
  Long Range / Expired / Unknown.
- "Critical" is a valuable actionable preparation window, never imminent expiry.
- Contracts under 30 days are never Critical, whatever the score/value.
- effective_priority downgrades a stale CRITICAL outside the critical window.
- recompete_report._priority reserves CRITICAL for the critical window.
- dashboard_analytics "Critical Opportunities" hides Too Late / Expired rows.
"""

from datetime import date, timedelta

import pytest

import lifecycle
import recompete_report as rr
import db as db_module


# ── Exact bucket boundaries ──────────────────────────────────────────────────

class TestBuckets:
    @pytest.mark.parametrize("days,expected", [
        (None, "unknown"),
        (-1, "expired"),
        (-100, "expired"),
        (0, "too_late"),
        (4, "too_late"),
        (29, "too_late"),
        (30, "closing"),
        (89, "closing"),
        (90, "pursue"),
        (179, "pursue"),
        (180, "prepare"),
        (364, "prepare"),
        (365, "early"),
        (540, "early"),
        (541, "long_range"),
        (5000, "long_range"),
    ])
    def test_stage_key(self, days, expected):
        assert lifecycle.stage_key(days) == expected

    def test_labels_match_spec(self):
        assert lifecycle.label(500) == "Early"
        assert lifecycle.label(250) == "Prepare"
        assert lifecycle.label(120) == "Pursue"
        assert lifecycle.label(45) == "Closing"
        assert lifecycle.label(10) == "Too Late"
        assert lifecycle.label(-3) == "Expired"
        assert lifecycle.label(900) == "Long Range"

    def test_non_numeric_is_unknown(self):
        assert lifecycle.stage_key("abc") == "unknown"


# ── Critical == valuable actionable window, never imminent expiry ─────────────

class TestCritical:
    def test_4_days_is_too_late_never_critical(self):
        assert lifecycle.stage_key(4) == "too_late"
        assert lifecycle.is_critical(4) is False

    @pytest.mark.parametrize("days", [-5, 0, 4, 15, 29])
    def test_under_30_never_critical(self, days):
        assert lifecycle.is_critical(days) is False

    @pytest.mark.parametrize("days", [30, 89, 90, 179, 180, 364, 365, 540])
    def test_actionable_window_is_critical(self, days):
        # Critical == the actionable window (Closing..Early, 30–540): realistic
        # runway to prepare, not imminent expiry.
        assert lifecycle.is_critical(days) is True

    @pytest.mark.parametrize("days", [541, 900, 5000])
    def test_long_range_not_critical(self, days):
        assert lifecycle.is_critical(days) is False


# ── Hidden-by-default (Too Late / Expired) ───────────────────────────────────

class TestHidden:
    @pytest.mark.parametrize("days", [-10, -1, 0, 15, 29])
    def test_too_late_and_expired_hidden(self, days):
        assert lifecycle.is_hidden_by_default(days) is True

    @pytest.mark.parametrize("days", [30, 90, 365, 541])
    def test_actionable_and_beyond_not_hidden(self, days):
        assert lifecycle.is_hidden_by_default(days) is False


# ── effective_priority display guard ─────────────────────────────────────────

class TestEffectivePriority:
    def test_high_score_cannot_restore_critical_under_30(self):
        # A stale/stored CRITICAL on a 5-day contract must not display Critical.
        assert lifecycle.effective_priority("CRITICAL", 5) == "HIGH"
        assert lifecycle.effective_priority("CRITICAL", 29) == "HIGH"

    def test_critical_kept_in_window(self):
        assert lifecycle.effective_priority("CRITICAL", 200) == "CRITICAL"
        assert lifecycle.effective_priority("CRITICAL", 45) == "CRITICAL"  # Closing still qualifies

    def test_long_range_critical_downgraded(self):
        assert lifecycle.effective_priority("CRITICAL", 900) == "HIGH"

    def test_non_critical_pass_through(self):
        assert lifecycle.effective_priority("HIGH", 5) == "HIGH"
        assert lifecycle.effective_priority("LOW", 500) == "LOW"

    def test_unknown_days_leaves_priority_untouched(self):
        assert lifecycle.effective_priority("CRITICAL", None) == "CRITICAL"


# ── recompete_report._priority reserves CRITICAL for the critical window ──────

class TestPriorityAssignment:
    def test_high_score_short_runway_is_not_critical(self):
        # score 100 but only 10 days left (Too Late) → never CRITICAL.
        assert rr._priority(100, days=10) == "HIGH"
        assert rr._priority(100, days=29) == "HIGH"
        assert rr._priority(100, days=-5) == "HIGH"

    def test_high_score_in_window_is_critical(self):
        assert rr._priority(100, days=30) == "CRITICAL"   # Closing lower edge
        assert rr._priority(100, days=200) == "CRITICAL"
        assert rr._priority(90, days=365) == "CRITICAL"
        assert rr._priority(100, days=540) == "CRITICAL"  # Early upper edge

    def test_long_range_high_score_not_critical(self):
        assert rr._priority(100, days=900) == "HIGH"

    def test_unknown_days_falls_back_to_score_ladder(self):
        assert rr._priority(95, days=None) == "CRITICAL"
        assert rr._priority(80, days=None) == "HIGH"


# ── Dashboard "Critical Opportunities" excludes Too Late / Expired ────────────

@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


def _seed_contract(iid, days, priority="CRITICAL", score=95, value=1_000_000):
    today = date.today()
    db_module.upsert_contract({
        "internal_id": iid,
        "award_id": iid,
        "vendor": f"Vendor {iid}",
        "agency": "DEFENSE",
        "value": value,
        "start_date": "2024-01-01",
        "end_date": (today + timedelta(days=days)).isoformat(),
        "days_remaining": days,
        "priority": priority,
        "recompete_score": score,
        "competition_type": "FULL AND OPEN COMPETITION",
    })


class TestDashboardCriticalExcludesExpired:
    def test_too_late_and_expired_not_in_dashboard_critical(self, test_db):
        import analytics
        _seed_contract("EXPIRED", days=-5)      # expired — hidden
        _seed_contract("TOOLATE", days=10)      # too late — hidden
        _seed_contract("LONGRANGE", days=900)   # long range — not actionable
        _seed_contract("CLOSING", days=45)      # closing — actionable, critical
        _seed_contract("GOOD", days=200)        # prep window — critical
        data = analytics.dashboard_analytics()
        crit_ids = {c["internal_id"] for c in data["critical"]}
        assert "GOOD" in crit_ids
        assert "CLOSING" in crit_ids
        assert "EXPIRED" not in crit_ids
        assert "TOOLATE" not in crit_ids
        assert "LONGRANGE" not in crit_ids

    def test_critical_count_excludes_too_late_and_expired(self, test_db):
        import analytics
        _seed_contract("TOOLATE", days=10)
        _seed_contract("EXPIRED", days=-3)
        _seed_contract("CLOSING", days=45)
        _seed_contract("GOOD", days=200)
        data = analytics.dashboard_analytics()
        # CLOSING (45) + GOOD (200) qualify; TOOLATE + EXPIRED excluded.
        assert data["platform"]["critical_contracts"] == 2
