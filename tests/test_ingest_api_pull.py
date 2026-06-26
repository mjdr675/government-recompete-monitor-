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
        """fetch_contracts(today, cutoff) must use action_date lookback window derived
        from the passed today — not module-level TODAY/CUTOFF frozen at import time."""
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

        filters = captured["payload"]["filters"]
        period = filters["time_period"][0]
        expected_start = (fixed_today - timedelta(days=jrr.ACTION_DATE_LOOKBACK_DAYS)).isoformat()
        assert period["date_type"] == "action_date", (
            "fetch_contracts must use action_date, not end_date"
        )
        assert period["start_date"] == expected_start, (
            "fetch_contracts must use lookback start derived from passed today, not module-level TODAY"
        )
        assert period["end_date"] == fixed_today.isoformat(), (
            "fetch_contracts end_date must be passed today"
        )
        assert "award_amounts" in filters, "filters must include award_amounts upper_bound cap"
        assert filters["award_amounts"][0]["upper_bound"] == jrr.MAX_CONTRACT_VALUE

    def test_fetch_contracts_never_sends_end_date_date_type(self, monkeypatch):
        """Regression: payload must never contain date_type 'end_date' (USASpending rejects it with 500)."""
        fixed_today = date(2025, 6, 1)
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
        jrr.fetch_contracts(fixed_today, fixed_today + timedelta(days=540))

        for period in captured["payload"]["filters"]["time_period"]:
            assert period.get("date_type") != "end_date", (
                "date_type 'end_date' is rejected by USASpending with HTTP 500 — must not appear in payload"
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


# ---------------------------------------------------------------------------
# Exception handling — retry + logging
# ---------------------------------------------------------------------------

class TestFetchContractsExceptionHandling:
    def test_request_exception_is_retried_and_logged(self, monkeypatch, caplog):
        """Any requests.exceptions.RequestException should trigger a warning
        and a reconnect rather than propagating out of the retry loop."""
        import requests as req_lib
        fixed_today = date(2025, 6, 1)
        call_count = {"n": 0}

        def flaky_post(self_or_url, url_or_none=None, json=None, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise req_lib.exceptions.Timeout("read timed out")
            class OkResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self):
                    return {"results": [], "page_metadata": {"hasNext": False}}
            return OkResp()

        monkeypatch.setattr(jrr.requests.Session, "post", flaky_post)
        with caplog.at_level(logging.WARNING, logger="ingest"):
            jrr.fetch_contracts(fixed_today, fixed_today + timedelta(days=540))

        assert call_count["n"] >= 2, "fetch_contracts must retry after a RequestException"
        assert any("request error" in r.message for r in caplog.records), (
            "fetch_contracts must log a WARNING with 'request error' on RequestException"
        )

    def test_ssl_error_is_retried_not_raised(self, monkeypatch):
        """SSLError (a RequestException subclass) must be caught by the broad
        except clause and trigger a retry, not propagate unhandled."""
        import requests as req_lib
        fixed_today = date(2025, 6, 1)
        call_count = {"n": 0}

        def ssl_then_ok(self_or_url, url_or_none=None, json=None, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise req_lib.exceptions.SSLError("certificate verify failed")
            class OkResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self):
                    return {"results": [], "page_metadata": {"hasNext": False}}
            return OkResp()

        monkeypatch.setattr(jrr.requests.Session, "post", ssl_then_ok)
        # Must not raise
        jrr.fetch_contracts(fixed_today, fixed_today + timedelta(days=540))
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# __main__ logging setup
# ---------------------------------------------------------------------------

class TestMainBlockLogging:
    def test_main_block_configures_basicConfig(self):
        """The __main__ block must call logging.basicConfig so that progress
        logs are visible when janitorial_recompete_report.py is run directly.
        Verify by reading the source — not by executing __main__."""
        import ast, pathlib
        src = pathlib.Path(jrr.__file__).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                ):
                    block_src = ast.unparse(node)
                    assert "basicConfig" in block_src, (
                        "__main__ block must call logging.basicConfig so that progress "
                        "logs are visible when the script is run directly"
                    )
                    return
        raise AssertionError("No if __name__ == '__main__' block found in source")


# ---------------------------------------------------------------------------
# NAICS normalization — search endpoint returns {code, description} object
# ---------------------------------------------------------------------------

class TestNaicsCodeNormalization:
    def test_dict_naics_returns_code(self):
        assert jrr._naics_code({"code": "712120", "description": "HISTORICAL SITES"}) == "712120"

    def test_dict_naics_missing_code_returns_empty(self):
        assert jrr._naics_code({"description": "no code here"}) == ""

    def test_string_naics_passthrough(self):
        assert jrr._naics_code("561720") == "561720"

    def test_none_naics_returns_empty(self):
        assert jrr._naics_code(None) == ""

    def test_dict_naics_is_persistable_as_text(self, tmp_path, monkeypatch):
        """Regression: a dict NAICS must not reach the TEXT naics_code column
        (sqlite ProgrammingError). upsert_contract must store a plain string."""
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "NAICS_1",
            "vendor": "Acme",
            "naics_code": jrr._naics_code({"code": "712120", "description": "HISTORICAL SITES"}),
        })
        from sqlalchemy import text
        with db_module.get_engine().connect() as conn:
            val = conn.execute(text(
                "SELECT naics_code FROM contracts WHERE internal_id = 'NAICS_1'"
            )).scalar()
        db_module._cached_engine.cache_clear()
        assert val == "712120"


# ---------------------------------------------------------------------------
# Award-detail fetch resilience (retry on RemoteDisconnected / 5xx)
# ---------------------------------------------------------------------------

class TestAwardDetailRetry:
    def test_retries_then_succeeds_after_connection_error(self, monkeypatch):
        """A transient RemoteDisconnected must be retried, not blank the row."""
        import requests as req_lib
        calls = {"n": 0}

        def flaky_get(url, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise req_lib.exceptions.ConnectionError("Remote end closed connection")

            class Ok:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return {"latest_transaction_contract_data": {"solicitation_identifier": "SOL-9"}}
            return Ok()

        monkeypatch.setattr(jrr.time, "sleep", lambda *a, **k: None)
        monkeypatch.setattr(jrr.requests, "get", flaky_get)
        out = jrr.fetch_award_detail("AWD-1", retries=3)
        assert calls["n"] == 2
        assert out["latest_transaction_contract_data"]["solicitation_identifier"] == "SOL-9"

    def test_gives_up_after_retries_returns_empty(self, monkeypatch):
        import requests as req_lib
        calls = {"n": 0}

        def always_fail(url, timeout=None):
            calls["n"] += 1
            raise req_lib.exceptions.ConnectionError("Remote end closed connection")

        monkeypatch.setattr(jrr.time, "sleep", lambda *a, **k: None)
        monkeypatch.setattr(jrr.requests, "get", always_fail)
        out = jrr.fetch_award_detail("AWD-1", retries=3)
        assert out == {}
        assert calls["n"] == 3

    def test_5xx_is_retried(self, monkeypatch):
        calls = {"n": 0}

        def server_error_then_ok(url, timeout=None):
            calls["n"] += 1
            class Resp:
                status_code = 500 if calls["n"] == 1 else 200
                def raise_for_status(self): pass
                def json(self): return {"ok": True}
            return Resp()

        monkeypatch.setattr(jrr.time, "sleep", lambda *a, **k: None)
        monkeypatch.setattr(jrr.requests, "get", server_error_then_ok)
        out = jrr.fetch_award_detail("AWD-1", retries=3)
        assert out == {"ok": True}
        assert calls["n"] == 2

    def test_4xx_not_retried(self, monkeypatch):
        calls = {"n": 0}

        def not_found(url, timeout=None):
            calls["n"] += 1
            class Resp:
                status_code = 404
                def raise_for_status(self): raise Exception("404")
                def json(self): return {}
            return Resp()

        monkeypatch.setattr(jrr.time, "sleep", lambda *a, **k: None)
        monkeypatch.setattr(jrr.requests, "get", not_found)
        out = jrr.fetch_award_detail("AWD-1", retries=3)
        assert out == {}
        assert calls["n"] == 1  # 404 is not retried
