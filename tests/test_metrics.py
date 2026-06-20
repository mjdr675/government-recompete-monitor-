"""
Tests for ai_agent/metrics.py — engineering metrics collection and reporting.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_agent.metrics import (
    EngMetrics,
    TaskMetrics,
    _count_tests,
    _get_commit_history,
    _parse_log,
    _parse_logs,
    collect_metrics,
    generate_metrics_report,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _write_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_metrics(**overrides) -> EngMetrics:
    defaults = dict(
        tasks_completed=5,
        tasks_failed=1,
        success_rate=5 / 6,
        total_retries=2,
        avg_time_seconds=12.5,
        test_count=100,
        commit_history=["abc1234 feat: add thing"],
        task_details=[],
        generated_at="2026-06-20 12:00 UTC",
    )
    defaults.update(overrides)
    return EngMetrics(**defaults)


# ---------------------------------------------------------------------------
# _parse_log
# ---------------------------------------------------------------------------

class TestParseLog:
    def test_parses_elapsed_from_done_line(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "[2026-06-20 10:00:00 UTC] DONE   commit=abc1234 elapsed=8.3s\n")
        t = _parse_log(log)
        assert t.elapsed_seconds == pytest.approx(8.3)

    def test_parses_elapsed_from_failed_line(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "[2026-06-20 10:00:00 UTC] FAILED error msg elapsed=2.1s\n")
        t = _parse_log(log)
        assert t.elapsed_seconds == pytest.approx(2.1)

    def test_counts_retries(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, (
            "[...] RETRY  attempt=2/3 category=test_failure\n"
            "[...] RETRY  attempt=3/3 category=test_failure\n"
        ))
        t = _parse_log(log)
        assert t.retries == 2

    def test_extracts_commit_sha(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "[2026-06-20 10:00:00 UTC] DONE   commit=deadbeef elapsed=5.0s\n")
        t = _parse_log(log)
        assert t.commit_sha == "deadbeef"

    def test_extracts_role(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "[...] ROLE   backend\n")
        t = _parse_log(log)
        assert t.role == "backend"

    def test_status_failed_when_fail_line_present(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "FAIL  2026-06-20 10:00 UTC some error\n")
        t = _parse_log(log)
        assert t.status == "failed"

    def test_status_completed_when_done_line_present(self, tmp_path):
        log = tmp_path / "task-001.log"
        _write_log(log, "[...] DONE   commit=abc1234 elapsed=5.0s\n")
        t = _parse_log(log)
        assert t.status == "completed"

    def test_uses_stem_as_filename(self, tmp_path):
        log = tmp_path / "049-pr-builder.log"
        _write_log(log, "")
        t = _parse_log(log)
        assert t.filename == "049-pr-builder"

    def test_handles_missing_file(self, tmp_path):
        t = _parse_log(tmp_path / "nonexistent.log")
        assert t.status == "unknown"

    def test_no_elapsed_when_not_present(self, tmp_path):
        log = tmp_path / "task.log"
        _write_log(log, "[...] ROLE   qa\n")
        t = _parse_log(log)
        assert t.elapsed_seconds is None

    def test_no_retries_when_none(self, tmp_path):
        log = tmp_path / "task.log"
        _write_log(log, "[...] DONE   commit=abc elapsed=3.0s\n")
        t = _parse_log(log)
        assert t.retries == 0


# ---------------------------------------------------------------------------
# _parse_logs
# ---------------------------------------------------------------------------

class TestParseLogs:
    def test_parses_multiple_logs(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        _write_log(logs / "task-001.log", "[...] DONE   commit=aaa elapsed=5.0s\n")
        _write_log(logs / "task-002.log", "[...] DONE   commit=bbb elapsed=7.0s\n")
        results = _parse_logs(logs)
        assert len(results) == 2

    def test_skips_daemon_log(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        _write_log(logs / "daemon.log", "daemon started\n")
        _write_log(logs / "task-001.log", "[...] DONE   commit=aaa elapsed=5.0s\n")
        results = _parse_logs(logs)
        filenames = [r.filename for r in results]
        assert "daemon" not in filenames
        assert "task-001" in filenames

    def test_skips_claude_pro_waiter_log(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        _write_log(logs / "claude-pro-waiter.log", "waiting\n")
        _write_log(logs / "task-001.log", "[...] DONE   commit=aaa elapsed=5.0s\n")
        results = _parse_logs(logs)
        filenames = [r.filename for r in results]
        assert "claude-pro-waiter" not in filenames

    def test_returns_empty_when_dir_missing(self, tmp_path):
        assert _parse_logs(tmp_path / "nonexistent") == []

    def test_returns_sorted_by_filename(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        _write_log(logs / "task-003.log", "")
        _write_log(logs / "task-001.log", "")
        _write_log(logs / "task-002.log", "")
        results = _parse_logs(logs)
        filenames = [r.filename for r in results]
        assert filenames == sorted(filenames)


# ---------------------------------------------------------------------------
# _get_commit_history
# ---------------------------------------------------------------------------

class TestGetCommitHistory:
    def test_returns_commit_list(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 feat: add thing\ndef5678 fix: bug\n"
        with patch("subprocess.run", return_value=mock_result):
            commits = _get_commit_history(tmp_path)
        assert len(commits) == 2
        assert "feat: add thing" in commits[0]

    def test_returns_empty_on_git_error(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            commits = _get_commit_history(tmp_path)
        assert commits == []

    def test_filters_blank_lines(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 msg\n\n"
        with patch("subprocess.run", return_value=mock_result):
            commits = _get_commit_history(tmp_path)
        assert len(commits) == 1


# ---------------------------------------------------------------------------
# _count_tests
# ---------------------------------------------------------------------------

class TestCountTests:
    def test_parses_collected_count(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = "496 tests collected in 2.1s\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            count = _count_tests(tmp_path)
        assert count == 496

    def test_returns_zero_when_no_match(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = "no output\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            count = _count_tests(tmp_path)
        assert count == 0

    def test_parses_from_stderr_too(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "42 tests collected in 0.5s\n"
        with patch("subprocess.run", return_value=mock_result):
            count = _count_tests(tmp_path)
        assert count == 42


# ---------------------------------------------------------------------------
# collect_metrics
# ---------------------------------------------------------------------------

class TestCollectMetrics:
    def _setup(self, tmp_path: Path):
        done = tmp_path / "done"
        done.mkdir()
        failed = tmp_path / "failed"
        failed.mkdir()
        logs = tmp_path / "logs"
        logs.mkdir()
        return done, failed, logs

    def test_counts_completed_tasks(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)
        (done / "task-001.md").write_text("done")
        (done / "task-002.md").write_text("done")

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.tasks_completed == 2

    def test_counts_failed_tasks(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)
        (failed / "task-bad.md").write_text("failed")

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.tasks_failed == 1

    def test_calculates_success_rate(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)
        (done / "t1.md").write_text("done")
        (done / "t2.md").write_text("done")
        (done / "t3.md").write_text("done")
        (failed / "t4.md").write_text("failed")

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.success_rate == pytest.approx(0.75)

    def test_success_rate_zero_when_no_tasks(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.success_rate == 0.0

    def test_sums_retries_from_logs(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)
        _write_log(logs / "t1.log", "[...] RETRY  attempt=2/3\n[...] RETRY  attempt=3/3\n")
        _write_log(logs / "t2.log", "[...] RETRY  attempt=2/3\n")

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.total_retries == 3

    def test_calculates_avg_time(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)
        _write_log(logs / "t1.log", "[...] DONE   commit=aaa elapsed=10.0s\n")
        _write_log(logs / "t2.log", "[...] DONE   commit=bbb elapsed=20.0s\n")

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.avg_time_seconds == pytest.approx(15.0)

    def test_avg_time_none_when_no_elapsed(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.avg_time_seconds is None

    def test_run_tests_false_yields_zero_count(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)

        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.test_count == 0

    def test_run_tests_true_calls_count_tests(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)

        with patch("ai_agent.metrics._get_commit_history", return_value=[]), \
             patch("ai_agent.metrics._count_tests", return_value=99) as mock_ct:
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=True)

        mock_ct.assert_called_once()
        assert m.test_count == 99

    def test_includes_commit_history(self, tmp_path):
        done, failed, logs = self._setup(tmp_path)

        with patch("ai_agent.metrics._get_commit_history", return_value=["abc feat: thing"]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.commit_history == ["abc feat: thing"]

    def test_handles_missing_done_and_failed_dirs(self, tmp_path):
        with patch("ai_agent.metrics._get_commit_history", return_value=[]):
            m = collect_metrics(agent_dir=tmp_path, repo_root=tmp_path, run_tests=False)

        assert m.tasks_completed == 0
        assert m.tasks_failed == 0


# ---------------------------------------------------------------------------
# generate_metrics_report
# ---------------------------------------------------------------------------

class TestGenerateMetricsReport:
    def test_creates_file(self, tmp_path):
        m = _make_metrics()
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        assert path.exists()

    def test_file_starts_with_header(self, tmp_path):
        m = _make_metrics()
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert content.startswith("# Engineering Metrics")

    def test_includes_summary_table(self, tmp_path):
        m = _make_metrics(tasks_completed=10, tasks_failed=2, success_rate=10 / 12)
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "Tasks completed" in content
        assert "10" in content
        assert "Tasks failed" in content

    def test_includes_success_rate(self, tmp_path):
        m = _make_metrics(tasks_completed=3, tasks_failed=1, success_rate=0.75)
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "75.0%" in content

    def test_includes_test_count(self, tmp_path):
        m = _make_metrics(test_count=496)
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "496" in content

    def test_includes_commit_history(self, tmp_path):
        m = _make_metrics(commit_history=["abc1234 feat: something cool"])
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "feat: something cool" in content

    def test_includes_task_details_table(self, tmp_path):
        task = TaskMetrics(
            filename="049-pr-builder",
            status="completed",
            elapsed_seconds=12.5,
            retries=1,
            commit_sha="abc1234",
            role="backend",
        )
        m = _make_metrics(task_details=[task])
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "049-pr-builder" in content
        assert "12.5s" in content
        assert "abc1234"[:7] in content

    def test_shows_na_when_avg_time_is_none(self, tmp_path):
        m = _make_metrics(avg_time_seconds=None)
        path = generate_metrics_report(m, output_path=tmp_path / "metrics.md")
        content = path.read_text()
        assert "n/a" in content

    def test_creates_parent_dirs(self, tmp_path):
        m = _make_metrics()
        path = generate_metrics_report(m, output_path=tmp_path / "nested" / "dir" / "metrics.md")
        assert path.exists()

    def test_uses_default_path_when_none(self, tmp_path):
        m = _make_metrics()
        with patch("ai_agent.metrics.METRICS_PATH", tmp_path / "metrics.md"):
            path = generate_metrics_report(m)
        assert path.exists()

    def test_overwrites_previous_report(self, tmp_path):
        out = tmp_path / "metrics.md"
        m1 = _make_metrics(tasks_completed=1)
        generate_metrics_report(m1, output_path=out)
        m2 = _make_metrics(tasks_completed=99)
        generate_metrics_report(m2, output_path=out)
        content = out.read_text()
        assert "99" in content
