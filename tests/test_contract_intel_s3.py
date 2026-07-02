"""Sprint 2 (CI-S2) tests: opportunity_highlights, score_rationale_headline,
and improved contract_plain_summary.
"""
import pytest
from datetime import date, timedelta
from contract_summary import (
    opportunity_highlights,
    score_rationale_headline,
    contract_plain_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        "end_date": "2027-01-01",
        "agency": "DEPARTMENT OF DEFENSE",
        "sub_agency": "",
        "description": "IT services and technical support",
        "naics_code": "541512",
        "naics_description": "Computer Systems Design Services",
        "psc_code": "D307",
        "psc_description": "IT and Telecom - Automated Information Systems",
        "sam_type": "",
        "sam_url": "",
        "sam_due_date": "",
        "place_of_performance_state": "VA",
    }
    base.update(kw)
    return base


# ===========================================================================
# opportunity_highlights
# ===========================================================================

class TestOpportunityHighlights:
    def test_returns_list(self):
        result = opportunity_highlights(_row())
        assert isinstance(result, list)

    def test_each_chip_has_required_keys(self):
        chips = opportunity_highlights(_row())
        for chip in chips:
            assert "label" in chip
            assert "value" in chip
            assert "signal" in chip
            assert chip["signal"] in ("positive", "negative", "neutral")

    def test_max_six_chips(self):
        chips = opportunity_highlights(_row())
        assert len(chips) <= 6

    def test_value_chip_present_for_million_dollar_contract(self):
        chips = opportunity_highlights(_row(value=2_500_000))
        labels = [c["label"] for c in chips]
        assert "Value" in labels

    def test_value_chip_uses_m_shorthand(self):
        chips = opportunity_highlights(_row(value=2_500_000))
        val = next(c["value"] for c in chips if c["label"] == "Value")
        assert "M" in val
        assert "$" in val

    def test_large_value_is_positive(self):
        chips = opportunity_highlights(_row(value=10_000_000))
        val_chip = next(c for c in chips if c["label"] == "Value")
        assert val_chip["signal"] == "positive"

    def test_competition_chip_full_open_is_positive(self):
        chips = opportunity_highlights(_row(competition_type="FULL AND OPEN COMPETITION"))
        comp = next((c for c in chips if c["label"] == "Competition"), None)
        assert comp is not None
        assert comp["signal"] == "positive"
        assert "Full" in comp["value"]

    def test_competition_chip_set_aside_is_neutral(self):
        chips = opportunity_highlights(_row(competition_type="SMALL BUSINESS SET ASIDE"))
        comp = next((c for c in chips if c["label"] == "Competition"), None)
        assert comp is not None
        assert comp["signal"] == "neutral"

    def test_timing_chip_best_window_is_positive(self):
        chips = opportunity_highlights(_row(days_remaining=400))
        timing = next((c for c in chips if c["label"] == "Timing"), None)
        assert timing is not None
        assert timing["signal"] == "positive"
        assert "ideal" in timing["value"].lower() or "window" in timing["value"].lower()

    def test_timing_chip_expired_is_negative(self):
        chips = opportunity_highlights(_row(days_remaining=-5))
        timing = next((c for c in chips if c["label"] == "Timing"), None)
        assert timing is not None
        assert timing["signal"] == "negative"

    def test_timing_chip_urgent_is_negative(self):
        chips = opportunity_highlights(_row(days_remaining=50))
        timing = next((c for c in chips if c["label"] == "Timing"), None)
        assert timing is not None
        assert timing["signal"] == "negative"

    def test_industry_chip_from_naics_description(self):
        chips = opportunity_highlights(_row(naics_description="Computer Systems Design Services"))
        ind = next((c for c in chips if c["label"] == "Industry"), None)
        assert ind is not None
        assert "Computer" in ind["value"]

    def test_industry_chip_truncated_if_long(self):
        chips = opportunity_highlights(_row(naics_description="Very Long Industry Description That Exceeds The Limit"))
        ind = next((c for c in chips if c["label"] == "Industry"), None)
        assert ind is not None
        assert len(ind["value"]) <= 32

    def test_location_chip_present_when_state_known(self):
        chips = opportunity_highlights(_row(place_of_performance_state="VA"))
        loc = next((c for c in chips if c["label"] == "Location"), None)
        assert loc is not None
        assert loc["value"] == "VA"

    def test_no_location_chip_when_state_missing(self):
        chips = opportunity_highlights(_row(place_of_performance_state=""))
        labels = [c["label"] for c in chips]
        assert "Location" not in labels

    def test_sam_solicitation_chip_is_positive(self):
        chips = opportunity_highlights(_row(sam_type="solicitation"))
        sam = next((c for c in chips if c["label"] == "SAM.gov"), None)
        assert sam is not None
        assert sam["signal"] == "positive"

    def test_no_value_chip_for_zero_value(self):
        chips = opportunity_highlights(_row(value=0))
        labels = [c["label"] for c in chips]
        assert "Value" not in labels

    def test_empty_row_returns_list(self):
        chips = opportunity_highlights({})
        assert isinstance(chips, list)

    def test_all_signals_are_valid(self):
        for days in (-5, 15, 60, 150, 250, 400, 700):
            chips = opportunity_highlights(_row(days_remaining=days))
            for c in chips:
                assert c["signal"] in ("positive", "negative", "neutral"), \
                    f"Invalid signal '{c['signal']}' for days={days}"


# ===========================================================================
# score_rationale_headline
# ===========================================================================

class TestScoreRationaleHeadline:
    def test_returns_string(self):
        result = score_rationale_headline(_row())
        assert isinstance(result, str)

    def test_non_empty_for_scored_contract(self):
        result = score_rationale_headline(_row(recompete_score=80))
        assert len(result) > 10

    def test_empty_for_unscored_contract(self):
        result = score_rationale_headline(_row(recompete_score=None))
        assert result == ""

    def test_includes_score_number(self):
        result = score_rationale_headline(_row(recompete_score=85))
        assert "85" in result

    def test_mentions_full_open_competition(self):
        result = score_rationale_headline(_row(
            recompete_score=85,
            competition_type="FULL AND OPEN COMPETITION",
        ))
        assert "full and open" in result.lower()

    def test_mentions_dod_agency(self):
        # Remove competition/value/timing so DoD is the primary signal
        result = score_rationale_headline({
            "recompete_score": 85,
            "agency": "DEPARTMENT OF DEFENSE",
            "competition_type": "",
            "value": 0,
            "days_remaining": None,
        })
        assert "DoD" in result or "defense" in result.lower()

    def test_mentions_value_for_large_contract(self):
        result = score_rationale_headline(_row(
            recompete_score=90,
            value=15_000_000,
        ))
        assert "$15M" in result or "15" in result

    def test_mentions_timing_for_best_window(self):
        result = score_rationale_headline(_row(recompete_score=85, days_remaining=400))
        assert "ideal" in result.lower() or "timing" in result.lower() or "recompete" in result.lower()

    def test_fallback_for_no_context(self):
        result = score_rationale_headline({"recompete_score": 75})
        assert "75" in result
        assert len(result) > 10

    def test_high_score_uses_strong_language(self):
        result = score_rationale_headline({"recompete_score": 92})
        assert "strong" in result.lower() or "driven" in result.lower() or "90" in result or "92" in result

    def test_low_score_uses_moderate_language(self):
        result = score_rationale_headline({"recompete_score": 45})
        assert "mixed" in result.lower() or "moderate" in result.lower() or "based on" in result.lower()

    def test_va_agency_mentioned(self):
        result = score_rationale_headline({
            "recompete_score": 80,
            "agency": "DEPARTMENT OF VETERANS AFFAIRS",
            "competition_type": "",
            "value": 0,
            "days_remaining": None,
        })
        assert "VA" in result or "veteran" in result.lower()


# ===========================================================================
# Improved contract_plain_summary
# ===========================================================================

class TestContractPlainSummary:
    def test_returns_non_empty_string(self):
        s = contract_plain_summary(_row())
        assert isinstance(s, str) and len(s) > 20

    def test_includes_vendor_name(self):
        s = contract_plain_summary(_row(vendor="Acme Defense LLC"))
        assert "Acme Defense LLC" in s

    def test_shortens_department_of_prefix(self):
        s = contract_plain_summary(_row(agency="DEPARTMENT OF DEFENSE"))
        assert "Defense" in s
        assert "DEPARTMENT OF DEFENSE" not in s

    def test_shortens_department_of_the_prefix(self):
        s = contract_plain_summary(_row(agency="DEPARTMENT OF THE NAVY"))
        assert "Navy" in s

    def test_uses_m_shorthand_for_large_values(self):
        s = contract_plain_summary(_row(value=2_500_000))
        assert "$2.5M" in s

    def test_mentions_full_and_open(self):
        s = contract_plain_summary(_row(competition_type="FULL AND OPEN COMPETITION"))
        assert "full and open" in s.lower()

    def test_best_window_timing_sentence(self):
        s = contract_plain_summary(_row(days_remaining=400))
        assert "ideal" in s.lower() or "window" in s.lower() or "position" in s.lower()

    def test_expired_timing_sentence(self):
        s = contract_plain_summary(_row(days_remaining=-5))
        assert "expired" in s.lower() or "follow-on" in s.lower()

    def test_urgent_timing_sentence(self):
        s = contract_plain_summary(_row(days_remaining=45))
        assert "45" in s or "late" in s.lower() or "remain" in s.lower()

    def test_open_solicitation_mentioned(self):
        s = contract_plain_summary(_row(sam_type="solicitation", solicitation_id="SOL-2025-001"))
        assert "solicitation" in s.lower()
        assert "SOL-2025-001" in s

    def test_presolicitation_mentioned(self):
        s = contract_plain_summary(_row(sam_type="presolicitation"))
        assert "pre-solicitation" in s.lower()

    def test_naics_description_used_as_work(self):
        s = contract_plain_summary(_row(naics_description="Cybersecurity Services"))
        assert "cybersecurity services" in s.lower()

    def test_falls_back_gracefully_for_sparse_row(self):
        s = contract_plain_summary({"internal_id": "X"})
        assert isinstance(s, str) and len(s) > 0

    def test_no_raw_agency_name_in_output(self):
        s = contract_plain_summary(_row(agency="DEPARTMENT OF HOMELAND SECURITY"))
        assert "Homeland Security" in s

    def test_watch_stage_sentence(self):
        s = contract_plain_summary(_row(days_remaining=700))
        assert "early" in s.lower() or "revisit" in s.lower() or "watch" in s.lower() or "700" in s
