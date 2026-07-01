"""Tests for capture_recommendation, incumbent_intelligence, score_data_confidence,
and contract_plain_summary — the AI Capture Assistant backend functions.
"""
import pytest
from contract_summary import (
    capture_recommendation,
    incumbent_intelligence,
    score_data_confidence,
    contract_plain_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contract(**kw):
    base = {
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
        "description": "IT services and technical support",
        "naics_code": "541512",
        "recipient_uei": "ABC123DEF456",
        "cage_code": "1A2B3",
        "sam_type": "",
        "sam_url": "",
        "sam_due_date": "",
    }
    base.update(kw)
    return base


# ===========================================================================
# capture_recommendation
# ===========================================================================

class TestCaptureVerdicts:
    def test_pursue_high_score_good_timing(self):
        r = capture_recommendation(_contract(recompete_score=85, days_remaining=400))
        assert r["verdict"] == "PURSUE"

    def test_pursue_returns_required_keys(self):
        r = capture_recommendation(_contract())
        assert "verdict" in r
        assert "confidence" in r
        assert "headline" in r
        assert "signals" in r
        assert "caution" in r
        assert r["verdict"] in ("PURSUE", "MONITOR", "PASS")
        assert r["confidence"] in ("HIGH", "MEDIUM", "LOW")

    def test_pass_expired(self):
        r = capture_recommendation(_contract(days_remaining=-5))
        assert r["verdict"] == "PASS"
        assert r["confidence"] == "HIGH"

    def test_pass_too_late(self):
        r = capture_recommendation(_contract(days_remaining=10))
        assert r["verdict"] == "PASS"

    def test_pass_low_score(self):
        r = capture_recommendation(_contract(recompete_score=35, days_remaining=400))
        assert r["verdict"] == "PASS"

    def test_monitor_watch_stage(self):
        r = capture_recommendation(_contract(recompete_score=80, days_remaining=600))
        assert r["verdict"] == "MONITOR"

    def test_monitor_medium_score(self):
        r = capture_recommendation(_contract(recompete_score=60, days_remaining=300))
        assert r["verdict"] == "MONITOR"

    def test_pass_poor_biz_match(self):
        r = capture_recommendation(_contract(), biz_match_score=10)
        assert r["verdict"] == "PASS"

    def test_pursue_good_biz_match(self):
        r = capture_recommendation(_contract(), biz_match_score=75)
        assert r["verdict"] == "PURSUE"

    def test_monitor_low_biz_match_not_pass(self):
        # biz_match 35 reduces confidence but not an outright PASS
        r = capture_recommendation(_contract(), biz_match_score=35)
        assert r["verdict"] in ("MONITOR", "PURSUE")  # not PASS

    def test_no_biz_match_still_works(self):
        r = capture_recommendation(_contract(), biz_match_score=None)
        assert r["verdict"] in ("PURSUE", "MONITOR", "PASS")

    def test_signals_list_non_empty(self):
        r = capture_recommendation(_contract())
        assert len(r["signals"]) >= 3

    def test_signal_positive_types(self):
        r = capture_recommendation(_contract())
        for sig in r["signals"]:
            assert sig["positive"] in (True, False, None)
            assert "label" in sig and "value" in sig

    def test_full_open_competition_positive_signal(self):
        r = capture_recommendation(_contract(competition_type="FULL AND OPEN COMPETITION"))
        comp_signals = [s for s in r["signals"] if "Competition" in s["label"]]
        assert comp_signals
        assert comp_signals[0]["positive"] is True

    def test_limited_competition_not_positive(self):
        r = capture_recommendation(_contract(competition_type="NOT COMPETED"))
        comp_signals = [s for s in r["signals"] if "Competition" in s["label"]]
        assert comp_signals
        assert comp_signals[0]["positive"] is not True

    def test_high_value_positive_signal(self):
        r = capture_recommendation(_contract(value=5_000_000))
        val_signals = [s for s in r["signals"] if "value" in s["label"].lower()]
        assert val_signals
        assert val_signals[0]["positive"] is True

    def test_caution_for_low_score(self):
        r = capture_recommendation(_contract(recompete_score=30))
        # Should have a caution about low score
        assert len(r["caution"]) > 0

    def test_caution_for_poor_biz_match(self):
        r = capture_recommendation(_contract(), biz_match_score=15)
        assert any("match" in c.lower() or "fit" in c.lower() for c in r["caution"])

    def test_solicitation_on_file_is_positive_signal(self):
        r = capture_recommendation(_contract(solicitation_id="SOL-2025-001"))
        sol_signals = [s for s in r["signals"] if "Solicitation" in s["label"]]
        assert sol_signals
        assert sol_signals[0]["positive"] is True

    def test_pursue_high_confidence_when_all_green(self):
        r = capture_recommendation(_contract(
            recompete_score=90,
            days_remaining=400,
            competition_type="FULL AND OPEN COMPETITION",
            value=5_000_000,
        ), biz_match_score=80)
        assert r["verdict"] == "PURSUE"
        assert r["confidence"] in ("HIGH", "MEDIUM")


class TestCaptureHeadlines:
    def test_pass_expired_headline_mentions_follow_on(self):
        r = capture_recommendation(_contract(days_remaining=-1))
        assert "follow-on" in r["headline"].lower() or "cycle" in r["headline"].lower()

    def test_pursue_headline_non_empty(self):
        r = capture_recommendation(_contract())
        assert len(r["headline"]) > 10

    def test_monitor_watch_headline(self):
        r = capture_recommendation(_contract(days_remaining=700))
        assert "early" in r["headline"].lower() or "track" in r["headline"].lower() or "monitor" in r["headline"].lower()


# ===========================================================================
# incumbent_intelligence
# ===========================================================================

class TestIncumbentIntelligence:
    def test_returns_required_keys(self):
        r = incumbent_intelligence(_contract())
        for key in ("name", "has_name", "uei", "cage_code", "hold_months",
                    "hold_label", "displacement_signal", "displacement_label",
                    "displacement_note"):
            assert key in r, f"Missing key: {key}"

    def test_known_vendor_has_name(self):
        r = incumbent_intelligence(_contract(vendor="Acme Corp"))
        assert r["has_name"] is True
        assert r["name"] == "Acme Corp"

    def test_missing_vendor_unknown_signal(self):
        r = incumbent_intelligence(_contract(vendor=""))
        assert r["has_name"] is False
        assert r["displacement_signal"] == "unknown"

    def test_uei_passed_through(self):
        r = incumbent_intelligence(_contract(recipient_uei="XYZ789"))
        assert r["uei"] == "XYZ789"

    def test_hold_months_calculated(self):
        r = incumbent_intelligence(_contract(start_date="2022-01-01", end_date="2024-01-01"))
        assert r["hold_months"] == 24
        assert "2 year" in r["hold_label"]

    def test_hold_months_none_when_dates_missing(self):
        r = incumbent_intelligence(_contract(start_date="", end_date=""))
        assert r["hold_months"] is None

    def test_easy_displacement_open_competition_short(self):
        r = incumbent_intelligence(_contract(
            competition_type="FULL AND OPEN COMPETITION",
            start_date="2023-01-01",
            end_date="2025-01-01",  # 24 months
        ))
        assert r["displacement_signal"] == "easy"

    def test_hard_displacement_long_tenure(self):
        r = incumbent_intelligence(_contract(
            start_date="2019-01-01",
            end_date="2025-01-01",  # 72 months
        ))
        assert r["displacement_signal"] == "hard"

    def test_medium_displacement_default(self):
        r = incumbent_intelligence(_contract(
            competition_type="",
            start_date="2022-01-01",
            end_date="2025-01-01",  # 36 months
        ))
        assert r["displacement_signal"] == "medium"

    def test_displacement_note_mentions_vendor(self):
        r = incumbent_intelligence(_contract(vendor="Defense Corp"))
        assert "Defense Corp" in r["displacement_note"]

    def test_cage_code_passed_through(self):
        r = incumbent_intelligence(_contract(cage_code="9ZZZZ"))
        assert r["cage_code"] == "9ZZZZ"


# ===========================================================================
# score_data_confidence
# ===========================================================================

class TestScoreDataConfidence:
    def test_high_when_all_present(self):
        r = score_data_confidence(_contract())
        assert r["level"] == "HIGH"
        assert r["missing"] == []

    def test_medium_when_one_missing(self):
        c = _contract()
        c["naics_code"] = ""
        r = score_data_confidence(c)
        assert r["level"] == "MEDIUM"
        assert "NAICS code" in r["missing"]

    def test_medium_when_two_missing(self):
        c = _contract()
        c["naics_code"] = ""
        c["vendor"] = None
        r = score_data_confidence(c)
        assert r["level"] == "MEDIUM"
        assert len(r["missing"]) == 2

    def test_low_when_three_or_more_missing(self):
        c = _contract()
        c["naics_code"] = None
        c["vendor"] = None
        c["description"] = ""
        r = score_data_confidence(c)
        assert r["level"] == "LOW"
        assert len(r["missing"]) >= 3

    def test_returns_note(self):
        r = score_data_confidence(_contract())
        assert isinstance(r["note"], str) and len(r["note"]) > 0

    def test_missing_value_is_missing(self):
        c = _contract()
        c["value"] = 0
        r = score_data_confidence(c)
        # value=0 is falsy → counted as missing
        assert "contract value" in r["missing"]


# ===========================================================================
# contract_plain_summary
# ===========================================================================

class TestContractPlainSummary:
    def test_returns_non_empty_string(self):
        s = contract_plain_summary(_contract())
        assert isinstance(s, str) and len(s) > 20

    def test_mentions_agency(self):
        s = contract_plain_summary(_contract(agency="DEPARTMENT OF DEFENSE"))
        assert "DEPARTMENT OF DEFENSE" in s

    def test_mentions_vendor(self):
        s = contract_plain_summary(_contract(vendor="Acme Corp"))
        assert "Acme Corp" in s

    def test_mentions_value(self):
        s = contract_plain_summary(_contract(value=2_500_000))
        assert "2,500,000" in s

    def test_end_date_formatted(self):
        s = contract_plain_summary(_contract(end_date="2025-06-30"))
        assert "June 2025" in s

    def test_competition_type_included(self):
        s = contract_plain_summary(_contract(competition_type="FULL AND OPEN COMPETITION"))
        assert "full and open competition" in s.lower()

    def test_sol_id_included(self):
        s = contract_plain_summary(_contract(solicitation_id="SOL-2025-001"))
        assert "SOL-2025-001" in s

    def test_sparse_record_no_crash(self):
        s = contract_plain_summary({"internal_id": "X"})
        assert isinstance(s, str) and len(s) > 0

    def test_no_vendor_still_returns(self):
        c = _contract()
        c["vendor"] = ""
        s = contract_plain_summary(c)
        assert isinstance(s, str) and len(s) > 0
