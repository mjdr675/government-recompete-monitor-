"""
Tests for ai_agent/pr_builder.py — GitHub PR draft generation.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ai_agent.pr_builder import (
    PRDraft,
    build_pr_draft,
    _get_changed_files,
    _get_commits,
    _get_completed_tasks,
    _generate_title,
    _generate_description,
    _run_tests,
    _slug,
)


# ---------------------------------------------------------------------------
# _get_changed_files
# ---------------------------------------------------------------------------

class TestGetChangedFiles:
    def test_returns_list_of_files(self, tmp_path):
        with patch("ai_agent.pr_builder._git", return_value="file1.py\nfile2.py"):
            files = _get_changed_files("main", repo_root=tmp_path)
        assert files == ["file1.py", "file2.py"]

    def test_returns_empty_on_no_output(self, tmp_path):
        with patch("ai_agent.pr_builder._git", return_value=""):
            files = _get_changed_files("main", repo_root=tmp_path)
        assert files == []

    def test_filters_blank_lines(self, tmp_path):
        with patch("ai_agent.pr_builder._git", return_value="app.py\n\ndb.py\n"):
            files = _get_changed_files("main", repo_root=tmp_path)
        assert files == ["app.py", "db.py"]


# ---------------------------------------------------------------------------
# _get_commits
# ---------------------------------------------------------------------------

class TestGetCommits:
    def test_returns_commit_list(self, tmp_path):
        output = "abc1234 feat: add feature\ndef5678 fix: fix bug"
        with patch("ai_agent.pr_builder._git", return_value=output):
            commits = _get_commits("main", repo_root=tmp_path)
        assert len(commits) == 2
        assert "feat: add feature" in commits[0]

    def test_returns_empty_on_no_commits(self, tmp_path):
        with patch("ai_agent.pr_builder._git", return_value=""):
            commits = _get_commits("main", repo_root=tmp_path)
        assert commits == []

    def test_filters_blank_lines(self, tmp_path):
        with patch("ai_agent.pr_builder._git", return_value="abc1234 msg\n\n"):
            commits = _get_commits("main", repo_root=tmp_path)
        assert len(commits) == 1


# ---------------------------------------------------------------------------
# _get_completed_tasks
# ---------------------------------------------------------------------------

class TestGetCompletedTasks:
    def test_returns_sorted_task_stems(self, tmp_path):
        done_dir = tmp_path / "done"
        done_dir.mkdir()
        (done_dir / "049-pr-builder.md").write_text("task")
        (done_dir / "048-ai-reviewer.md").write_text("task")
        tasks = _get_completed_tasks(done_dir)
        assert tasks == ["048-ai-reviewer", "049-pr-builder"]

    def test_returns_empty_when_dir_missing(self, tmp_path):
        tasks = _get_completed_tasks(tmp_path / "nonexistent")
        assert tasks == []

    def test_returns_empty_when_dir_is_empty(self, tmp_path):
        done_dir = tmp_path / "done"
        done_dir.mkdir()
        assert _get_completed_tasks(done_dir) == []

    def test_only_includes_md_files(self, tmp_path):
        done_dir = tmp_path / "done"
        done_dir.mkdir()
        (done_dir / "049-task.md").write_text("task")
        (done_dir / "readme.txt").write_text("not a task")
        tasks = _get_completed_tasks(done_dir)
        assert tasks == ["049-task"]
        assert "readme" not in tasks


# ---------------------------------------------------------------------------
# _generate_title
# ---------------------------------------------------------------------------

class TestGenerateTitle:
    def test_generates_title_from_numbered_task(self):
        title = _generate_title([], ["049-github-pr-builder"])
        assert "049" in title
        assert "Github Pr Builder" in title or "PR Builder" in title

    def test_uses_last_task_when_multiple(self):
        title = _generate_title([], ["048-reviewer", "049-pr-builder"])
        assert "049" in title

    def test_falls_back_to_commit_when_no_tasks(self):
        title = _generate_title(["abc1234 feat: add pr builder"], [])
        assert "feat: add pr builder" in title

    def test_default_when_no_data(self):
        title = _generate_title([], [])
        assert len(title) > 0
        assert "update" in title.lower() or "automated" in title.lower()

    def test_handles_unnumbered_task(self):
        title = _generate_title([], ["some-task-name"])
        assert len(title) > 0


# ---------------------------------------------------------------------------
# _generate_description
# ---------------------------------------------------------------------------

class TestGenerateDescription:
    def test_includes_changed_files_section(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=["app.py", "db.py"],
            commits=[],
            test_summary="3 passed",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "## Changed Files" in desc
        assert "`app.py`" in desc
        assert "`db.py`" in desc

    def test_includes_commits_section(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=[],
            commits=["abc1234 feat: something"],
            test_summary="0 passed",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "## Commits" in desc
        assert "abc1234 feat: something" in desc

    def test_includes_tests_section(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=[],
            commits=[],
            test_summary="100 passed in 5s",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "## Tests" in desc
        assert "100 passed" in desc

    def test_includes_completed_tasks_when_present(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=["049-pr-builder"],
            changed_files=[],
            commits=[],
            test_summary="ok",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "049-pr-builder" in desc
        assert "Completed Tasks" in desc

    def test_omits_tasks_section_when_empty(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=[],
            commits=[],
            test_summary="ok",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "Completed Tasks" not in desc

    def test_shows_placeholder_for_empty_files(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=[],
            commits=[],
            test_summary="ok",
            base_branch="main",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "no" in desc.lower()

    def test_includes_base_branch_attribution(self):
        desc = _generate_description(
            title="Test PR",
            completed_tasks=[],
            changed_files=[],
            commits=[],
            test_summary="ok",
            base_branch="develop",
            generated_at="2026-06-20 12:00 UTC",
        )
        assert "develop" in desc


# ---------------------------------------------------------------------------
# _slug
# ---------------------------------------------------------------------------

class TestSlug:
    def test_lowercases_and_replaces_spaces(self):
        assert _slug("Hello World") == "hello_world"

    def test_truncates_to_40_chars(self):
        long_input = "a" * 100
        result = _slug(long_input)
        assert len(result) <= 40

    def test_strips_leading_trailing_underscores(self):
        assert not _slug("  test  ").startswith("_")
        assert not _slug("  test  ").endswith("_")


# ---------------------------------------------------------------------------
# _run_tests
# ---------------------------------------------------------------------------

class TestRunTests:
    def test_returns_summary_line(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = "collected 5 items\n.\n5 passed in 0.5s\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            summary = _run_tests(tmp_path)
        assert "5 passed" in summary

    def test_returns_fallback_when_no_output(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            summary = _run_tests(tmp_path)
        assert summary == "(no test output)"


# ---------------------------------------------------------------------------
# build_pr_draft — integration
# ---------------------------------------------------------------------------

class TestBuildPrDraft:
    def _make_done_dir(self, tmp_path: Path, *tasks: str) -> Path:
        done_dir = tmp_path / "done"
        done_dir.mkdir(exist_ok=True)
        for task in tasks:
            (done_dir / f"{task}.md").write_text("task")
        return done_dir

    def test_creates_draft_file(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path, "049-pr-builder")
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                run_tests=False,
                repo_root=tmp_path,
                drafts_dir=drafts_dir,
                done_dir=done_dir,
            )

        assert draft.draft_path is not None
        assert draft.draft_path.exists()
        assert draft.draft_path.suffix == ".md"

    def test_draft_contains_pr_header(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        content = draft.draft_path.read_text()
        assert content.startswith("# PR Draft:")

    def test_draft_includes_completed_tasks(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path, "048-ai-reviewer", "049-pr-builder")
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert "048-ai-reviewer" in draft.completed_tasks
        assert "049-pr-builder" in draft.completed_tasks
        content = draft.draft_path.read_text()
        assert "048-ai-reviewer" in content

    def test_draft_includes_changed_files(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value="app.py\ntests/test_app.py"):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert "app.py" in draft.changed_files
        assert "tests/test_app.py" in draft.changed_files
        content = draft.draft_path.read_text()
        assert "app.py" in content

    def test_draft_includes_commits(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value="abc1234 feat: add pr builder"):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert len(draft.commits) == 1
        assert "feat: add pr builder" in draft.commits[0]
        content = draft.draft_path.read_text()
        assert "feat: add pr builder" in content

    def test_run_tests_false_uses_placeholder(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                run_tests=False,
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert "tests not run" in draft.test_summary.lower()

    def test_run_tests_true_calls_pytest(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""), \
             patch("ai_agent.pr_builder._run_tests", return_value="42 passed in 3s") as mock_run:
            draft = build_pr_draft(
                base_branch="main",
                run_tests=True,
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        mock_run.assert_called_once()
        assert "42 passed" in draft.test_summary

    def test_creates_drafts_dir_if_missing(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "nested" / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert drafts_dir.exists()
        assert draft.draft_path.exists()

    def test_filename_contains_slug_of_title(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path, "049-github-pr-builder")
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="main",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert "049" in draft.draft_path.name or "github" in draft.draft_path.name

    def test_returns_pr_draft_dataclass(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert isinstance(draft, PRDraft)
        assert isinstance(draft.title, str)
        assert isinstance(draft.changed_files, list)
        assert isinstance(draft.commits, list)
        assert isinstance(draft.completed_tasks, list)

    def test_draft_records_base_branch(self, tmp_path):
        done_dir = self._make_done_dir(tmp_path)
        drafts_dir = tmp_path / "pr_drafts"

        with patch("ai_agent.pr_builder._git", return_value=""):
            draft = build_pr_draft(
                base_branch="develop",
                drafts_dir=drafts_dir,
                done_dir=done_dir,
                repo_root=tmp_path,
            )

        assert draft.base_branch == "develop"
        assert "develop" in draft.draft_path.read_text()
