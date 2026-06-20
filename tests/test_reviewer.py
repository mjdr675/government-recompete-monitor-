"""
Tests for ai_agent/reviewer.py — regex safety scan and AI quality review.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ai_agent.reviewer import (
    review,
    ai_review,
    _parse_review_response,
    _write_review,
)


# ---------------------------------------------------------------------------
# Stage 1 — regex review
# ---------------------------------------------------------------------------

class TestRegexReview:
    def test_clean_patch_passes(self):
        safe, violations = review("def add(a, b):\n    return a + b\n")
        assert safe
        assert violations == []

    def test_git_push_blocked(self):
        safe, violations = review("os.system('git push origin main')")
        assert not safe
        assert any("git push" in v for v in violations)

    def test_rm_rf_blocked(self):
        safe, violations = review("subprocess.run(['rm', '-rf', path])")
        assert not safe

    def test_drop_table_blocked(self):
        safe, violations = review("cursor.execute('DROP TABLE users')")
        assert not safe

    def test_hardcoded_api_key_blocked(self):
        safe, violations = review(
            "ANTHROPIC_API_KEY = 'sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ'"
        )
        assert not safe

    def test_multiple_violations_all_reported(self):
        patch_text = "git push\nrm -rf /tmp"
        safe, violations = review(patch_text)
        assert not safe
        assert len(violations) >= 2


# ---------------------------------------------------------------------------
# Stage 2 — response parsing
# ---------------------------------------------------------------------------

class TestParseReviewResponse:
    def test_parses_approved_with_none_finding(self):
        response = "DECISION: APPROVED\nFINDINGS:\n- None\n"
        approved, findings, decision = _parse_review_response(response)
        assert approved is True
        assert decision == "APPROVED"
        assert findings == ["No specific findings"]

    def test_parses_rejected_with_findings(self):
        response = (
            "DECISION: REJECTED\n"
            "FINDINGS:\n"
            "- Missing test for new route\n"
            "- SQL without parameterization\n"
        )
        approved, findings, decision = _parse_review_response(response)
        assert approved is False
        assert decision == "REJECTED"
        assert len(findings) == 2
        assert "Missing test" in findings[0]

    def test_parses_approved_with_minor_finding(self):
        response = "DECISION: APPROVED\nFINDINGS:\n- Consider adding a docstring\n"
        approved, findings, _ = _parse_review_response(response)
        assert approved is True
        assert len(findings) == 1

    def test_empty_response_defaults_to_approved(self):
        approved, findings, decision = _parse_review_response("")
        assert approved is True
        assert findings == ["No specific findings"]

    def test_case_insensitive_decision_parsing(self):
        response = "decision: rejected\nfindings:\n- Bug in loop\n"
        approved, findings, _ = _parse_review_response(response)
        assert approved is False


# ---------------------------------------------------------------------------
# Stage 2 — write_review helper
# ---------------------------------------------------------------------------

class TestWriteReview:
    def test_creates_file_with_expected_sections(self, tmp_path):
        path = tmp_path / "REVIEW.md"
        _write_review(path, "Task 056", "2026-06-20 10:00 UTC", "APPROVED", ["No issues"])
        content = path.read_text()
        assert "# AI Code Review" in content
        assert "Task 056" in content
        assert "APPROVED" in content
        assert "No issues" in content

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "REVIEW.md"
        _write_review(path, "test", "ts", "APPROVED", ["ok"])
        assert path.exists()

    def test_overwrites_previous_review(self, tmp_path):
        path = tmp_path / "REVIEW.md"
        _write_review(path, "Task A", "ts1", "APPROVED", ["ok"])
        _write_review(path, "Task B", "ts2", "REJECTED", ["bad"])
        content = path.read_text()
        assert "Task B" in content
        assert "Task A" not in content


# ---------------------------------------------------------------------------
# Stage 2 — ai_review end-to-end
# ---------------------------------------------------------------------------

class TestAiReview:
    def test_falls_back_when_llm_unavailable(self, tmp_path):
        review_path = tmp_path / "REVIEW.md"
        with patch("ai_agent.llm.available", return_value=False):
            approved, findings = ai_review(
                "def foo(): pass",
                task_title="test task",
                review_output_path=review_path,
            )
        assert approved is True
        assert any("unavailable" in f for f in findings)
        assert review_path.exists()

    def test_writes_review_md_on_approval(self, tmp_path):
        review_path = tmp_path / "REVIEW.md"
        mock_response = "DECISION: APPROVED\nFINDINGS:\n- None\n"
        with patch("ai_agent.llm.available", return_value=True), \
             patch("ai_agent.llm.call", return_value=mock_response):
            approved, findings = ai_review(
                "def add(a, b): return a + b",
                task_title="Task 056",
                review_output_path=review_path,
            )
        assert approved is True
        content = review_path.read_text()
        assert "Task 056" in content
        assert "APPROVED" in content

    def test_returns_false_on_rejection(self, tmp_path):
        review_path = tmp_path / "REVIEW.md"
        mock_response = (
            "DECISION: REJECTED\n"
            "FINDINGS:\n"
            "- SQL injection risk\n"
            "- Missing tests\n"
        )
        with patch("ai_agent.llm.available", return_value=True), \
             patch("ai_agent.llm.call", return_value=mock_response):
            approved, findings = ai_review(
                "db.execute('SELECT * FROM users WHERE id=' + uid)",
                task_title="Task X",
                review_output_path=review_path,
            )
        assert approved is False
        assert len(findings) >= 1
        assert "REJECTED" in review_path.read_text()

    def test_fails_open_on_llm_exception(self, tmp_path):
        review_path = tmp_path / "REVIEW.md"
        with patch("ai_agent.llm.available", return_value=True), \
             patch("ai_agent.llm.call", side_effect=RuntimeError("timeout")):
            approved, findings = ai_review(
                "def foo(): pass",
                review_output_path=review_path,
            )
        assert approved is True
        assert any("error" in f.lower() for f in findings)

    def test_uses_default_path_when_none_given(self, tmp_path):
        with patch("ai_agent.llm.available", return_value=False):
            approved, findings = ai_review("def foo(): pass")
        assert approved is True

    def test_truncates_large_patches(self, tmp_path):
        review_path = tmp_path / "REVIEW.md"
        large_patch = "x = 1\n" * 5000  # well over 8000 chars
        mock_response = "DECISION: APPROVED\nFINDINGS:\n- None\n"
        captured = []
        def capture_call(prompt, **kwargs):
            captured.append(prompt)
            return mock_response
        with patch("ai_agent.llm.available", return_value=True), \
             patch("ai_agent.llm.call", side_effect=capture_call):
            ai_review(large_patch, review_output_path=review_path)
        assert len(captured) == 1
        # the patch excerpt in the prompt must be bounded
        assert len(captured[0]) < len(large_patch) + 500
