"""
Unit tests for ai_agent/recovery.py.

Covers: FailureCategory classification, AttemptRecord creation, pattern
detection (repeated category, identical patch), feedback generation, early
cut-short logic, and failure report output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.recovery import (
    AttemptRecord,
    FailureCategory,
    RecoveryTracker,
    classify,
)


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("error,expected", [
    ("LLM error: rate limit exceeded",       FailureCategory.LLM_ERROR),
    ("LLM error: ANTHROPIC_API_KEY not set", FailureCategory.LLM_ERROR),
    ("anthropic not installed",              FailureCategory.LLM_ERROR),
    ("reviewer blocked: git push",           FailureCategory.REVIEWER_BLOCKED),
    ("reviewer blocked: rm -rf",             FailureCategory.REVIEWER_BLOCKED),
    ("patch validation failed: Before text not found in app.py", FailureCategory.VALIDATION_FAILED),
    ("Before text not found in calc.py",     FailureCategory.VALIDATION_FAILED),
    ("ambiguous match (3 occurrences)",      FailureCategory.VALIDATION_FAILED),
    ("tests failed after apply (rolled back)", FailureCategory.TEST_FAILED),
    ("post-apply pytest failed: 2 failed",   FailureCategory.TEST_FAILED),
    ("no new commit detected after apply",   FailureCategory.COMMIT_MISSING),
    ("commit_sha was None",                  FailureCategory.COMMIT_MISSING),
    ("something completely unrecognised",    FailureCategory.UNKNOWN),
])
def test_classify(error: str, expected: FailureCategory) -> None:
    assert classify(error) == expected


# ---------------------------------------------------------------------------
# RecoveryTracker.record()
# ---------------------------------------------------------------------------

def test_record_creates_attempt_record() -> None:
    tracker = RecoveryTracker("001-task.md", max_attempts=3)
    rec = tracker.record(1, "LLM error: timeout")
    assert isinstance(rec, AttemptRecord)
    assert rec.attempt == 1
    assert rec.category == FailureCategory.LLM_ERROR
    assert "timeout" in rec.error
    assert rec.timestamp  # non-empty ISO string


def test_record_stores_patch_hash_when_content_provided() -> None:
    tracker = RecoveryTracker("001.md")
    rec = tracker.record(1, "reviewer blocked: git push", patch_content="git push origin main")
    assert rec.patch_hash is not None
    assert len(rec.patch_hash) == 10  # first 10 chars of MD5


def test_record_no_patch_hash_without_content() -> None:
    tracker = RecoveryTracker("001.md")
    rec = tracker.record(1, "some error")
    assert rec.patch_hash is None


def test_record_uses_provided_category() -> None:
    tracker = RecoveryTracker("001.md")
    rec = tracker.record(1, "anything", category=FailureCategory.COMMIT_MISSING)
    assert rec.category == FailureCategory.COMMIT_MISSING


def test_record_appends_to_attempts_list() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error one")
    tracker.record(2, "error two")
    assert len(tracker.attempts) == 2


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

def test_has_repeated_category_false_with_single_attempt() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "tests failed after apply (rolled back)")
    assert tracker.has_repeated_category() is False


def test_has_repeated_category_false_with_different_categories() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "reviewer blocked: git push")
    tracker.record(2, "tests failed after apply (rolled back)")
    assert tracker.has_repeated_category() is False


def test_has_repeated_category_true_when_same() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "tests failed after apply (rolled back)")
    tracker.record(2, "tests failed after apply (rolled back)")
    assert tracker.has_repeated_category() is True


def test_has_identical_patch_false_with_single_attempt() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error", patch_content="patch A")
    assert tracker.has_identical_patch() is False


def test_has_identical_patch_false_with_different_patches() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error", patch_content="patch A")
    tracker.record(2, "error", patch_content="patch B")
    assert tracker.has_identical_patch() is False


def test_has_identical_patch_true_when_same_content() -> None:
    tracker = RecoveryTracker("001.md")
    same = "## Patch: calc.py\n### Before\n```\nold\n```\n### After\n```\nnew\n```"
    tracker.record(1, "error", patch_content=same)
    tracker.record(2, "error", patch_content=same)
    assert tracker.has_identical_patch() is True


def test_has_identical_patch_false_when_no_patch_hash() -> None:
    """If either attempt has no patch (e.g. LLM error), should not trigger."""
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "LLM error: timeout")          # no patch content
    tracker.record(2, "LLM error: timeout")          # no patch content
    assert tracker.has_identical_patch() is False


# ---------------------------------------------------------------------------
# should_cut_short()
# ---------------------------------------------------------------------------

def test_should_cut_short_false_with_no_attempts() -> None:
    assert RecoveryTracker("001.md").should_cut_short() is False


def test_should_cut_short_false_with_different_patches() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error", patch_content="patch A")
    tracker.record(2, "error", patch_content="patch B")
    assert tracker.should_cut_short() is False


def test_should_cut_short_true_when_identical_patch() -> None:
    tracker = RecoveryTracker("001.md")
    same_patch = "unchanged patch content"
    tracker.record(1, "reviewer blocked: rm -rf", patch_content=same_patch)
    tracker.record(2, "reviewer blocked: rm -rf", patch_content=same_patch)
    assert tracker.should_cut_short() is True


# ---------------------------------------------------------------------------
# build_feedback()
# ---------------------------------------------------------------------------

def test_build_feedback_empty_with_no_attempts() -> None:
    assert RecoveryTracker("001.md").build_feedback() == ""


def test_build_feedback_includes_all_recorded_failures() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "tests failed after apply (rolled back): assertion error")
    tracker.record(2, "reviewer blocked: git push")
    feedback = tracker.build_feedback()
    assert "tests failed" in feedback
    assert "reviewer blocked" in feedback


def test_build_feedback_includes_attempt_numbers() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "some error")
    tracker.record(2, "another error")
    feedback = tracker.build_feedback()
    assert "Attempt 1" in feedback
    assert "Attempt 2" in feedback


def test_build_feedback_warns_on_repeated_category() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "tests failed after apply (rolled back)")
    tracker.record(2, "tests failed after apply (rolled back)")
    feedback = tracker.build_feedback()
    assert "same failure category" in feedback.lower() or "repeated" in feedback.lower()


def test_build_feedback_warns_on_identical_patch() -> None:
    tracker = RecoveryTracker("001.md")
    same = "same patch content"
    tracker.record(1, "error", patch_content=same)
    tracker.record(2, "error", patch_content=same)
    feedback = tracker.build_feedback()
    assert "identical" in feedback.lower() or "same" in feedback.lower()


def test_build_feedback_instructs_different_approach() -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "reviewer blocked: git push", patch_content="git push")
    feedback = tracker.build_feedback()
    assert "address" in feedback.lower() or "patch" in feedback.lower()


# ---------------------------------------------------------------------------
# write_failure_report()
# ---------------------------------------------------------------------------

def test_write_failure_report_creates_file(tmp_path: Path) -> None:
    tracker = RecoveryTracker("044-example.md", max_attempts=3)
    tracker.record(1, "tests failed after apply (rolled back)")
    tracker.record(2, "patch validation failed: Before text not found")
    tracker.record(3, "tests failed after apply (rolled back)")

    report = tracker.write_failure_report(tmp_path / "logs")
    assert report.exists()
    assert report.name == "044-example-failure-report.md"


def test_write_failure_report_contains_attempt_history(tmp_path: Path) -> None:
    tracker = RecoveryTracker("044-example.md")
    tracker.record(1, "LLM error: rate limit")
    tracker.record(2, "reviewer blocked: rm -rf", patch_content="rm -rf /")
    tracker.record(3, "patch validation failed: Before text not found in app.py")

    report_text = tracker.write_failure_report(tmp_path / "logs").read_text()

    assert "Attempt 1" in report_text
    assert "Attempt 2" in report_text
    assert "Attempt 3" in report_text
    assert "LLM error" in report_text
    assert "reviewer blocked" in report_text
    assert "validation failed" in report_text


def test_write_failure_report_contains_metadata(tmp_path: Path) -> None:
    tracker = RecoveryTracker("001-task.md", max_attempts=3)
    tracker.record(1, "some error")
    report_text = tracker.write_failure_report(tmp_path / "logs").read_text()
    assert "001-task.md" in report_text
    assert "Attempts made:" in report_text
    assert "Generated:" in report_text


def test_write_failure_report_flags_repeated_category(tmp_path: Path) -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "tests failed after apply (rolled back)")
    tracker.record(2, "tests failed after apply (rolled back)")
    report_text = tracker.write_failure_report(tmp_path / "logs").read_text()
    assert "Repeated" in report_text or "repeated" in report_text


def test_write_failure_report_flags_identical_patch(tmp_path: Path) -> None:
    tracker = RecoveryTracker("001.md")
    same = "identical patch content"
    tracker.record(1, "error", patch_content=same)
    tracker.record(2, "error", patch_content=same)
    report_text = tracker.write_failure_report(tmp_path / "logs").read_text()
    assert "Identical" in report_text or "identical" in report_text


def test_write_failure_report_creates_logs_dir_if_missing(tmp_path: Path) -> None:
    logs_dir = tmp_path / "nested" / "logs"
    assert not logs_dir.exists()
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error")
    tracker.write_failure_report(logs_dir)
    assert logs_dir.exists()


def test_write_failure_report_includes_resolution_steps(tmp_path: Path) -> None:
    tracker = RecoveryTracker("001.md")
    tracker.record(1, "error")
    report_text = tracker.write_failure_report(tmp_path / "logs").read_text()
    assert "Resolution" in report_text


# ---------------------------------------------------------------------------
# MAX_PLAN_ATTEMPTS enforcement
# ---------------------------------------------------------------------------

def test_max_attempts_reflected_in_repr() -> None:
    tracker = RecoveryTracker("001.md", max_attempts=3)
    tracker.record(1, "error")
    assert "1/3" in repr(tracker)


def test_max_3_attempts_enforced_via_loop(tmp_path: Path) -> None:
    """Simulate the actual loop: exactly 3 attempts, report written on third."""
    tracker = RecoveryTracker("001.md", max_attempts=3)
    errors = [
        "tests failed after apply (rolled back)",
        "tests failed after apply (rolled back)",
        "tests failed after apply (rolled back)",
    ]
    for i, err in enumerate(errors, start=1):
        tracker.record(i, err, patch_content=f"patch-{i}")  # different each time
        is_last = i == 3
        if is_last or tracker.should_cut_short():
            report = tracker.write_failure_report(tmp_path / "logs")
            break

    assert len(tracker.attempts) == 3
    assert report.exists()


def test_cut_short_at_attempt_2_not_3(tmp_path: Path) -> None:
    """Identical patch on attempt 2 triggers cut-short before attempt 3."""
    tracker = RecoveryTracker("001.md", max_attempts=3)
    same_patch = "same patch every time"
    used_attempts = 0

    for i in range(1, 4):  # would go to 3 without cut-short
        used_attempts = i
        tracker.record(i, "reviewer blocked: git push", patch_content=same_patch)
        if i == 3 or tracker.should_cut_short():
            tracker.write_failure_report(tmp_path / "logs")
            break

    # Should have stopped at attempt 2 (identical patch detected)
    assert used_attempts == 2
    assert tracker.should_cut_short() is True
