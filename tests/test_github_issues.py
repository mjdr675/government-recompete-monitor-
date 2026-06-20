"""
Tests for ai_agent/github_issues.py — GitHub Issues Sync.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_agent.github_issues import (
    SyncResult,
    _already_imported,
    _detect_repo,
    _fetch_via_api,
    _fetch_via_gh,
    _gh_available,
    _slug,
    fetch_issues,
    issue_to_content,
    issue_to_filename,
    sync_issues,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(number: int, title: str = "Test issue", body: str = "", labels=None) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "state": "OPEN",
        "url": f"https://github.com/owner/repo/issues/{number}",
    }


# ---------------------------------------------------------------------------
# _detect_repo
# ---------------------------------------------------------------------------

class TestDetectRepo:
    def test_parses_https_url(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/my-repo\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_repo(tmp_path) == "owner/my-repo"

    def test_parses_https_git_suffix(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_repo(tmp_path) == "owner/repo"

    def test_parses_ssh_url(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_repo(tmp_path) == "owner/repo"

    def test_returns_none_on_git_error(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_repo(tmp_path) is None

    def test_returns_none_for_non_github_remote(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://gitlab.com/owner/repo.git\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _detect_repo(tmp_path) is None


# ---------------------------------------------------------------------------
# _gh_available
# ---------------------------------------------------------------------------

class TestGhAvailable:
    def test_returns_true_when_authenticated(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert _gh_available() is True

    def test_returns_false_when_not_authenticated(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            assert _gh_available() is False


# ---------------------------------------------------------------------------
# _fetch_via_gh
# ---------------------------------------------------------------------------

class TestFetchViaGh:
    def test_returns_parsed_issues(self):
        issues = [_issue(1, "Bug fix"), _issue(2, "Feature")]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(issues)
        with patch("subprocess.run", return_value=mock_result):
            result = _fetch_via_gh("owner/repo")
        assert len(result) == 2
        assert result[0]["number"] == 1

    def test_raises_on_nonzero_exit(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "authentication required"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="gh issue list failed"):
                _fetch_via_gh("owner/repo")

    def test_returns_empty_list_for_empty_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"
        with patch("subprocess.run", return_value=mock_result):
            result = _fetch_via_gh("owner/repo")
        assert result == []


# ---------------------------------------------------------------------------
# _fetch_via_api
# ---------------------------------------------------------------------------

class TestFetchViaApi:
    def test_returns_issues_without_prs(self):
        api_response = [
            {"number": 1, "title": "Bug", "pull_request": {}},  # PR — excluded
            {"number": 2, "title": "Feature"},                   # issue — included
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = api_response
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            result = _fetch_via_api("owner/repo", "fake-token")
        assert len(result) == 1
        assert result[0]["number"] == 2

    def test_raises_on_http_error(self):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(req.HTTPError):
                _fetch_via_api("owner/repo", "bad-token")


# ---------------------------------------------------------------------------
# fetch_issues
# ---------------------------------------------------------------------------

class TestFetchIssues:
    def test_uses_gh_when_available(self):
        issues = [_issue(1, "Test")]
        with patch("ai_agent.github_issues._gh_available", return_value=True), \
             patch("ai_agent.github_issues._fetch_via_gh", return_value=issues) as mock_gh:
            result = fetch_issues("owner/repo")
        mock_gh.assert_called_once_with("owner/repo", limit=100)
        assert result == issues

    def test_falls_back_to_api_when_gh_unavailable(self):
        issues = [_issue(1, "Test")]
        with patch("ai_agent.github_issues._gh_available", return_value=False), \
             patch("os.environ.get", return_value="fake-token"), \
             patch("ai_agent.github_issues._fetch_via_api", return_value=issues) as mock_api:
            result = fetch_issues("owner/repo")
        mock_api.assert_called_once_with("owner/repo", "fake-token", limit=100)
        assert result == issues

    def test_raises_when_no_credentials(self):
        with patch("ai_agent.github_issues._gh_available", return_value=False), \
             patch("os.environ.get", return_value=""):
            with pytest.raises(RuntimeError, match="No GitHub credentials"):
                fetch_issues("owner/repo")


# ---------------------------------------------------------------------------
# issue_to_filename
# ---------------------------------------------------------------------------

class TestIssueToFilename:
    def test_uses_four_digit_number(self):
        name = issue_to_filename(1, "Bug fix")
        assert name.startswith("issue-0001-")

    def test_slugifies_title(self):
        name = issue_to_filename(42, "Fix login bug!")
        assert "fix_login_bug" in name

    def test_has_md_extension(self):
        assert issue_to_filename(1, "Test").endswith(".md")

    def test_four_digit_padding(self):
        name = issue_to_filename(999, "Test")
        assert name.startswith("issue-0999-")

    def test_large_number(self):
        name = issue_to_filename(10000, "Test")
        assert name.startswith("issue-10000-")


# ---------------------------------------------------------------------------
# issue_to_content
# ---------------------------------------------------------------------------

class TestIssueToContent:
    def test_includes_title_and_number(self):
        content = issue_to_content(_issue(7, "Add pagination"))
        assert "# Issue #7: Add pagination" in content

    def test_includes_body(self):
        content = issue_to_content(_issue(1, "Bug", body="Steps to reproduce"))
        assert "Steps to reproduce" in content

    def test_includes_labels(self):
        content = issue_to_content(_issue(1, "Bug", labels=["bug", "high-priority"]))
        assert "bug" in content
        assert "high-priority" in content

    def test_includes_url(self):
        content = issue_to_content(_issue(3, "Feature"))
        assert "github.com" in content

    def test_handles_empty_body(self):
        content = issue_to_content(_issue(1, "No body"))
        assert "# Issue #1" in content  # should not crash

    def test_handles_missing_labels(self):
        issue = {"number": 1, "title": "No labels"}
        content = issue_to_content(issue)
        assert "# Issue #1" in content
        assert "Labels" not in content


# ---------------------------------------------------------------------------
# _already_imported
# ---------------------------------------------------------------------------

class TestAlreadyImported:
    def test_returns_true_when_file_exists_in_queue(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        (queue / "issue-0001-some-bug.md").write_text("task")
        assert _already_imported(1, [queue]) is True

    def test_returns_false_when_file_missing(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        assert _already_imported(99, [queue]) is False

    def test_checks_multiple_dirs(self, tmp_path):
        done = tmp_path / "done"
        done.mkdir()
        (done / "issue-0005-old-task.md").write_text("task")
        queue = tmp_path / "queue"
        queue.mkdir()
        assert _already_imported(5, [queue, done]) is True

    def test_returns_false_when_dirs_dont_exist(self, tmp_path):
        assert _already_imported(1, [tmp_path / "nonexistent"]) is False

    def test_different_number_not_duplicate(self, tmp_path):
        queue = tmp_path / "queue"
        queue.mkdir()
        (queue / "issue-0001-task.md").write_text("task")
        assert _already_imported(2, [queue]) is False


# ---------------------------------------------------------------------------
# _slug helper
# ---------------------------------------------------------------------------

class TestSlug:
    def test_lowercases(self):
        assert _slug("Hello") == "hello"

    def test_replaces_special_chars(self):
        assert _slug("Fix login bug!") == "fix_login_bug"

    def test_truncates_to_40(self):
        assert len(_slug("a" * 100)) <= 40


# ---------------------------------------------------------------------------
# sync_issues — integration
# ---------------------------------------------------------------------------

class TestSyncIssues:
    def _dirs(self, tmp_path: Path):
        q = tmp_path / "queue"
        d = tmp_path / "done"
        f = tmp_path / "failed"
        q.mkdir()
        return q, d, f

    def test_imports_new_issues(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        issues = [_issue(1, "First issue"), _issue(2, "Second issue")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        assert len(result.imported) == 2
        assert len(result.skipped) == 0
        assert len(result.errors) == 0
        assert (q / "issue-0001-first_issue.md").exists()
        assert (q / "issue-0002-second_issue.md").exists()

    def test_skips_duplicate_in_queue(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        (q / "issue-0001-already-there.md").write_text("existing")
        issues = [_issue(1, "First issue"), _issue(2, "New issue")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        assert len(result.imported) == 1
        assert len(result.skipped) == 1
        assert "issue-0002" in result.imported[0]

    def test_skips_duplicate_in_done(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        d.mkdir()
        (d / "issue-0003-done-task.md").write_text("completed")
        issues = [_issue(3, "Done issue"), _issue(4, "New issue")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        assert len(result.skipped) == 1
        assert len(result.imported) == 1

    def test_skips_duplicate_in_failed(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        f.mkdir()
        (f / "issue-0007-failed-task.md").write_text("failed")
        issues = [_issue(7, "Failed issue")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        assert len(result.skipped) == 1
        assert len(result.imported) == 0

    def test_preserves_issue_number_ordering(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        issues = [_issue(10, "Later"), _issue(3, "Earlier"), _issue(7, "Middle")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        # imported list should be in issue-number order
        numbers = [int(fn.split("-")[1]) for fn in result.imported]
        assert numbers == sorted(numbers)

    def test_dry_run_does_not_write_files(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        issues = [_issue(1, "New issue")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
            dry_run=True,
        )

        assert len(result.imported) == 1   # reported as imported
        assert not list(q.glob("issue-*.md"))  # but file not written

    def test_file_content_includes_title_and_body(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        issues = [_issue(5, "Feature request", body="Please add export")]

        sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        content = (q / "issue-0005-feature_request.md").read_text()
        assert "Feature request" in content
        assert "Please add export" in content

    def test_returns_error_when_no_repo(self, tmp_path):
        q, d, f = self._dirs(tmp_path)

        with patch("ai_agent.github_issues._detect_repo", return_value=None):
            result = sync_issues(
                queue_dir=q,
                done_dir=d,
                failed_dir=f,
                repo_root=tmp_path,
                issues=[],
            )

        assert len(result.errors) == 1
        assert "repo" in result.errors[0].lower()

    def test_returns_error_on_fetch_failure(self, tmp_path):
        q, d, f = self._dirs(tmp_path)

        with patch(
            "ai_agent.github_issues.fetch_issues",
            side_effect=RuntimeError("auth failed"),
        ):
            result = sync_issues(
                repo="owner/repo",
                queue_dir=q,
                done_dir=d,
                failed_dir=f,
            )

        assert len(result.errors) == 1
        assert "auth failed" in result.errors[0]

    def test_auto_detects_repo_from_git(self, tmp_path):
        q, d, f = self._dirs(tmp_path)

        with patch("ai_agent.github_issues._detect_repo", return_value="owner/auto-repo"), \
             patch("ai_agent.github_issues.fetch_issues", return_value=[]) as mock_fetch:
            result = sync_issues(
                queue_dir=q,
                done_dir=d,
                failed_dir=f,
                repo_root=tmp_path,
            )

        assert result.repo == "owner/auto-repo"
        mock_fetch.assert_called_once_with("owner/auto-repo")

    def test_creates_queue_dir_if_missing(self, tmp_path):
        q = tmp_path / "new_queue"
        d = tmp_path / "done"
        f = tmp_path / "failed"
        issues = [_issue(1, "Test")]

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=issues,
        )

        assert q.exists()
        assert len(result.imported) == 1

    def test_handles_issue_with_missing_number(self, tmp_path):
        q, d, f = self._dirs(tmp_path)
        bad_issue = {"title": "No number", "body": ""}

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=[bad_issue],
        )

        assert len(result.errors) == 1
        assert len(result.imported) == 0

    def test_empty_issue_list_is_a_noop(self, tmp_path):
        q, d, f = self._dirs(tmp_path)

        result = sync_issues(
            repo="owner/repo",
            queue_dir=q,
            done_dir=d,
            failed_dir=f,
            issues=[],
        )

        assert result.imported == []
        assert result.skipped == []
        assert result.errors == []
