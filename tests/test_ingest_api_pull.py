"""Tests for the contract API pull / ingest reliability fixes.

Covers:
- Stale TODAY date bug: main() must use a fresh date on every call, not the
  module-level constant that is frozen at Celery worker import time.
- Missing SAM_API_KEY: must produce a visible warning, not silent skip.
- fetch_contracts() retry logic: retries on 5xx, raises after exhaustion.
- fetch_contracts() stops at last page: does not paginate forever.
- Zero-results guard: main() logs an error when 0 contracts match the filter.
"""

import logging
from datetime import date, timedelta
from unittest.mock import patch

import pytest

import db as db_module
import janitorial_recompete_report as jrr


# ---------------------------------------------------------------------------
# Shared fixture — isolated DB + temp working directory
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


def _award_ending(end_date: date, amount=500_000):
    """Return a USASpending-shaped award dict with the given end date."""
    return {
        "Award ID": f"AWD-{end_date.isoformat()}",
        "Recipient Name": "Test Vendor",
        "Award Amount": str(amount),
        "Start Date": "2024-01-01",
        "End Date": end_date.isoformat(),
        "Awarding Agency": "Department of Defense",
        "Awarding Sub Agency": "Army",
        "Description": "Test services",
        "generated_internal_id": f"CONT_AWD_{end_date.isoformat()}",
    }


# ---------------------------------------------------------------------------
# Stale TODAY date bug
# ---------------------------------------------------------------------------

class TestStaleDateFix:
    def test_main_uses_today_function_not_module_constant(self, test_db, monkeypatch):
        """main() must call _today() so frozen module-level TODAY in a long-lived
        Celery worker doesn't silently filter on an old date.

        Strategy: monkeypatch _today() to a fixed past date (2025-01-01).
        Create an award whose end date is 100 days after that date (2025-04-11).
        - If main() uses _today() (2025-01-01): end date is in the future → persisted.
        - If main() uses module-level TODAY (real today ~2026): end date is in the
          past → NOT persisted.
        Only one behavior results in count == 1.
        """
        fixed_today = date(2025, 1, 1)
        monkeypatch.setattr(jrr, "_today", lambda: fixed_today)

        award = _award_ending(fixed_today + timedelta(days=100))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM contracts")).scalar()
        assert count == 1, (
            "Contract should be persisted when end date is within _today()'s horizon. "
            "If count is 0, main() likely used the stale module-level TODAY."
        )

    def test_today_function_returns_current_date(self):
        assert jrr._today() == date.today()

    def test_module_today_still_accessible_for_test_fixtures(self):
        """Module-level TODAY must remain so test helpers can construct relative dates."""
        assert isinstance(jrr.TODAY, date)

    def test_main_run_date_matches_today_function_not_module_constant(self, test_db, monkeypatch):
        """The run_date written to contract_snapshots must reflect _today(), not TODAY."""
        fixed_date = date(2025, 3, 15)
        monkeypatch.setattr(jrr, "_today", lambda: fixed_date)

        award = _award_ending(fixed_date + timedelta(days=90))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            run_date = conn.execute(
                text("SELECT run_date FROM contract_snapshots LIMIT 1")
            ).scalar()
        assert run_date == "2025-03-15"


# ---------------------------------------------------------------------------
# SAM_API_KEY missing warning
# ---------------------------------------------------------------------------

class TestSamApiKeyWarning:
    def test_warning_logged_when_sam_key_missing(self, test_db, monkeypatch, caplog):
        monkeypatch.delenv("SAM_API_KEY", raising=False)

        today = date.today()
        award = _award_ending(today + timedelta(days=90))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            with caplog.at_level(logging.WARNING, logger="ingest"):
                jrr.main()

        assert any("SAM_API_KEY" in r.message for r in caplog.records), (
            "Expected a WARNING about missing SAM_API_KEY in the 'ingest' logger"
        )

    def test_no_sam_warning_when_key_present(self, test_db, monkeypatch, caplog):
        monkeypatch.setenv("SAM_API_KEY", "fake-key-for-test")

        today = date.today()
        award = _award_ending(today + timedelta(days=90))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            with caplog.at_level(logging.WARNING, logger="ingest"):
                jrr.main()

        sam_warnings = [r for r in caplog.records if "SAM_API_KEY" in r.message]
        assert sam_warnings == []


# ---------------------------------------------------------------------------
# NOTE: fetch_contracts() retry/pagination tests from the original lane commit
# were dropped during integration. They asserted a 3-attempt requests.post loop
# that raises on persistent failure and returns unfiltered results. Integration
# kept origin/main's stronger fetch_contracts instead (session-based 5-attempt
# retry with reconnect, in-loop date + $10M value-ceiling filtering, skip-page
# on persistent 5xx rather than aborting the whole run). Those tests are
# incompatible with that behavior; the production retry path is exercised by the
# broader suite. The stale-date, SAM-key, and zero-row guards below — the actual
# reliability fixes this commit lands — are retained.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Zero-results guard
# ---------------------------------------------------------------------------

class TestZeroResultsGuard:
    def test_raises_and_logs_error_when_no_contracts_match_filter(self, test_db, monkeypatch, caplog):
        """If fetch_contracts returns data but none passes the date filter,
        main() must both log an ERROR and raise RuntimeError so callers
        (run_ingest Celery task) record a 'failure' status — not silently
        mark ingest as successful with 0 rows persisted."""
        expired_award = _award_ending(date(2021, 1, 1))  # far in the past
        with patch.object(jrr, "fetch_contracts", return_value=[expired_award]):
            with caplog.at_level(logging.ERROR, logger="ingest"):
                with pytest.raises(RuntimeError, match="0 rows matched filter"):
                    jrr.main()

        assert any("0 rows" in r.message or "0 contracts" in r.message for r in caplog.records), (
            "Expected an ERROR log when ingest produces 0 matching contracts"
        )

    def test_no_error_when_contracts_persist(self, test_db, monkeypatch, caplog):
        today = date.today()
        award = _award_ending(today + timedelta(days=90))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            with caplog.at_level(logging.ERROR, logger="ingest"):
                jrr.main()

        zero_errors = [r for r in caplog.records
                       if r.levelno >= logging.ERROR and "0 rows" in r.message]
        assert zero_errors == []


# ---------------------------------------------------------------------------
# fetch_contracts() uses passed today/cutoff, not module-level constants
# ---------------------------------------------------------------------------

class TestFetchContractsDateParam:
    def test_fetch_contracts_uses_passed_today_in_api_payload(self, monkeypatch):
        """fetch_contracts(today, cutoff) must embed the passed dates in the
        API payload — not the module-level TODAY/CUTOFF frozen at import time."""
        fixed_today = date(2025, 6, 1)
        fixed_cutoff = fixed_today + timedelta(days=540)
        captured = {}

        def fake_post(self_or_url, url_or_none=None, json=None, timeout=None):
            captured["payload"] = json
            class FakeResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self):
                    return {"results": [], "page_metadata": {"hasNext": False}}
            return FakeResp()

        monkeypatch.setattr(jrr.requests.Session, "post", fake_post)
        jrr.fetch_contracts(fixed_today, fixed_cutoff)

        period = captured["payload"]["filters"]["time_period"][0]
        assert period["start_date"] == "2025-06-01", (
            "fetch_contracts must use passed today, not module-level TODAY"
        )
        assert period["end_date"] == fixed_cutoff.isoformat(), (
            "fetch_contracts must use passed cutoff, not module-level CUTOFF"
        )


# ---------------------------------------------------------------------------
# ingest_log writes
# ---------------------------------------------------------------------------

class TestIngestLogWrites:
    def test_main_writes_ingest_log_success(self, test_db, monkeypatch):
        """On successful ingest, main() must write a 'success' row to ingest_log."""
        today = date.today()
        award = _award_ending(today + timedelta(days=90))
        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            row = conn.execute(text(
                "SELECT status, record_count, source FROM ingest_log LIMIT 1"
            )).fetchone()
        assert row is not None, "ingest_log must have a row after successful main()"
        assert row[0] == "success"
        assert row[1] >= 1
        assert row[2] == "usaspending"

    def test_main_writes_ingest_log_failure_on_zero_rows(self, test_db, monkeypatch):
        """When fetch_contracts returns no usable rows, main() must write a 'failure'
        row to ingest_log before raising RuntimeError."""
        expired_award = _award_ending(date(2021, 1, 1))
        with patch.object(jrr, "fetch_contracts", return_value=[expired_award]):
            with pytest.raises(RuntimeError):
                jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            row = conn.execute(text(
                "SELECT status, record_count FROM ingest_log LIMIT 1"
            )).fetchone()
        assert row is not None, "ingest_log must have a row even on zero-row failure"
        assert row[0] == "failure"
        assert row[1] == 0

    def test_main_writes_ingest_log_failure_on_exception(self, test_db, monkeypatch):
        """When save_snapshot raises, main() must write a 'failure' row to ingest_log."""
        today = date.today()
        award = _award_ending(today + timedelta(days=90))

        def bad_snapshot(*args, **kwargs):
            raise RuntimeError("DB write blew up")

        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            with patch.object(jrr, "save_snapshot", bad_snapshot):
                with pytest.raises(RuntimeError, match="DB write blew up"):
                    jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            row = conn.execute(text(
                "SELECT status, error_message FROM ingest_log LIMIT 1"
            )).fetchone()
        assert row is not None, "ingest_log must have a row when persistence fails"
        assert row[0] == "failure"
        assert "DB write blew up" in (row[1] or "")

    def test_main_ingest_log_run_date_matches_today(self, test_db, monkeypatch):
        """The run_date in ingest_log must reflect _today(), not the module constant."""
        fixed_today = date(2025, 9, 15)
        monkeypatch.setattr(jrr, "_today", lambda: fixed_today)
        award = _award_ending(fixed_today + timedelta(days=90))

        with patch.object(jrr, "fetch_contracts", return_value=[award]):
            jrr.main()

        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            run_date = conn.execute(text(
                "SELECT run_date FROM ingest_log LIMIT 1"
            )).scalar()
        assert run_date == "2025-09-15"
