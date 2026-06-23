"""Regression tests for the ingest enrichment award-id mismatch.

Tier-A enrichment previously gated on ``row["internal_id"]``, but the
USAspending ingest only populates ``generated_internal_id`` — so
``should_enrich()`` was always falsy and enrichment never ran. The fix resolves
the award id via ``enrichment_award_id()`` (``internal_id`` → fallback
``generated_internal_id``). These tests pin the behavior in both pipelines.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

import db as db_module

# Both near-identical pipelines must behave the same for the unit-level checks.
import janitorial_recompete_report as jrr
import recompete_report as rr


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)  # CSV write lands in scratch dir, not the repo
    yield db_path
    db_module._cached_engine.cache_clear()


# ---------------------------------------------------------------------------
# enrichment_award_id() / should_enrich() — both modules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mod", [jrr, rr])
class TestAwardIdResolution:
    def test_generated_internal_id_resolves_when_internal_id_absent(self, mod):
        row = {"generated_internal_id": "CONT_AWD_99", "internal_id": None}
        assert mod.enrichment_award_id(row) == "CONT_AWD_99"

    def test_internal_id_preferred_when_present(self, mod):
        row = {"generated_internal_id": "CONT_AWD_99", "internal_id": "IID_1"}
        assert mod.enrichment_award_id(row) == "IID_1"

    def test_no_usable_id_returns_falsy(self, mod):
        assert not mod.enrichment_award_id({"internal_id": None})
        assert not mod.enrichment_award_id({})

    def test_row_with_generated_id_is_eligible_for_enrichment(self, mod):
        # Tier-A: >= $1M and <= 180 days remaining, only generated_internal_id set.
        row = {"value": 2_000_000, "days_remaining": 100,
               "generated_internal_id": "CONT_AWD_BIG", "internal_id": None}
        assert mod.should_enrich(row) is True

    def test_enrichment_skipped_when_no_award_id(self, mod):
        # Meets value/time thresholds but has no usable award id → must not enrich.
        row = {"value": 5_000_000, "days_remaining": 30,
               "generated_internal_id": None, "internal_id": None}
        assert mod.should_enrich(row) is False

    def test_enrichment_skipped_below_thresholds(self, mod):
        row = {"value": 10_000, "days_remaining": 30,
               "generated_internal_id": "CONT_AWD_SMALL"}
        assert mod.should_enrich(row) is False


# ---------------------------------------------------------------------------
# End-to-end: enrichment actually runs and scoring/persistence still work
# ---------------------------------------------------------------------------

def _award(jrr_mod, generated_id, amount, days_out, agency="DEFENSE"):
    end = (jrr_mod.TODAY + timedelta(days=days_out)).isoformat()
    start = (jrr_mod.TODAY - timedelta(days=200)).isoformat()
    return {
        "Award ID": f"AWD-{generated_id}",
        "Recipient Name": "Acme Corp",
        "Award Amount": str(amount),
        "Start Date": start,
        "End Date": end,
        "Awarding Agency": agency,
        "Awarding Sub Agency": "ARMY",
        "Description": "Services",
        "generated_internal_id": generated_id,
        # note: no "internal_id" key — mirrors real USAspending responses
    }


# Award-detail payload that enrichment_from_detail() parses into a competed,
# solicitation-bearing contract (drives recompete_score up).
_DETAIL = {
    "latest_transaction_contract_data": {
        "extent_competed_description": "FULL AND OPEN COMPETITION",
        "solicitation_identifier": "SOL-XYZ",
    },
    "awarding_agency": {"office_agency_name": "Contracting Office"},
}


def test_main_enriches_tier_a_via_generated_id_and_persists(test_db):
    big = _award(jrr, "CONT_AWD_BIG", 2_000_000, 100)   # qualifies for enrichment
    small = _award(jrr, "CONT_AWD_SMALL", 50_000, 100)  # below value threshold

    with patch.object(jrr, "fetch_contracts", return_value=[big, small]), \
         patch.object(jrr, "fetch_award_detail", return_value=_DETAIL) as mock_detail:
        jrr.main()

    # Enrichment ran exactly once, addressed by the generated_internal_id.
    mock_detail.assert_called_once_with("CONT_AWD_BIG")

    with db_module.get_engine().connect() as conn:
        big_row = conn.execute(text(
            "SELECT competition_type, solicitation_id, recompete_score, priority"
            " FROM contracts WHERE internal_id = 'CONT_AWD_BIG'"
        )).mappings().fetchone()
        small_row = conn.execute(text(
            "SELECT competition_type, recompete_score FROM contracts"
            " WHERE internal_id = 'CONT_AWD_SMALL'"
        )).mappings().fetchone()

    # Enriched fields landed and fed back into scoring.
    assert big_row["competition_type"] == "FULL AND OPEN COMPETITION"
    assert big_row["solicitation_id"] == "SOL-XYZ"
    # competition(40) + value 2M(15) + days 100(10) + DEFENSE(5) + solicitation(5) = 75
    assert big_row["recompete_score"] == 75
    assert big_row["priority"] == "HIGH"

    # Non-qualifying row persisted but never enriched.
    assert (small_row["competition_type"] or "") == ""


def test_main_skips_enrichment_when_no_award_id(test_db):
    row = _award(jrr, "", 2_000_000, 100)  # qualifies on value/time, but blank id
    row["generated_internal_id"] = ""

    with patch.object(jrr, "fetch_contracts", return_value=[row]), \
         patch.object(jrr, "fetch_award_detail") as mock_detail:
        jrr.main()

    mock_detail.assert_not_called()
