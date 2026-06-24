"""Tests for parse_natural_query: stop-word removal, state extraction,
category/intent detection, and end-to-end integration with get_contracts.
"""
import pytest

import db as db_module
from db import parse_natural_query


# ---------------------------------------------------------------------------
# parse_natural_query — unit tests (pure function, no DB)
# ---------------------------------------------------------------------------

class TestCleanQ:
    def test_strips_stop_word_contracts(self):
        r = parse_natural_query("lawn care contracts")
        assert "contracts" not in r["clean_q"]

    def test_strips_stop_word_in(self):
        r = parse_natural_query("cleaning services in Kentucky")
        assert " in " not in r["clean_q"]

    def test_strips_multiple_stop_words(self):
        r = parse_natural_query("federal government it services")
        tokens = r["clean_q"].split()
        for sw in ("federal", "government", "services"):
            assert sw not in tokens

    def test_intent_phrase_removed_from_clean_q(self):
        # "lawn care" triggers category=Grounds; the phrase is removed from FTS
        # so the category filter handles semantic matching (not literal FTS).
        r = parse_natural_query("lawn care contracts")
        assert r["category"] == "Grounds"
        assert "lawn" not in r["clean_q"]
        assert "care" not in r["clean_q"]

    def test_empty_query(self):
        r = parse_natural_query("")
        assert r == {"clean_q": "", "state": "", "category": ""}

    def test_punctuation_only(self):
        r = parse_natural_query("!!!")
        assert r["clean_q"] == ""

    def test_all_stop_words(self):
        r = parse_natural_query("contracts for the government")
        assert r["clean_q"] == ""
        assert r["state"] == ""
        assert r["category"] == ""


class TestStateExtraction:
    def test_full_state_name(self):
        assert parse_natural_query("cleaning in Kentucky")["state"] == "KY"

    def test_full_state_name_case_insensitive(self):
        assert parse_natural_query("janitorial KENTUCKY")["state"] == "KY"

    def test_state_abbr_uppercase(self):
        assert parse_natural_query("janitorial services TX")["state"] == "TX"

    def test_state_removed_from_clean_q(self):
        r = parse_natural_query("lawn care Kentucky")
        assert "kentucky" not in r["clean_q"]

    def test_no_state(self):
        assert parse_natural_query("lawn care contracts")["state"] == ""

    def test_california(self):
        assert parse_natural_query("hvac contracts in California")["state"] == "CA"

    def test_new_york(self):
        assert parse_natural_query("security guards new york")["state"] == "NY"

    def test_washington_dc(self):
        assert parse_natural_query("it support washington dc")["state"] == "DC"

    def test_ambiguous_state_not_fired(self):
        # "indiana" inside "indianapolis" must NOT fire
        r = parse_natural_query("contracts in indianapolis")
        assert r["state"] == ""

    def test_west_virginia(self):
        assert parse_natural_query("grounds west virginia")["state"] == "WV"

    def test_dc_abbreviation(self):
        assert parse_natural_query("security guard DC")["state"] == "DC"


class TestCategoryExtraction:
    def test_lawn_care(self):
        assert parse_natural_query("lawn care contracts")["category"] == "Grounds"

    def test_landscaping(self):
        assert parse_natural_query("landscaping services")["category"] == "Grounds"

    def test_janitorial(self):
        assert parse_natural_query("janitorial services")["category"] == "Cleaning"

    def test_custodial(self):
        assert parse_natural_query("custodial work")["category"] == "Cleaning"

    def test_cybersecurity(self):
        assert parse_natural_query("cybersecurity contracts")["category"] == "Cybersecurity"

    def test_cyber_security_two_words(self):
        assert parse_natural_query("cyber security services")["category"] == "Cybersecurity"

    def test_it_support(self):
        assert parse_natural_query("it support services")["category"] == "IT"

    def test_help_desk(self):
        assert parse_natural_query("help desk services")["category"] == "IT"

    def test_security_guard(self):
        assert parse_natural_query("security guard services")["category"] == "Security"

    def test_hvac(self):
        assert parse_natural_query("hvac maintenance")["category"] == "Facilities"

    def test_building_maintenance(self):
        assert parse_natural_query("building maintenance contracts")["category"] == "Facilities"

    def test_construction(self):
        assert parse_natural_query("construction projects")["category"] == "Construction"

    def test_logistics(self):
        assert parse_natural_query("logistics and supply chain")["category"] == "Logistics"

    def test_no_category(self):
        assert parse_natural_query("large defense contractor")["category"] == ""


class TestCombined:
    def test_lawn_care_kentucky(self):
        r = parse_natural_query("lawn care contracts in Kentucky")
        assert r["state"] == "KY"
        assert r["category"] == "Grounds"
        # intent phrase and state removed; stop words stripped — clean_q is empty
        # (category filter handles the semantic match instead of FTS)
        assert "kentucky" not in r["clean_q"]
        assert "contracts" not in r["clean_q"]

    def test_cleaning_in_texas(self):
        r = parse_natural_query("cleaning services in Texas")
        assert r["state"] == "TX"
        assert r["category"] == "Cleaning"

    def test_it_contracts_california(self):
        r = parse_natural_query("it support contracts california")
        assert r["state"] == "CA"
        assert r["category"] == "IT"

    def test_abbreviation_plus_intent(self):
        r = parse_natural_query("janitorial services TX")
        assert r["state"] == "TX"
        assert r["category"] == "Cleaning"


# ---------------------------------------------------------------------------
# get_contracts integration — parsed intent filters results
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    db_module.save_snapshot("2026-06-22", [
        {
            "internal_id": "G1", "vendor": "Green Thumb Landscaping",
            "agency": "GSA", "award_id": "GT1", "value": 150_000,
            "recompete_score": 60, "priority": "MEDIUM",
            "description": "lawn mowing and grounds maintenance services",
            "place_of_performance_state": "KY",
        },
        {
            "internal_id": "C1", "vendor": "SparkleClean LLC",
            "agency": "VA", "award_id": "SC1", "value": 200_000,
            "recompete_score": 70, "priority": "HIGH",
            "description": "janitorial and custodial services",
            "place_of_performance_state": "TX",
        },
        {
            "internal_id": "C2", "vendor": "Cyber Defense Group",
            "agency": "DOD", "award_id": "CD1", "value": 500_000,
            "recompete_score": 90, "priority": "CRITICAL",
            "description": "cybersecurity and information security services",
            "place_of_performance_state": "VA",
        },
        {
            "internal_id": "G2", "vendor": "Bluegrass Services",
            "agency": "DOI", "award_id": "BG1", "value": 80_000,
            "recompete_score": 55, "priority": "LOW",
            "description": "landscape and turf maintenance",
            "place_of_performance_state": "KY",
        },
    ])
    yield


class TestGetContractsNaturalQuery:
    def test_lawn_care_contracts_kentucky_returns_grounds_ky(self, db):
        result = db_module.get_contracts(q="lawn care contracts in Kentucky")
        ids = {r["internal_id"] for r in result["contracts"]}
        # KY grounds contracts only
        assert "G1" in ids
        assert "G2" in ids
        assert "C1" not in ids   # TX, not KY
        assert "C2" not in ids   # wrong state and category

    def test_janitorial_returns_cleaning(self, db):
        result = db_module.get_contracts(q="janitorial services")
        ids = {r["internal_id"] for r in result["contracts"]}
        assert "C1" in ids
        assert "C2" not in ids

    def test_explicit_state_beats_parsed_state(self, db):
        # explicit state=VA should win over state extracted from "Kentucky" query
        result = db_module.get_contracts(q="lawn care Kentucky", state="VA")
        ids = {r["internal_id"] for r in result["contracts"]}
        # VA only — G1/G2 are KY
        assert "G1" not in ids
        assert "G2" not in ids

    def test_stop_words_only_returns_no_results(self, db):
        # All tokens are stop words → no usable signal → 0 results, same as
        # punctuation-only. Better than silently returning everything.
        result = db_module.get_contracts(q="contracts for the government")
        assert result["total"] == 0

    def test_abbreviation_state_filter(self, db):
        result = db_module.get_contracts(q="cleaning services TX")
        ids = {r["internal_id"] for r in result["contracts"]}
        assert "C1" in ids   # TX + Cleaning
        assert "G1" not in ids
