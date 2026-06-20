"""
Cost Budgeting — tracks token usage and enforces spending limits.

Usage:
  from ai_agent.budget import BudgetConfig, BudgetTracker

  config = BudgetConfig(session_limit_usd=1.0, daily_limit_usd=5.0)
  tracker = BudgetTracker(config)
  record = tracker.record_usage("claude-haiku-4-5", 1000, 200, "054-cost-budgeting.md")
  if tracker.should_pause():
      ...
  path = tracker.generate_report()
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_AGENT_DIR = Path(__file__).parent
DEFAULT_USAGE_PATH = _AGENT_DIR / "budget_usage.json"
DEFAULT_REPORT_PATH = _AGENT_DIR / "budget_report.md"

# Per-token costs (USD). Pricing: $/MTok ÷ 1_000_000.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5":            (10.0 / 1_000_000, 50.0 / 1_000_000),
    "claude-opus-4-8":           ( 5.0 / 1_000_000, 25.0 / 1_000_000),
    "claude-opus-4-7":           ( 5.0 / 1_000_000, 25.0 / 1_000_000),
    "claude-opus-4-6":           ( 5.0 / 1_000_000, 25.0 / 1_000_000),
    "claude-sonnet-4-6":         ( 3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-haiku-4-5":          ( 1.0 / 1_000_000,  5.0 / 1_000_000),
    "claude-haiku-4-5-20251001": ( 1.0 / 1_000_000,  5.0 / 1_000_000),
}

# Fallback when model is not in MODEL_PRICING.
_FALLBACK_MODEL = "claude-sonnet-4-6"


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for a single API call."""
    in_rate, out_rate = MODEL_PRICING.get(model, MODEL_PRICING[_FALLBACK_MODEL])
    return in_rate * input_tokens + out_rate * output_tokens


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str       # ISO 8601 UTC string, e.g. "2026-06-20T12:00:00Z"
    task_filename: str = ""


@dataclass
class BudgetConfig:
    daily_limit_usd: Optional[float] = None
    session_limit_usd: Optional[float] = None
    total_limit_usd: Optional[float] = None


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------

class BudgetTracker:
    """
    Tracks per-session and cumulative token/cost usage.

    Args:
        config:      Spending limits. All limits default to None (unlimited).
        usage_path:  JSON file for persistent usage records.
        _now:        Injectable clock (returns UTC datetime). Override in tests.
    """

    def __init__(
        self,
        config: Optional[BudgetConfig] = None,
        usage_path: Path = DEFAULT_USAGE_PATH,
        _now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.config = config or BudgetConfig()
        self.usage_path = usage_path
        self._now: Callable[[], datetime] = _now or (lambda: datetime.now(timezone.utc))
        self._session_records: list[UsageRecord] = []

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_filename: str = "",
    ) -> UsageRecord:
        """Record one LLM call and append it to the session list."""
        cost = estimate_cost(model, input_tokens, output_tokens)
        record = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            timestamp=self._now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            task_filename=task_filename,
        )
        self._session_records.append(record)
        return record

    def session_cost(self) -> float:
        """Return total cost (USD) accrued in this session."""
        return sum(r.cost_usd for r in self._session_records)

    def check_limits(self) -> Optional[str]:
        """
        Return a human-readable reason string if any configured limit is
        exceeded, or ``None`` if all limits are within bounds.

        Checks in order: session → daily → total.
        """
        cfg = self.config

        if cfg.session_limit_usd is not None:
            spent = self.session_cost()
            if spent >= cfg.session_limit_usd:
                return (
                    f"Session budget exhausted: "
                    f"${spent:.4f} >= ${cfg.session_limit_usd:.4f}"
                )

        if cfg.daily_limit_usd is None and cfg.total_limit_usd is None:
            return None

        all_records = self._load_records() + self._session_records

        if cfg.daily_limit_usd is not None:
            today = self._now().strftime("%Y-%m-%d")
            daily_spent = sum(
                r.cost_usd for r in all_records if r.timestamp.startswith(today)
            )
            if daily_spent >= cfg.daily_limit_usd:
                return (
                    f"Daily budget exhausted: "
                    f"${daily_spent:.4f} >= ${cfg.daily_limit_usd:.4f}"
                )

        if cfg.total_limit_usd is not None:
            total_spent = sum(r.cost_usd for r in all_records)
            if total_spent >= cfg.total_limit_usd:
                return (
                    f"Total budget exhausted: "
                    f"${total_spent:.4f} >= ${cfg.total_limit_usd:.4f}"
                )

        return None

    def should_pause(self) -> bool:
        """Return True when any configured limit has been reached."""
        return self.check_limits() is not None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_records(self) -> list[UsageRecord]:
        """Load persisted records from disk (returns empty list if file missing or corrupt)."""
        if not self.usage_path.exists():
            return []
        try:
            data = json.loads(self.usage_path.read_text(encoding="utf-8"))
            return [UsageRecord(**r) for r in data.get("records", [])]
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return []

    def save(self) -> Path:
        """
        Append session records to the on-disk JSON file and clear the
        in-memory session list. Returns the path of the written file.
        """
        existing = self._load_records()
        all_records = existing + self._session_records
        payload = {"records": [asdict(r) for r in all_records]}
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        self.usage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._session_records.clear()
        return self.usage_path

    def load(self) -> list[UsageRecord]:
        """Load and return all persisted records (does not affect session state)."""
        return self._load_records()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self, output_path: Optional[Path] = None) -> Path:
        """Write a Markdown budget report and return the path of the written file."""
        if output_path is None:
            output_path = DEFAULT_REPORT_PATH

        all_records = self._load_records() + self._session_records
        total_cost = sum(r.cost_usd for r in all_records)
        total_input = sum(r.input_tokens for r in all_records)
        total_output = sum(r.output_tokens for r in all_records)
        session_cost = self.session_cost()

        ts = self._now().strftime("%Y-%m-%d %H:%M UTC")
        cfg = self.config
        today = self._now().strftime("%Y-%m-%d")
        daily_cost = sum(r.cost_usd for r in all_records if r.timestamp.startswith(today))

        lines: list[str] = [
            "# Budget Report",
            "",
            f"*Generated: {ts}*",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total calls recorded | {len(all_records)} |",
            f"| Total input tokens | {total_input:,} |",
            f"| Total output tokens | {total_output:,} |",
            f"| Total cost (USD) | ${total_cost:.6f} |",
            f"| Session cost (USD) | ${session_cost:.6f} |",
            "",
            "## Limits",
            "",
            "| Limit | Configured | Status |",
            "|-------|-----------|--------|",
        ]

        def _limit_row(label: str, limit: Optional[float], spent: float) -> str:
            configured = f"${limit:.4f}" if limit is not None else "—"
            if limit is None:
                status = "no limit"
            elif spent >= limit:
                status = f"**EXCEEDED** (${spent:.4f})"
            else:
                status = f"OK (${spent:.4f} / ${limit:.4f})"
            return f"| {label} | {configured} | {status} |"

        lines.append(_limit_row("Session", cfg.session_limit_usd, session_cost))
        lines.append(_limit_row("Daily", cfg.daily_limit_usd, daily_cost))
        lines.append(_limit_row("Total (lifetime)", cfg.total_limit_usd, total_cost))
        lines.append("")

        if all_records:
            lines += ["## Call Log", ""]
            lines += ["| Timestamp | Model | In Tok | Out Tok | Cost (USD) | Task |"]
            lines += ["|-----------|-------|--------|---------|------------|------|"]
            for r in all_records:
                lines.append(
                    f"| {r.timestamp} | {r.model} | {r.input_tokens:,} |"
                    f" {r.output_tokens:,} | ${r.cost_usd:.6f} | {r.task_filename or '—'} |"
                )
            lines.append("")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
