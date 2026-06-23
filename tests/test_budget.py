"""Tests for ai_agent/budget.py — cost budgeting and usage tracking."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_agent.budget import (
    MODEL_PRICING,
    BudgetConfig,
    BudgetTracker,
    UsageRecord,
    estimate_cost,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fixed_now(dt_str: str = "2026-06-20T12:00:00Z"):
    dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return lambda: dt


def _tracker(
    config: BudgetConfig = None,
    tmp_path: Path = None,
    now_str: str = "2026-06-20T12:00:00Z",
) -> BudgetTracker:
    path = (tmp_path / "usage.json") if tmp_path is not None else Path("/tmp/test_budget_unused.json")
    return BudgetTracker(config=config, usage_path=path, _now=_fixed_now(now_str))


def _write_record(path: Path, record: UsageRecord) -> None:
    """Write a single UsageRecord directly to a usage JSON file."""
    payload = {"records": [{
        "model": record.model,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost_usd": record.cost_usd,
        "timestamp": record.timestamp,
        "task_filename": record.task_filename,
    }]}
    path.write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

class TestEstimateCost:
    def test_known_haiku_model(self):
        # 1M input @ $1/MTok = $1.00; 1M output @ $5/MTok = $5.00
        cost = estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert abs(cost - 6.0) < 1e-6

    def test_known_sonnet_model(self):
        cost = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert abs(cost - 18.0) < 1e-6

    def test_known_opus_model(self):
        cost = estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000)
        assert abs(cost - 30.0) < 1e-6

    def test_haiku_alias_same_pricing(self):
        c1 = estimate_cost("claude-haiku-4-5", 500, 100)
        c2 = estimate_cost("claude-haiku-4-5-20251001", 500, 100)
        assert abs(c1 - c2) < 1e-12

    def test_unknown_model_falls_back_to_sonnet(self):
        known = estimate_cost("claude-sonnet-4-6", 1000, 200)
        unknown = estimate_cost("claude-definitely-unknown", 1000, 200)
        assert abs(known - unknown) < 1e-12

    def test_zero_tokens_returns_zero(self):
        assert estimate_cost("claude-haiku-4-5", 0, 0) == 0.0

    def test_only_input_tokens(self):
        cost = estimate_cost("claude-haiku-4-5", 1_000_000, 0)
        assert abs(cost - 1.0) < 1e-6

    def test_only_output_tokens(self):
        cost = estimate_cost("claude-haiku-4-5", 0, 1_000_000)
        assert abs(cost - 5.0) < 1e-6

    def test_all_models_have_positive_cost(self):
        for model in MODEL_PRICING:
            assert estimate_cost(model, 1000, 1000) > 0

    def test_output_more_expensive_than_input(self):
        # For every model, output rate should be ≥ input rate
        for model, (in_rate, out_rate) in MODEL_PRICING.items():
            assert out_rate >= in_rate, f"{model} output should cost >= input"


# ---------------------------------------------------------------------------
# record_usage
# ---------------------------------------------------------------------------

class TestRecordUsage:
    def test_returns_usage_record(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        r = t.record_usage("claude-haiku-4-5", 100, 50)
        assert isinstance(r, UsageRecord)
        assert r.model == "claude-haiku-4-5"
        assert r.input_tokens == 100
        assert r.output_tokens == 50

    def test_cost_calculated_correctly(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        r = t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        assert abs(r.cost_usd - 1.0) < 1e-6

    def test_timestamp_uses_injected_clock(self, tmp_path):
        t = _tracker(tmp_path=tmp_path, now_str="2026-06-20T09:30:00Z")
        r = t.record_usage("claude-haiku-4-5", 100, 50)
        assert r.timestamp == "2026-06-20T09:30:00Z"

    def test_task_filename_stored(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        r = t.record_usage("claude-haiku-4-5", 100, 50, task_filename="054-cost-budgeting.md")
        assert r.task_filename == "054-cost-budgeting.md"

    def test_default_task_filename_is_empty(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        r = t.record_usage("claude-haiku-4-5", 100, 50)
        assert r.task_filename == ""

    def test_multiple_records_accumulate(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        t.record_usage("claude-haiku-4-5", 200, 100)
        assert len(t._session_records) == 2

    def test_record_added_to_session_list(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        r = t.record_usage("claude-haiku-4-5", 100, 50)
        assert r in t._session_records


# ---------------------------------------------------------------------------
# session_cost
# ---------------------------------------------------------------------------

class TestSessionCost:
    def test_zero_when_no_calls(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        assert t.session_cost() == 0.0

    def test_sums_multiple_calls(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)   # $1.00
        t.record_usage("claude-haiku-4-5", 0, 1_000_000)   # $5.00
        assert abs(t.session_cost() - 6.0) < 1e-6

    def test_does_not_include_persisted_records(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        t.save()
        assert t.session_cost() == 0.0


# ---------------------------------------------------------------------------
# check_limits / should_pause
# ---------------------------------------------------------------------------

class TestCheckLimits:
    def test_returns_none_when_no_limits(self, tmp_path):
        t = _tracker(config=BudgetConfig(), tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert t.check_limits() is None

    def test_returns_none_below_session_limit(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=10.0)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        assert t.check_limits() is None

    def test_triggers_at_session_limit(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00 > $0.001
        reason = t.check_limits()
        assert reason is not None
        assert "Session" in reason

    def test_triggers_above_session_limit(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.5)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00 > $0.50
        assert t.check_limits() is not None

    def test_returns_none_at_zero_session_cost(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=1.0)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        assert t.check_limits() is None

    def test_triggers_at_total_limit(self, tmp_path):
        cfg = BudgetConfig(total_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00
        reason = t.check_limits()
        assert reason is not None
        assert "Total" in reason

    def test_total_limit_includes_persisted(self, tmp_path):
        cfg = BudgetConfig(total_limit_usd=1.5)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00
        t.save()
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # another $1.00 → $2.00 total
        assert t.check_limits() is not None

    def test_daily_limit_only_counts_today(self, tmp_path):
        """Records from yesterday must not count against today's daily limit."""
        yesterday_record = UsageRecord(
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=0,
            cost_usd=1.0,
            timestamp="2026-06-19T12:00:00Z",
            task_filename="",
        )
        path = tmp_path / "usage.json"
        _write_record(path, yesterday_record)

        cfg = BudgetConfig(daily_limit_usd=0.50)
        t = BudgetTracker(config=cfg, usage_path=path, _now=_fixed_now("2026-06-20T12:00:00Z"))
        # No usage today — should be under limit despite yesterday's $1.00
        assert t.check_limits() is None

    def test_daily_limit_triggers_when_exceeded_today(self, tmp_path):
        cfg = BudgetConfig(daily_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path, now_str="2026-06-20T12:00:00Z")
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00 today
        reason = t.check_limits()
        assert reason is not None
        assert "Daily" in reason

    def test_daily_limit_includes_earlier_today(self, tmp_path):
        """Earlier persisted calls from today count toward the daily limit."""
        earlier_today = UsageRecord(
            model="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=0,
            cost_usd=1.0,
            timestamp="2026-06-20T08:00:00Z",
            task_filename="",
        )
        path = tmp_path / "usage.json"
        _write_record(path, earlier_today)

        cfg = BudgetConfig(daily_limit_usd=1.5)
        t = BudgetTracker(config=cfg, usage_path=path, _now=_fixed_now("2026-06-20T14:00:00Z"))
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # another $1.00 → $2.00 daily
        assert t.check_limits() is not None

    def test_reason_includes_dollar_amounts(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        reason = t.check_limits()
        assert "$" in reason

    def test_session_checked_before_total(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.001, total_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        assert "Session" in t.check_limits()


class TestShouldPause:
    def test_false_when_no_limits(self, tmp_path):
        t = _tracker(config=BudgetConfig(), tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert t.should_pause() is False

    def test_true_when_session_limit_exceeded(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        assert t.should_pause() is True

    def test_false_when_no_session_records(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=1.0)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        assert t.should_pause() is False

    def test_false_when_under_all_limits(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=10.0, daily_limit_usd=50.0, total_limit_usd=100.0)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        assert t.should_pause() is False


# ---------------------------------------------------------------------------
# Persistence (save / load)
# ---------------------------------------------------------------------------

class TestSave:
    def test_creates_file(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        t.save()
        assert (tmp_path / "usage.json").exists()

    def test_clears_session_records(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        t.save()
        assert len(t._session_records) == 0

    def test_returns_path(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        result = t.save()
        assert result == tmp_path / "usage.json"

    def test_file_contains_valid_json(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        t.save()
        data = json.loads((tmp_path / "usage.json").read_text())
        assert "records" in data

    def test_accumulates_across_sessions(self, tmp_path):
        t1 = BudgetTracker(config=BudgetConfig(), usage_path=tmp_path / "usage.json", _now=_fixed_now())
        t1.record_usage("claude-haiku-4-5", 100, 50)
        t1.save()

        t2 = BudgetTracker(config=BudgetConfig(), usage_path=tmp_path / "usage.json", _now=_fixed_now())
        t2.record_usage("claude-haiku-4-5", 200, 100)
        t2.save()

        t3 = BudgetTracker(config=BudgetConfig(), usage_path=tmp_path / "usage.json", _now=_fixed_now())
        assert len(t3.load()) == 2

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "sub" / "dir" / "usage.json"
        t = BudgetTracker(config=BudgetConfig(), usage_path=nested, _now=_fixed_now())
        t.record_usage("claude-haiku-4-5", 100, 50)
        t.save()
        assert nested.exists()

    def test_save_with_no_records_writes_empty_list(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.save()
        data = json.loads((tmp_path / "usage.json").read_text())
        assert data["records"] == []


class TestLoad:
    def test_returns_records(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50, "054-test.md")
        t.save()
        loaded = t.load()
        assert len(loaded) == 1
        assert loaded[0].model == "claude-haiku-4-5"
        assert loaded[0].task_filename == "054-test.md"

    def test_returns_empty_when_file_missing(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        assert t.load() == []

    def test_handles_corrupt_json(self, tmp_path):
        path = tmp_path / "usage.json"
        path.write_text("not valid json")
        t = BudgetTracker(config=BudgetConfig(), usage_path=path, _now=_fixed_now())
        assert t.load() == []

    def test_handles_missing_records_key(self, tmp_path):
        path = tmp_path / "usage.json"
        path.write_text(json.dumps({"other": "data"}))
        t = BudgetTracker(config=BudgetConfig(), usage_path=path, _now=_fixed_now())
        assert t.load() == []

    def test_loaded_records_have_correct_fields(self, tmp_path):
        t = _tracker(tmp_path=tmp_path, now_str="2026-06-20T10:00:00Z")
        t.record_usage("claude-opus-4-8", 500, 200, "task.md")
        t.save()
        r = t.load()[0]
        assert r.model == "claude-opus-4-8"
        assert r.input_tokens == 500
        assert r.output_tokens == 200
        assert r.timestamp == "2026-06-20T10:00:00Z"


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_creates_file(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1000, 500)
        path = t.generate_report(tmp_path / "report.md")
        assert path.exists()

    def test_returns_path(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        out = tmp_path / "report.md"
        result = t.generate_report(out)
        assert result == out

    def test_starts_with_header(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        path = t.generate_report(tmp_path / "r.md")
        assert path.read_text().startswith("# Budget Report")

    def test_includes_total_cost(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)  # $1.00
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "1.000000" in content

    def test_includes_token_counts(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 12345, 6789)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "12,345" in content

    def test_includes_session_cost_line(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "Session cost" in content

    def test_shows_exceeded_when_over_limit(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=0.001)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 1_000_000, 0)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "EXCEEDED" in content

    def test_shows_no_limit_when_unconfigured(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "no limit" in content

    def test_includes_call_log_when_records_exist(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50, "054-test.md")
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "Call Log" in content
        assert "054-test.md" in content

    def test_no_call_log_when_no_records(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "Call Log" not in content

    def test_includes_model_in_call_log(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-opus-4-8", 100, 50)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "claude-opus-4-8" in content

    def test_creates_parent_dirs(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        path = tmp_path / "sub" / "dir" / "report.md"
        t.generate_report(path)
        assert path.exists()

    def test_includes_persisted_records(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50, "task-a.md")
        t.save()
        t.record_usage("claude-haiku-4-5", 200, 100, "task-b.md")
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "task-a.md" in content
        assert "task-b.md" in content

    def test_limits_section_present(self, tmp_path):
        t = _tracker(tmp_path=tmp_path)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "## Limits" in content

    def test_ok_status_when_under_limit(self, tmp_path):
        cfg = BudgetConfig(session_limit_usd=100.0)
        t = _tracker(config=cfg, tmp_path=tmp_path)
        t.record_usage("claude-haiku-4-5", 100, 50)
        content = t.generate_report(tmp_path / "r.md").read_text()
        assert "OK" in content


# ---------------------------------------------------------------------------
# call_with_usage integration (llm.py)
# ---------------------------------------------------------------------------

class TestCallWithUsage:
    def test_returns_text_and_token_counts(self):
        from unittest.mock import MagicMock, patch

        mock_usage = MagicMock()
        mock_usage.input_tokens = 42
        mock_usage.output_tokens = 17

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="hello world")]
        mock_message.usage = mock_usage

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                from ai_agent.llm import call_with_usage
                text, inp, out = call_with_usage("test prompt", model="claude-haiku-4-5")

        assert text == "hello world"
        assert inp == 42
        assert out == 17

    def test_raises_when_no_api_key(self):
        from unittest.mock import patch
        from ai_agent.llm import call_with_usage
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                call_with_usage("test prompt")

    def test_tuple_length_is_three(self):
        from unittest.mock import MagicMock, patch

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="ok")]
        mock_message.usage = MagicMock(input_tokens=10, output_tokens=5)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                from ai_agent.llm import call_with_usage
                result = call_with_usage("prompt")

        assert len(result) == 3
