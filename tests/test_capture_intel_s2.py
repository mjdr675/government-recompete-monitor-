"""Sprint 2 tests: why_now, estimated_solicitation_window, next_action_steps,
confidence_rationale, and enhanced why_it_matters with NAICS/PSC context.
"""
import pytest
from datetime import date, timedelta
from contract_summary import (
    why_now,
    estimated_solicitation_window,
    next_action_steps,
    capture_recommendation,
    why_it_matters,
    incumbent_intelligence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(days=30):
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


def _past(days=10):
    return (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")


def _row(**kw):
    base = {
        "internal_id": "TEST001",
        "recompete_score": 80,
        "priority": "HIGH",
        "days_remaining": 400,
        "competition_type": "FULL AND OPEN COMPETITION",
        "value": 2_500_000,
        "solicitation_id": None,
        "vendor": "Acme Defense LLC",
        "start_date": "2022-01-01",
        "end_date": "2025-01-01",
        "agency": "DEPARTMENT OF DEFENSE",
        "sub_agency": "",
        "description": "IT services and technical support",
        "naics_code": "541512",
        "naics_description": "Computer Systems Design Services",
        "psc_code": "D307",
        "psc_description": "IT and Telecom - Automated Information Systems",
        "recipient_uei": None,
        "cage_code": None,
        "sam_type": "",
        "sam_url": "",
        "sam_due_date": "",
        "place_of_performance_state": "VA",
    }
    base.update(kw)
    return base


# ===========================================================================
# why_now
# ===========================================================================

class TestWhyNow:
    def test_returns_non_empty_string(self):
        s = why_now(_row())
        assert isinstance(s, str) and len(s) > 20

    def test_open_solicitation_with_future_due_date(self):
        s = why_now(_row(
            sam_type="solicitation",
            sam_due_date=_future(20),
        ))
        assert "closes" in s.lower() or "open" in s.lower()
        assert "20 day" in s or "days" in s

    def test_open_solicitation_closing_soon(self):
        s = why_now(_row(
            sam_type="solicitation",
            sam_due_date=_future(3),
        ))
        assert "3 day" in s
        assert "respond now" in s.lower() or "window closes" in s.lower()

    def test_presolicitation_mentions_capability(self):
        s = why_now(_row(sam_type="presolicitation"))
        assert "capability" in s.lower() or "pre-solicitation" in s.lower() or "rfp" in s.lower()

    def test_expired(self):
        s = why_now(_row(days_remaining=-5))
        assert "expired" in s.lower() or "follow-on" in s.lower()

    def test_too_late(self):
        s = why_now(_row(days_remaining=15))
        assert "days" in s.lower()
        assert "follow-on" in s.lower() or "closed" in s.lower() or "shift" in s.lower()

    def test_urgent(self):
        s = why_now(_row(days_remaining=60))
        assert "60 days" in s or "days remain" in s.lower()
        assert "may" in s.lower() or "immediately" in s.lower() or "already" in s.lower()

    def test_active_pursuit(self):
        s = why_now(_row(days_remaining=150))
        assert "150" in s
        assert "60" in s or "30" in s or "day" in s.lower()

    def test_prepare(self):
        s = why_now(_row(days_remaining=220))
        assert "220" in s
        assert "teaming" in s.lower() or "proposal" in s.lower() or "days" in s.lower()

    def test_shape(self):
        s = why_now(_row(days_remaining=320))
        assert "320" in s
        assert "requirements" in s.lower() or "influence" in s.lower() or "solicitation" in s.lower()

    def test_best_window(self):
        s = why_now(_row(days_remaining=400))
        assert "400" in s
        assert "window" in s.lower() or "solicitation" in s.lower()

    def test_best_window_includes_estimated_date(self):
        s = why_now(_row(days_remaining=400))
        # Should mention a rough month/year estimate
        current_year = str(date.today().year)
        next_year = str(date.today().year + 1)
        assert current_year in s or next_year in s

    def test_watch(self):
        s = why_now(_row(days_remaining=700))
        assert "700" in s or "18" in s or "month" in s.lower() or "revisit" in s.lower()

    def test_unknown_days(self):
        s = why_now(_row(days_remaining=None))
        assert "unknown" in s.lower() or "verify" in s.lower()


# ===========================================================================
# estimated_solicitation_window
# ===========================================================================

class TestEstimatedSolicitationWindow:
    def test_returns_required_keys(self):
        r = estimated_solicitation_window(_row())
        for key in ("status", "label", "detail", "urgency"):
            assert key in r

    def test_open_with_future_due_date(self):
        r = estimated_solicitation_window(_row(
            sam_type="solicitation",
            sam_due_date=_future(30),
        ))
        assert r["status"] == "open"
        assert "Open now" in r["label"]
        assert r["urgency"] in ("critical", "high")

    def test_open_with_imminent_due_date_is_critical(self):
        r = estimated_solicitation_window(_row(
            sam_type="solicitation",
            sam_due_date=_future(5),
        ))
        assert r["status"] == "open"
        assert r["urgency"] == "critical"

    def test_open_without_due_date(self):
        r = estimated_solicitation_window(_row(sam_type="solicitation"))
        assert r["status"] == "open"
        assert r["urgency"] == "high"

    def test_presolicitation(self):
        r = estimated_solicitation_window(_row(sam_type="presolicitation"))
        assert r["status"] == "presolicitation"
        assert r["urgency"] == "high"

    def test_sources_sought(self):
        r = estimated_solicitation_window(_row(sam_type="sources sought"))
        assert r["status"] == "presolicitation"

    def test_award_notice(self):
        r = estimated_solicitation_window(_row(sam_type="award notice"))
        assert r["status"] == "awarded"

    def test_expired(self):
        r = estimated_solicitation_window(_row(days_remaining=-1))
        assert r["status"] == "expired"

    def test_too_late(self):
        r = estimated_solicitation_window(_row(days_remaining=15))
        assert r["status"] == "too_late"
        assert r["urgency"] == "none"

    def test_near_90_days_is_critical(self):
        r = estimated_solicitation_window(_row(days_remaining=60))
        assert r["status"] == "near"
        assert r["urgency"] == "critical"

    def test_near_150_days_is_high(self):
        r = estimated_solicitation_window(_row(days_remaining=150))
        assert r["status"] == "near"
        assert r["urgency"] == "high"

    def test_expected_window(self):
        r = estimated_solicitation_window(_row(days_remaining=250))
        assert r["status"] == "expected"
        assert "expected" in r["label"].lower()

    def test_best_window_expected(self):
        r = estimated_solicitation_window(_row(days_remaining=400))
        assert r["status"] == "expected"
        assert "expected" in r["label"].lower()

    def test_early_watch_stage(self):
        r = estimated_solicitation_window(_row(days_remaining=700))
        assert r["status"] == "early"
        assert r["urgency"] == "low"

    def test_unknown_days(self):
        r = estimated_solicitation_window(_row(days_remaining=None))
        assert r["status"] == "unknown"
        assert r["urgency"] == "none"

    def test_all_statuses_have_detail(self):
        for days in (None, -1, 15, 60, 150, 250, 400, 700):
            r = estimated_solicitation_window(_row(days_remaining=days))
            assert isinstance(r["detail"], str) and len(r["detail"]) > 5


# ===========================================================================
# next_action_steps
# ===========================================================================

class TestNextActionSteps:
    def test_returns_list(self):
        steps = next_action_steps(_row())
        assert isinstance(steps, list)
        assert len(steps) >= 1

    def test_each_step_has_required_keys(self):
        steps = next_action_steps(_row())
        for step in steps:
            assert "action" in step
            assert "detail" in step
            assert "timeframe" in step
            assert "priority" in step
            assert step["priority"] in ("now", "soon", "later")

    def test_best_window_mentions_agency_engagement(self):
        steps = next_action_steps(_row(days_remaining=400, agency="DEPARTMENT OF DEFENSE"))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "agency" in combined or "department of defense" in combined

    def test_best_window_mentions_incumbent_when_known(self):
        intel = incumbent_intelligence(_row(vendor="Acme Corp"))
        steps = next_action_steps(_row(days_remaining=400), incumbent_intel=intel)
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "acme corp" in combined

    def test_best_window_without_incumbent_suggests_finding_one(self):
        intel = incumbent_intelligence(_row(vendor=""))
        steps = next_action_steps(_row(days_remaining=400, vendor=""), incumbent_intel=intel)
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "incumbent" in combined

    def test_expired_returns_follow_on_search(self):
        steps = next_action_steps(_row(days_remaining=-5))
        assert any("follow-on" in s["action"].lower() or "sam.gov" in s["detail"].lower() for s in steps)

    def test_too_late_returns_steps(self):
        steps = next_action_steps(_row(days_remaining=10))
        assert len(steps) >= 1

    def test_urgent_includes_engagement_caveat(self):
        steps = next_action_steps(_row(days_remaining=60))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "already engaged" in combined or "late" in combined

    def test_active_pursuit_mentions_solicitation(self):
        steps = next_action_steps(_row(days_remaining=150))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "solicitation" in combined or "sam.gov" in combined

    def test_active_pursuit_with_sol_id_references_it(self):
        steps = next_action_steps(_row(days_remaining=150, solicitation_id="SOL-2025-001"))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "sol-2025-001" in combined

    def test_prepare_mentions_proposal(self):
        steps = next_action_steps(_row(days_remaining=220))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "proposal" in combined

    def test_shape_mentions_briefing(self):
        steps = next_action_steps(_row(days_remaining=320))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "briefing" in combined or "capability" in combined or "agency" in combined

    def test_watch_returns_reminder_step(self):
        steps = next_action_steps(_row(days_remaining=700))
        combined = " ".join(s["action"] for s in steps).lower()
        assert "reminder" in combined or "watch" in combined or "revisit" in combined

    def test_watch_step_priority_is_later(self):
        steps = next_action_steps(_row(days_remaining=700))
        assert all(s["priority"] == "later" for s in steps)

    def test_now_priority_steps_in_active_stages(self):
        for days in (150, 220, 320, 400):
            steps = next_action_steps(_row(days_remaining=days))
            assert any(s["priority"] == "now" for s in steps), f"No 'now' step for days={days}"

    def test_sub_agency_used_in_label(self):
        steps = next_action_steps(_row(
            days_remaining=400,
            agency="DEPARTMENT OF DEFENSE",
            sub_agency="DEFENSE HEALTH AGENCY",
        ))
        combined = " ".join(s["action"] + " " + s["detail"] for s in steps).lower()
        assert "defense health agency" in combined

    def test_unknown_timing_returns_verify_step(self):
        steps = next_action_steps(_row(days_remaining=None))
        assert len(steps) >= 1
        combined = " ".join(s["action"] for s in steps).lower()
        assert "verify" in combined or "end date" in combined or "sam.gov" in combined


# ===========================================================================
# confidence_rationale (added to capture_recommendation return)
# ===========================================================================

class TestConfidenceRationale:
    def test_capture_returns_confidence_rationale_key(self):
        r = capture_recommendation(_row())
        assert "confidence_rationale" in r

    def test_confidence_rationale_is_non_empty_string(self):
        r = capture_recommendation(_row())
        assert isinstance(r["confidence_rationale"], str) and len(r["confidence_rationale"]) > 10

    def test_high_confidence_mentions_high(self):
        r = capture_recommendation(_row(
            recompete_score=90,
            days_remaining=400,
            competition_type="FULL AND OPEN COMPETITION",
            value=5_000_000,
        ))
        # If verdict is PURSUE with HIGH confidence, rationale mentions HIGH
        if r["confidence"] == "HIGH":
            assert "HIGH" in r["confidence_rationale"]

    def test_low_confidence_mentions_verify(self):
        r = capture_recommendation(_row(recompete_score=30, days_remaining=400))
        if r["confidence"] == "LOW":
            assert "verify" in r["confidence_rationale"].lower() or "mixed" in r["confidence_rationale"].lower()

    def test_rationale_mentions_verdict(self):
        r = capture_recommendation(_row())
        # Rationale should reference the verdict decision
        assert r["verdict"] in r["confidence_rationale"] or r["confidence"] in r["confidence_rationale"]

    def test_medium_confidence_rationale(self):
        r = capture_recommendation(_row(recompete_score=65, days_remaining=300))
        if r["confidence"] == "MEDIUM":
            assert "MEDIUM" in r["confidence_rationale"]

    def test_pass_verdict_rationale(self):
        r = capture_recommendation(_row(days_remaining=-1))
        assert isinstance(r["confidence_rationale"], str) and len(r["confidence_rationale"]) > 5


# ===========================================================================
# Enhanced why_it_matters with NAICS/PSC context
# ===========================================================================

class TestWhyItMattersEnhanced:
    def test_naics_description_bullet_added(self):
        row = _row(
            naics_code="541512",
            naics_description="Computer Systems Design Services",
        )
        bullets = why_it_matters(row)
        combined = " ".join(bullets)
        assert "541512" in combined
        assert "Computer Systems Design Services" in combined

    def test_naics_description_only_no_code(self):
        row = _row(naics_code="", naics_description="Engineering Services")
        bullets = why_it_matters(row)
        combined = " ".join(bullets)
        assert "Engineering Services" in combined

    def test_psc_description_bullet_added(self):
        row = _row(psc_description="IT and Telecom - Automated Information Systems")
        bullets = why_it_matters(row)
        combined = " ".join(bullets)
        assert "IT and Telecom" in combined

    def test_no_naics_no_extra_bullet(self):
        row = _row(naics_code="", naics_description="")
        bullets = why_it_matters(row)
        combined = " ".join(bullets)
        assert "NAICS" not in combined or "541" not in combined

    def test_no_psc_no_extra_bullet(self):
        row = _row(psc_code="", psc_description="")
        bullets = why_it_matters(row)
        combined = " ".join(bullets)
        assert "Product/service" not in combined

    def test_still_returns_core_bullets(self):
        row = _row(
            value=2_000_000,
            recompete_score=80,
            days_remaining=400,
            competition_type="FULL AND OPEN COMPETITION",
        )
        bullets = why_it_matters(row)
        combined = " ".join(bullets).lower()
        # Core bullets should still be present
        assert "best pursuit" in combined or "ideal" in combined or "window" in combined
        assert "full and open" in combined or "recompete" in combined

    def test_always_returns_at_least_one_bullet(self):
        row = {"internal_id": "X"}
        bullets = why_it_matters(row)
        assert len(bullets) >= 1
