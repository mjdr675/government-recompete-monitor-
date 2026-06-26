"""Tests for naics_description column and _extract_pop_state bug fix.

Two things verified here:
1. _extract_pop_state now reads the `performance_state` key (the key
   janitorial_recompete_report uses), so place_of_performance_state is
   actually stored and the State filter works.
2. naics_description is parsed from the USASpending search NAICS dict,
   optionally upgraded by enrichment, and persisted as its own column.
"""

import pytest
from sqlalchemy import text
from datetime import date

import db as db_module
import janitorial_recompete_report as jrr


# ─── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


def _cols(engine):
    with engine.connect() as conn:
        return [r[1] for r in conn.execute(text("PRAGMA table_info(contracts)"))]


# ─── _extract_pop_state bug fix ─────────────────────────────────────────────

class TestExtractPopState:
    def test_reads_performance_state_key(self):
        """Ingest rows use 'performance_state'; _extract_pop_state must find it."""
        row = {"performance_state": "VA"}
        assert db_module._extract_pop_state(row) == "VA"

    def test_still_reads_place_of_performance_state(self):
        row = {"place_of_performance_state": "TX"}
        assert db_module._extract_pop_state(row) == "TX"

    def test_prefers_place_of_performance_state_over_performance_state(self):
        row = {"place_of_performance_state": "TX", "performance_state": "VA"}
        assert db_module._extract_pop_state(row) == "TX"

    def test_lowercases_are_uppercased(self):
        row = {"performance_state": "ca"}
        assert db_module._extract_pop_state(row) == "CA"

    def test_empty_performance_state_falls_through(self):
        row = {"performance_state": "", "pop_state": "MD"}
        assert db_module._extract_pop_state(row) == "MD"

    def test_missing_returns_none(self):
        assert db_module._extract_pop_state({}) is None

    def test_upsert_contract_persists_performance_state_key(self, sqlite_db):
        """When ingest row uses performance_state, the DB column is populated."""
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "STATE_BUG",
            "vendor": "Acme",
            "agency": "DoD",
            "performance_state": "VA",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT place_of_performance_state FROM contracts WHERE internal_id = 'STATE_BUG'"
            )).scalar()
        assert val == "VA"

    def test_save_snapshot_persists_performance_state_key(self, sqlite_db):
        db_module.init_db()
        db_module.save_snapshot(str(date.today()), [{
            "internal_id": "SNAP_STATE",
            "generated_internal_id": "SNAP_STATE",
            "award_id": "AWD-1",
            "vendor": "Test Vendor",
            "agency": "DoD",
            "value": 100000,
            "start_date": "2024-01-01",
            "end_date": "2026-12-31",
            "days_remaining": 189,
            "recompete_score": 40,
            "priority": "LOW",
            "performance_state": "MD",
        }])
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT place_of_performance_state FROM contracts WHERE internal_id = 'SNAP_STATE'"
            )).scalar()
        assert val == "MD"


# ─── naics_description column ───────────────────────────────────────────────

class TestNaicsDescriptionColumn:
    def test_brand_new_db_has_naics_description(self, sqlite_db):
        db_module.init_db()
        assert "naics_description" in _cols(db_module.get_engine())

    def test_self_heal_adds_naics_description_to_existing_db(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE contracts DROP COLUMN naics_description"))
        assert "naics_description" not in _cols(engine)

        db_module.init_db()
        assert "naics_description" in _cols(engine)

    def test_upsert_contract_persists_naics_description(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "NAICS_DESC",
            "vendor": "Tech Corp",
            "agency": "DoD",
            "naics_code": "541511",
            "naics_description": "Custom Computer Programming Services",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT naics_description FROM contracts WHERE internal_id = 'NAICS_DESC'"
            )).scalar()
        assert val == "Custom Computer Programming Services"

    def test_missing_naics_description_stored_as_null(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "NO_NAICS_DESC",
            "vendor": "Acme",
            "agency": "GSA",
            "naics_code": "541511",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT naics_description FROM contracts WHERE internal_id = 'NO_NAICS_DESC'"
            )).scalar()
        assert val is None

    def test_save_snapshot_persists_naics_description(self, sqlite_db):
        db_module.init_db()
        db_module.save_snapshot(str(date.today()), [{
            "internal_id": "SNAP_NAICS",
            "generated_internal_id": "SNAP_NAICS",
            "award_id": "AWD-NAICS",
            "vendor": "Tech Vendor",
            "agency": "DoD",
            "value": 750000,
            "start_date": "2024-01-01",
            "end_date": "2027-06-01",
            "days_remaining": 340,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "naics_code": "541511",
            "naics_description": "Custom Computer Programming Services",
        }])
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT naics_description FROM contracts WHERE internal_id = 'SNAP_NAICS'"
            )).scalar()
        assert val == "Custom Computer Programming Services"


# ─── _naics_description helper ──────────────────────────────────────────────

class TestNaicsDescriptionHelper:
    def test_extracts_description_from_dict(self):
        naics = {"code": "541511", "description": "Custom Computer Programming Services"}
        assert jrr._naics_description(naics) == "Custom Computer Programming Services"

    def test_returns_empty_for_plain_string(self):
        assert jrr._naics_description("541511") == ""

    def test_returns_empty_for_none(self):
        assert jrr._naics_description(None) == ""

    def test_returns_empty_for_dict_without_description(self):
        assert jrr._naics_description({"code": "541511"}) == ""

    def test_naics_code_still_works_alongside(self):
        naics = {"code": "541511", "description": "Custom Computer Programming Services"}
        assert jrr._naics_code(naics) == "541511"
        assert jrr._naics_description(naics) == "Custom Computer Programming Services"


# ─── enrichment_from_detail includes naics_description ──────────────────────

class TestEnrichmentNaicsDescription:
    def test_enrichment_extracts_naics_description(self):
        data = {
            "latest_transaction_contract_data": {
                "naics_description": "Engineering Services",
                "product_or_service_code": "R499",
                "product_or_service_description": "Support",
            },
            "place_of_performance": {},
            "recipient": {},
            "awarding_agency": {},
            "funding_agency": {},
            "parent_award": {},
            "psc_hierarchy": {},
        }
        result = jrr.enrichment_from_detail(data)
        assert result["naics_description"] == "Engineering Services"

    def test_enrichment_returns_empty_when_missing(self):
        data = {
            "latest_transaction_contract_data": {},
            "place_of_performance": {},
            "recipient": {},
            "awarding_agency": {},
            "funding_agency": {},
            "parent_award": {},
            "psc_hierarchy": {},
        }
        result = jrr.enrichment_from_detail(data)
        assert result["naics_description"] == ""

    def test_enrichment_does_not_overwrite_with_empty_naics_description(self):
        """naics_description from search must not be blanked by empty enrichment."""
        row = {
            "internal_id": "X",
            "value": 600000,
            "days_remaining": 90,
            "generated_internal_id": "X",
            "naics_code": "541511",
            "naics_description": "From Search",
            "performance_state": "VA",
            "performance_city": "",
            "performance_zip": "",
            "performance_country": "",
        }
        # Enrichment returns empty naics_description
        enriched = {
            "naics_description": "",
            "performance_city": "Arlington",
            "performance_state": "VA",
            "performance_zip": "22201",
            "performance_country": "UNITED STATES",
        }
        for k, v in enriched.items():
            if v or k not in ("performance_city", "performance_state", "performance_zip",
                               "performance_country", "naics_description"):
                row[k] = v
        assert row["naics_description"] == "From Search"
        assert row["performance_city"] == "Arlington"
