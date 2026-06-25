"""Tests for recompete_report.py — the generic, configurable contract ingest.

Covers:
- NAICS codes come from INGEST_NAICS_CODES env var, not hardcoded to janitorial.
- Default NAICS list is broader than just 561720.
- Multiple NAICS codes passed in a single API call.
- Zero-row ingest raises RuntimeError (not silently marked success).
- SAM_API_KEY missing is logged as WARNING.
- Successful ingest persists rows and records correct run_date.
- tasks.run_ingest calls recompete_report.main() not janitorial version.
- janitorial_recompete_report is preserved and still importable.
- fetch_contracts() retry/pagination behaves correctly.
"""

import inspect
import logging
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

import db as db_module
import recompete_report as rr


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

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


def _award(days_out=90, amount=500_000, naics="561720"):
    today = date.today()
    return {
        "Award ID": f"AWD-{naics}-{days_out}",
        "Recipient Name": "Test Vendor Inc",
        "Award Amount": str(amount),
        "Start Date": "2024-01-01",
        "End Date": (today + timedelta(days=days_out)).isoformat(),
        "Awarding Agency": "Department of Defense",
        "Awarding Sub Agency": "Army",
        "Description": f"Test services NAICS {naics}",
        "generated_internal_id": f"CONT_AWD_{naics}_{days_out}",
    }


# ---------------------------------------------------------------------------
# NAICS configuration
# ---------------------------------------------------------------------------

class TestNaicsConfiguration:
    def test_default_naics_codes_not_janitorial_only(self):
        """Default NAICS list must include codes beyond 561720 (janitorial)."""
        assert len(rr.DEFAULT_NAICS_CODES) > 1, "Default should cover multiple categories"
        non_janitorial = [c for c in rr.DEFAULT_NAICS_CODES if c != "561720"]
        assert len(non_janitorial) >= 1, "Default must include non-janitorial codes"

    def test_naics_codes_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("INGEST_NAICS_CODES", "541512,541611")
        codes = rr._naics_codes()
        assert codes == ["541512", "541611"]

    def test_naics_codes_falls_back_to_default_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("INGEST_NAICS_CODES", raising=False)
        codes = rr._naics_codes()
        assert codes == rr.DEFAULT_NAICS_CODES

    def test_naics_codes_ignores_blank_env_var(self, monkeypatch):
        monkeypatch.setenv("INGEST_NAICS_CODES", "   ")
        codes = rr._naics_codes()
        assert codes == rr.DEFAULT_NAICS_CODES

    def test_main_passes_all_naics_to_fetch_contracts(self, test_db, monkeypatch):
        """All NAICS codes must be passed in a single fetch_contracts call."""
        captured = []

        def fake_fetch(naics_codes):
            captured.append(naics_codes)
            return [_award()]

        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", side_effect=fake_fetch):
            rr.main(naics_codes=["561720", "541512", "541611"])

        assert len(captured) == 1, "fetch_contracts must be called exactly once"
        assert "561720" in captured[0]
        assert "541512" in captured[0]
        assert "541611" in captured[0]

    def test_main_accepts_explicit_naics_codes(self, test_db, monkeypatch):
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[_award()]):
            count = rr.main(naics_codes=["561720"])
        assert count > 0

    def test_fetch_contracts_sends_naics_in_payload(self):
        """fetch_contracts must send the naics_codes list in the API payload."""
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status.return_value = None
        ok_response.json.return_value = {
            "results": [],
            "page_metadata": {"hasNext": False},
        }
        with patch("recompete_report.requests.post", return_value=ok_response) as mock_post:
            rr.fetch_contracts(["541512", "541611"])
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert payload["filters"]["naics_codes"] == ["541512", "541611"]


# ---------------------------------------------------------------------------
# Zero-row guard
# ---------------------------------------------------------------------------

class TestZeroRowGuard:
    def test_raises_runtime_error_on_zero_matching_contracts(self, test_db, monkeypatch, caplog):
        """When 0 contracts pass the date filter, main() must raise RuntimeError
        so run_ingest records status='failure' in ingest_log."""
        expired = _award(days_out=-100)  # end date in the past
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[expired]):
            with caplog.at_level(logging.ERROR, logger="ingest"):
                with pytest.raises(RuntimeError, match="0 rows matched filter"):
                    rr.main(naics_codes=["561720"])

    def test_error_logged_before_raise_on_zero_rows(self, test_db, monkeypatch, caplog):
        expired = _award(days_out=-100)
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[expired]):
            with caplog.at_level(logging.ERROR, logger="ingest"):
                with pytest.raises(RuntimeError):
                    rr.main(naics_codes=["561720"])
        assert any("0 rows" in r.message for r in caplog.records)

    def test_no_raise_when_contracts_persist(self, test_db, monkeypatch):
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[_award()]):
            count = rr.main(naics_codes=["561720"])
        assert count >= 1


# ---------------------------------------------------------------------------
# SAM_API_KEY warning
# ---------------------------------------------------------------------------

class TestSamApiKeyWarning:
    def test_warning_logged_when_sam_key_missing(self, test_db, monkeypatch, caplog):
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[_award()]):
            with caplog.at_level(logging.WARNING, logger="ingest"):
                rr.main(naics_codes=["561720"])
        assert any("SAM_API_KEY" in r.message for r in caplog.records)

    def test_no_sam_warning_when_key_present(self, test_db, monkeypatch, caplog):
        monkeypatch.setenv("SAM_API_KEY", "fake-key")
        with patch.object(rr, "fetch_contracts", return_value=[_award()]):
            with caplog.at_level(logging.WARNING, logger="ingest"):
                rr.main(naics_codes=["561720"])
        sam_warnings = [r for r in caplog.records if "SAM_API_KEY" in r.message]
        assert sam_warnings == []


# ---------------------------------------------------------------------------
# Freshness / persistence
# ---------------------------------------------------------------------------

class TestFreshnessPersistence:
    def test_main_returns_row_count(self, test_db, monkeypatch):
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        awards = [_award(days_out=90), _award(days_out=120)]
        with patch.object(rr, "fetch_contracts", return_value=awards):
            count = rr.main(naics_codes=["561720"])
        assert count == 2

    def test_main_persists_contracts_to_db(self, test_db, monkeypatch):
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        with patch.object(rr, "fetch_contracts", return_value=[_award()]):
            rr.main(naics_codes=["561720"])
        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM contracts")).scalar()
        assert count >= 1

    def test_main_uses_today_not_module_level_constant(self, test_db, monkeypatch):
        """main() must call _today() so stale import-time date is never used.

        Patch _today() to a fixed past date. An award ending 100 days after
        that date is within [past_date, past_date+540] but outside real today's
        horizon. If _today() is used, count==1. If TODAY constant is used, count==0.
        """
        fixed = date(2025, 1, 1)
        monkeypatch.setattr(rr, "_today", lambda: fixed)
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        award = _award(days_out=100)  # end ~2026-09-03, past fixed+540 (2026-06-25)?
        # Actually: fixed (2025-01-01) + 540d = 2026-07-25; real today ~2026-06-25
        # award end = date.today() + 100d = 2026-10-03
        # With fixed: 2025-01-01 <= 2026-10-03 <= 2026-07-25 → FALSE (too far out)
        # Use a different strategy: award ending fixed+100d = 2025-04-11
        from datetime import date as _date
        target_end = (fixed + timedelta(days=100)).isoformat()
        custom_award = {
            "Award ID": "AWD-FRESHNESS",
            "Recipient Name": "Freshness Vendor",
            "Award Amount": "500000",
            "Start Date": "2024-01-01",
            "End Date": target_end,
            "Awarding Agency": "DOD",
            "Awarding Sub Agency": "Army",
            "Description": "Freshness test",
            "generated_internal_id": "CONT_AWD_FRESHNESS",
        }
        with patch.object(rr, "fetch_contracts", return_value=[custom_award]):
            # With _today()=2025-01-01, 2025-04-11 is within [2025-01-01, 2026-07-25]
            # With real today=2026-06-25, 2025-04-11 is in the past → 0 rows → raises
            count = rr.main(naics_codes=["561720"])
        assert count == 1, "main() must use _today() — stale module-level date would miss this award"

    def test_run_date_written_with_today_function(self, test_db, monkeypatch):
        fixed = date(2025, 3, 15)
        monkeypatch.setattr(rr, "_today", lambda: fixed)
        monkeypatch.delenv("SAM_API_KEY", raising=False)
        award = {
            "Award ID": "AWD-RUNDATE",
            "Recipient Name": "RunDate Vendor",
            "Award Amount": "300000",
            "Start Date": "2024-01-01",
            "End Date": (fixed + timedelta(days=90)).isoformat(),
            "Awarding Agency": "DOD",
            "Awarding Sub Agency": "Army",
            "Description": "RunDate test",
            "generated_internal_id": "CONT_AWD_RUNDATE",
        }
        with patch.object(rr, "fetch_contracts", return_value=[award]):
            rr.main(naics_codes=["561720"])
        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            run_date = conn.execute(
                text("SELECT run_date FROM contract_snapshots LIMIT 1")
            ).scalar()
        assert run_date == "2025-03-15"


# ---------------------------------------------------------------------------
# tasks.run_ingest wiring
# ---------------------------------------------------------------------------

class TestTasksWiring:
    def test_run_ingest_calls_recompete_report_not_janitorial(self):
        """tasks.py must import main from recompete_report, not janitorial_recompete_report.
        Janitorial-only ingest is a product regression — the scheduler must use
        the generic configurable script."""
        import tasks as tasks_module
        source = inspect.getsource(tasks_module.run_ingest)
        assert "recompete_report" in source, (
            "run_ingest must import from recompete_report (configurable NAICS), "
            "not janitorial_recompete_report (hardcoded to cleaning-only NAICS 561720)"
        )
        assert "janitorial_recompete_report" not in source, (
            "run_ingest must NOT import from janitorial_recompete_report"
        )

    def test_janitorial_report_still_importable(self):
        """Backward compatibility: janitorial_recompete_report must remain importable."""
        import janitorial_recompete_report as jrr
        assert callable(jrr.main)
        assert callable(jrr.fetch_contracts)

    def test_janitorial_report_has_today_function(self):
        import janitorial_recompete_report as jrr
        assert callable(jrr._today)
        assert jrr._today() == date.today()


# ---------------------------------------------------------------------------
# fetch_contracts retry and pagination
# ---------------------------------------------------------------------------

class TestFetchContractsRetry:
    def _resp(self, status=200, results=None, has_next=False):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = {
            "results": results or [],
            "page_metadata": {"hasNext": has_next},
        }
        if status >= 400:
            r.raise_for_status.side_effect = Exception(f"HTTP {status}")
        else:
            r.raise_for_status.return_value = None
        return r

    def test_retries_on_500_then_succeeds(self):
        fail = self._resp(500)
        ok = self._resp(200, results=[{"id": "x"}])
        with patch("recompete_report.requests.post", side_effect=[fail, ok]):
            with patch("recompete_report.time.sleep"):
                results = rr.fetch_contracts(["561720"])
        assert len(results) == 1

    def test_raises_after_three_failures(self):
        fail = self._resp(500)
        with patch("recompete_report.requests.post", return_value=fail):
            with patch("recompete_report.time.sleep"):
                with pytest.raises(Exception):
                    rr.fetch_contracts(["561720"])

    def test_paginates_when_has_next(self):
        p1 = self._resp(200, results=[{"id": "a"}], has_next=True)
        p2 = self._resp(200, results=[{"id": "b"}], has_next=False)
        with patch("recompete_report.requests.post", side_effect=[p1, p2]):
            results = rr.fetch_contracts(["561720"])
        assert len(results) == 2

    def test_stops_on_last_page(self):
        p1 = self._resp(200, results=[{"id": "a"}], has_next=False)
        with patch("recompete_report.requests.post", return_value=p1) as m:
            rr.fetch_contracts(["561720"])
        assert m.call_count == 1
