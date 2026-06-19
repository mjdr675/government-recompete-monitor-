"""
Recovery tracking for the autonomous loop.

Records every attempt on a task, classifies failure types, detects stuck
patterns (repeated error category, identical patch), builds cumulative
feedback for retry prompts, and writes structured failure reports.

Exported:
  FailureCategory  — enum of classified error types
  AttemptRecord    — one recorded attempt (attempt #, category, error, patch hash)
  RecoveryTracker  — per-task retry state machine

Usage:
  tracker = RecoveryTracker("044-example.md", max_attempts=3)

  for attempt in range(1, 4):
      feedback = tracker.build_feedback() if attempt > 1 else ""
      try:
          result = do_work(feedback)
      except SomeError as exc:
          tracker.record(attempt, str(exc))
          if tracker.should_cut_short() or attempt == 3:
              report = tracker.write_failure_report(logs_dir)
              break
          continue
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

class FailureCategory(str, Enum):
    LLM_ERROR = "llm_error"               # API / network / key problems
    REVIEWER_BLOCKED = "reviewer_blocked"  # dangerous-pattern match
    VALIDATION_FAILED = "validation_failed"  # patch format / text mismatch
    TEST_FAILED = "test_failed"            # code applied but tests broke
    COMMIT_MISSING = "commit_missing"      # apply reported success but no SHA
    UNKNOWN = "unknown"


def classify(error: str) -> FailureCategory:
    """Map a plain-text error string to the closest FailureCategory."""
    e = error.lower()
    if "llm error" in e or "api key" in e or "rate limit" in e or "not installed" in e:
        return FailureCategory.LLM_ERROR
    if "reviewer blocked" in e or "dangerous" in e:
        return FailureCategory.REVIEWER_BLOCKED
    if (
        "validation failed" in e
        or "before text not found" in e
        or "not found" in e
        or "ambiguous" in e
    ):
        return FailureCategory.VALIDATION_FAILED
    if "test" in e or "pytest" in e or "rolled back" in e:
        return FailureCategory.TEST_FAILED
    if "commit" in e:
        return FailureCategory.COMMIT_MISSING
    return FailureCategory.UNKNOWN


def _patch_hash(content: Optional[str]) -> Optional[str]:
    if not content:
        return None
    return hashlib.md5(content.encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class AttemptRecord:
    """Immutable record of a single failed attempt."""
    attempt: int
    timestamp: str
    category: FailureCategory
    error: str
    patch_hash: Optional[str] = None  # first 10 chars of MD5 of patch content

    def one_line(self) -> str:
        return f"attempt {self.attempt} [{self.category}]: {self.error[:120]}"


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class RecoveryTracker:
    """
    Manages retry state for a single task.

    Responsibilities:
    - Record each failed attempt with structured metadata
    - Detect stuck patterns:
        • has_repeated_category() — same failure type across last two attempts
        • has_identical_patch()  — LLM produced the same patch twice
    - should_cut_short()        — True when continuing is provably pointless
    - build_feedback()          — cumulative prompt for the next retry
    - write_failure_report()    — detailed markdown report for human review
    """

    def __init__(self, task_filename: str, max_attempts: int = 3) -> None:
        self.task_filename = task_filename
        self.max_attempts = max_attempts
        self.attempts: list[AttemptRecord] = []

    # -- Recording --

    def record(
        self,
        attempt: int,
        error: str,
        *,
        category: Optional[FailureCategory] = None,
        patch_content: Optional[str] = None,
    ) -> AttemptRecord:
        """Record a failed attempt. Returns the created AttemptRecord."""
        rec = AttemptRecord(
            attempt=attempt,
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category if category is not None else classify(error),
            error=error,
            patch_hash=_patch_hash(patch_content),
        )
        self.attempts.append(rec)
        return rec

    # -- Pattern detection --

    def has_repeated_category(self) -> bool:
        """True when the last two recorded failures share the same category."""
        if len(self.attempts) < 2:
            return False
        return self.attempts[-1].category == self.attempts[-2].category

    def has_identical_patch(self) -> bool:
        """True when the last two recorded patches have the same hash — model is stuck."""
        if len(self.attempts) < 2:
            return False
        h1 = self.attempts[-2].patch_hash
        h2 = self.attempts[-1].patch_hash
        return h1 is not None and h2 is not None and h1 == h2

    def should_cut_short(self) -> bool:
        """
        True when burning another attempt is provably pointless.
        Triggered when the model generates the same patch twice — it has not
        incorporated any feedback, and a third identical attempt will also fail.
        """
        return self.has_identical_patch()

    # -- Retry prompt --

    def build_feedback(self) -> str:
        """
        Build a cumulative feedback string for the next retry prompt.
        Includes all recorded failures and any detected stuck patterns.
        """
        if not self.attempts:
            return ""

        lines: list[str] = ["## Previous Attempt Failures", ""]
        for rec in self.attempts:
            lines += [
                f"### Attempt {rec.attempt} ({rec.category})",
                rec.error[:400],
                "",
            ]

        if self.has_repeated_category():
            lines += [
                "**Warning:** The same failure category repeated across attempts.",
                "Try a substantially different approach — do not repeat the previous patch.",
                "",
            ]

        if self.has_identical_patch():
            lines += [
                "**Warning:** Your patch was identical to the previous attempt (same content hash).",
                "You must generate a different patch. Review the error above carefully.",
                "",
            ]

        lines += [
            "Please address ALL of the failures listed above in your next patch.",
            "Do not repeat any approach that has already failed.",
        ]
        return "\n".join(lines)

    # -- Failure report --

    def write_failure_report(self, logs_dir: Path) -> Path:
        """
        Write a structured markdown failure report to logs_dir/.
        Returns the path to the written file.
        """
        logs_dir.mkdir(parents=True, exist_ok=True)
        stem = self.task_filename.removesuffix(".md")
        report_path = logs_dir / f"{stem}-failure-report.md"

        lines: list[str] = [
            f"# Failure Report — {self.task_filename}",
            "",
            f"- **Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"- **Attempts made:** {len(self.attempts)} / {self.max_attempts}",
            f"- **Cut short early:** {self.should_cut_short()}",
            "",
            "## Attempt History",
            "",
        ]

        for rec in self.attempts:
            lines += [
                f"### Attempt {rec.attempt}",
                f"- **Timestamp:** {rec.timestamp}",
                f"- **Category:** {rec.category}",
                f"- **Patch hash:** {rec.patch_hash or 'N/A'}",
                "- **Error:**",
                "",
                f"  {rec.error[:600]}",
                "",
            ]

        # Analysis section
        analysis: list[str] = []
        if self.has_repeated_category():
            analysis.append(
                f"- Repeated failure category (`{self.attempts[-1].category}`) "
                "across multiple attempts — the model failed to recover."
            )
        if self.has_identical_patch():
            analysis.append(
                "- Identical patch content across attempts — the model did not "
                "incorporate feedback. Cutting short was correct."
            )
        if not analysis:
            analysis.append("- No stuck-loop pattern detected.")

        lines += ["## Analysis", ""] + analysis + [
            "",
            "## Resolution",
            "",
            "1. Review the error messages above and the full log in `ai_agent/logs/`",
            "2. Rewrite or clarify the task specification",
            "3. Check for codebase issues the model may be hitting",
            "",
        ]

        report_path.write_text("\n".join(lines))
        return report_path

    # -- Introspection --

    def __repr__(self) -> str:
        return (
            f"RecoveryTracker({self.task_filename!r}, "
            f"attempts={len(self.attempts)}/{self.max_attempts})"
        )
