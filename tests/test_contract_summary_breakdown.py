"""Tests for recompete_score_breakdown() in contract_summary.py."""

import pytest
from contract_summary import recompete_score_breakdown


# ── helpers ──────────────────────────────────────────────────────────────────

def _row(**kwargs):
    base = {
        "competition_type": None,
        "value": None,
        "days_remaining": None,
        "agency": None,
        "solicitation_id": None,
        "awarding_office": None,
    }
    base.update(kwargs)
    return base


def _component(breakdown, name):
    return next((c for c in breakdown["components"] if c["name"] == name), None)


# ── None / empty input ───────────────────────────────────────────────────────

class TestNullInput:
    def test_none_row_returns_none(self):
        assert recompete_score_breakdown(None) is None

    def test_empty_dict_returns_breakdown(self):
        result = recompete_score_breakdown({})
        assert result is not None
        assert result["total"] == 0


# ── Competition type component ────────────────────────────────────────────────

class TestCompetitionComponent:
    def test_full_and_open_earns_40(self):
        r = recompete_score_breakdown(_row(competition_type="FULL AND OPEN COMPETITION"))
        c = _component(r, "Competition type")
        assert c["earned"] == 40
        assert c["max"] == 40

    def test_full_and_open_after_exclusion_earns_35(self):
        r = recompete_score_breakdown(_row(competition_type="FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES"))
        c = _component(r, "Competition type")
        assert c["earned"] == 35

    def test_competed_under_sap_earns_30(self):
        r = recompete_score_breakdown(_row(competition_type="COMPETED UNDER SAP"))
        c = _component(r, "Competition type")
        assert c["earned"] == 30

    def test_unknown_competition_type_earns_0(self):
        r = recompete_score_breakdown(_row(competition_type="NOT TO BE COMPETED"))
        c = _component(r, "Competition type")
        assert c["earned"] == 0

    def test_none_competition_type_earns_0(self):
        r = recompete_score_breakdown(_row(competition_type=None))
        c = _component(r, "Competition type")
        assert c["earned"] == 0

    def test_competition_type_case_insensitive(self):
        r = recompete_score_breakdown(_row(competition_type="full and open competition"))
        c = _component(r, "Competition type")
        assert c["earned"] == 40


# ── Value component ───────────────────────────────────────────────────────────

class TestValueComponent:
    def test_10m_plus_earns_35(self):
        r = recompete_score_breakdown(_row(value=10_000_000))
        c = _component(r, "Contract value")
        assert c["earned"] == 35

    def test_5m_earns_25(self):
        r = recompete_score_breakdown(_row(value=5_000_000))
        c = _component(r, "Contract value")
        assert c["earned"] == 25

    def test_2m_earns_15(self):
        r = recompete_score_breakdown(_row(value=2_000_000))
        c = _component(r, "Contract value")
        assert c["earned"] == 15

    def test_1m_earns_10(self):
        r = recompete_score_breakdown(_row(value=1_000_000))
        c = _component(r, "Contract value")
        assert c["earned"] == 10

    def test_below_1m_earns_0(self):
        r = recompete_score_breakdown(_row(value=500_000))
        c = _component(r, "Contract value")
        assert c["earned"] == 0

    def test_none_value_earns_0(self):
        r = recompete_score_breakdown(_row(value=None))
        c = _component(r, "Contract value")
        assert c["earned"] == 0

    def test_zero_value_earns_0(self):
        r = recompete_score_breakdown(_row(value=0))
        c = _component(r, "Contract value")
        assert c["earned"] == 0

    def test_string_value_parsed(self):
        r = recompete_score_breakdown(_row(value="12000000"))
        c = _component(r, "Contract value")
        assert c["earned"] == 35


# ── Timing component ──────────────────────────────────────────────────────────

class TestTimingComponent:
    def test_30_days_or_less_earns_25(self):
        for d in [0, 1, 30]:
            r = recompete_score_breakdown(_row(days_remaining=d))
            c = _component(r, "Time remaining")
            assert c["earned"] == 25, f"failed for days={d}"

    def test_expired_earns_25(self):
        r = recompete_score_breakdown(_row(days_remaining=-5))
        c = _component(r, "Time remaining")
        assert c["earned"] == 25

    def test_60_days_earns_20(self):
        r = recompete_score_breakdown(_row(days_remaining=60))
        c = _component(r, "Time remaining")
        assert c["earned"] == 20

    def test_90_days_earns_15(self):
        r = recompete_score_breakdown(_row(days_remaining=90))
        c = _component(r, "Time remaining")
        assert c["earned"] == 15

    def test_180_days_earns_10(self):
        r = recompete_score_breakdown(_row(days_remaining=180))
        c = _component(r, "Time remaining")
        assert c["earned"] == 10

    def test_181_days_earns_0(self):
        r = recompete_score_breakdown(_row(days_remaining=181))
        c = _component(r, "Time remaining")
        assert c["earned"] == 0

    def test_none_days_earns_0(self):
        r = recompete_score_breakdown(_row(days_remaining=None))
        c = _component(r, "Time remaining")
        assert c["earned"] == 0


# ── Agency bonus ──────────────────────────────────────────────────────────────

class TestAgencyBonus:
    def test_defense_earns_5(self):
        r = recompete_score_breakdown(_row(agency="DEPARTMENT OF DEFENSE"))
        c = _component(r, "Agency bonus")
        assert c["earned"] == 5

    def test_veterans_affairs_earns_4(self):
        r = recompete_score_breakdown(_row(agency="DEPARTMENT OF VETERANS AFFAIRS"))
        c = _component(r, "Agency bonus")
        assert c["earned"] == 4

    def test_homeland_security_earns_3(self):
        r = recompete_score_breakdown(_row(agency="DEPARTMENT OF HOMELAND SECURITY"))
        c = _component(r, "Agency bonus")
        assert c["earned"] == 3

    def test_other_agency_earns_0(self):
        r = recompete_score_breakdown(_row(agency="DEPARTMENT OF AGRICULTURE"))
        c = _component(r, "Agency bonus")
        assert c["earned"] == 0

    def test_none_agency_earns_0(self):
        r = recompete_score_breakdown(_row(agency=None))
        c = _component(r, "Agency bonus")
        assert c["earned"] == 0


# ── Solicitation bonus ────────────────────────────────────────────────────────

class TestSolicitationBonus:
    def test_solicitation_id_earns_5(self):
        r = recompete_score_breakdown(_row(solicitation_id="W912HV-24-R-0001"))
        c = _component(r, "Solicitation on file")
        assert c["earned"] == 5

    def test_no_solicitation_earns_0(self):
        r = recompete_score_breakdown(_row(solicitation_id=None))
        c = _component(r, "Solicitation on file")
        assert c["earned"] == 0

    def test_empty_solicitation_earns_0(self):
        r = recompete_score_breakdown(_row(solicitation_id=""))
        c = _component(r, "Solicitation on file")
        assert c["earned"] == 0


# ── Office bonus ──────────────────────────────────────────────────────────────

class TestOfficeBonus:
    def test_priority_office_earns_5(self):
        r = recompete_score_breakdown(_row(awarding_office="NETWORK CONTRACT OFFICE 22"))
        c = _component(r, "Office signal")
        assert c["earned"] == 5

    def test_navfac_earns_5(self):
        r = recompete_score_breakdown(_row(awarding_office="NAVFAC SOUTHEAST"))
        c = _component(r, "Office signal")
        assert c["earned"] == 5

    def test_unknown_office_earns_0(self):
        r = recompete_score_breakdown(_row(awarding_office="RANDOM CONTRACTING OFFICE"))
        c = _component(r, "Office signal")
        assert c["earned"] == 0

    def test_none_office_earns_0(self):
        r = recompete_score_breakdown(_row(awarding_office=None))
        c = _component(r, "Office signal")
        assert c["earned"] == 0


# ── Total and structure ───────────────────────────────────────────────────────

class TestTotalAndStructure:
    def test_total_is_sum_of_earned(self):
        r = recompete_score_breakdown(_row(
            competition_type="FULL AND OPEN COMPETITION",
            value=10_000_000,
            days_remaining=30,
            agency="DEPARTMENT OF DEFENSE",
            solicitation_id="SOL-123",
        ))
        expected = 40 + 35 + 25 + 5 + 5 + 0
        assert r["total"] == expected

    def test_all_zero_total(self):
        r = recompete_score_breakdown(_row())
        assert r["total"] == 0

    def test_components_list_has_six_entries(self):
        r = recompete_score_breakdown(_row())
        assert len(r["components"]) == 6

    def test_each_component_has_required_keys(self):
        r = recompete_score_breakdown(_row())
        for c in r["components"]:
            assert "name" in c
            assert "earned" in c
            assert "max" in c
            assert "detail" in c

    def test_earned_never_exceeds_max(self):
        r = recompete_score_breakdown(_row(
            competition_type="FULL AND OPEN COMPETITION",
            value=20_000_000,
            days_remaining=10,
            agency="DEPARTMENT OF DEFENSE",
            solicitation_id="SOL-001",
            awarding_office="NAVFAC SOUTHWEST",
        ))
        for c in r["components"]:
            assert c["earned"] <= c["max"], f"{c['name']}: earned {c['earned']} > max {c['max']}"

    def test_primary_components_appear_before_bonuses(self):
        r = recompete_score_breakdown(_row())
        names = [c["name"] for c in r["components"]]
        assert names[0] == "Competition type"
        assert names[1] == "Contract value"
        assert names[2] == "Time remaining"
        # bonuses follow
        assert "Agency bonus" in names[3:]
        assert "Solicitation on file" in names[3:]
        assert "Office signal" in names[3:]
