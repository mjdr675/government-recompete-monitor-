"""
Unit tests for QueueManager in ai_agent/manager.py.

All tests use isolated tmp_path directories — no global state touched.
"""

import json
from pathlib import Path

import pytest

from ai_agent.manager import QueueManager, TaskState, TaskInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dirs(tmp_path: Path) -> dict[str, Path]:
    q = tmp_path / "queue"
    d = tmp_path / "done"
    f = tmp_path / "failed"
    lo = tmp_path / "logs"
    q.mkdir()
    d.mkdir()
    f.mkdir()
    # logs dir intentionally not created — manager should create it on demand
    return {
        "queue": q,
        "done": d,
        "failed": f,
        "logs": lo,
        "report": tmp_path / "morning_report.md",
        "state": tmp_path / ".queue_state.json",
    }


def make_mgr(dirs: dict[str, Path]) -> QueueManager:
    return QueueManager(
        queue_dir=dirs["queue"],
        done_dir=dirs["done"],
        failed_dir=dirs["failed"],
        logs_dir=dirs["logs"],
        report_path=dirs["report"],
        state_file=dirs["state"],
    )


def add_task(dirs: dict[str, Path], name: str, folder: str = "queue") -> Path:
    path = dirs[folder] / name
    path.write_text(f"# Task: {name}\n")
    return path


# ---------------------------------------------------------------------------
# all_tasks / discovery
# ---------------------------------------------------------------------------

def test_empty_queue_returns_no_tasks(dirs):
    mgr = make_mgr(dirs)
    assert mgr.all_tasks() == []


def test_queued_files_detected(dirs):
    add_task(dirs, "001-alpha.md")
    add_task(dirs, "002-beta.md")
    mgr = make_mgr(dirs)
    tasks = mgr.all_tasks()
    assert len(tasks) == 2
    assert all(t.state == TaskState.QUEUED for t in tasks)


def test_completed_files_detected(dirs):
    add_task(dirs, "001-alpha.md", folder="done")
    mgr = make_mgr(dirs)
    tasks = mgr.all_tasks()
    assert len(tasks) == 1
    assert tasks[0].state == TaskState.COMPLETED


def test_failed_files_detected(dirs):
    add_task(dirs, "001-alpha.md", folder="failed")
    mgr = make_mgr(dirs)
    tasks = mgr.all_tasks()
    assert len(tasks) == 1
    assert tasks[0].state == TaskState.FAILED


def test_running_file_detected_via_state(dirs):
    add_task(dirs, "001-alpha.md")
    dirs["state"].write_text(json.dumps({"running": "001-alpha.md", "started_at": "now"}))
    mgr = make_mgr(dirs)
    running = mgr.running()
    assert running is not None
    assert running.filename == "001-alpha.md"
    assert running.state == TaskState.RUNNING
    assert running.started_at == "now"


def test_tasks_sorted_alphabetically(dirs):
    add_task(dirs, "030-zzz.md")
    add_task(dirs, "010-aaa.md")
    add_task(dirs, "020-mmm.md")
    mgr = make_mgr(dirs)
    names = [t.filename for t in mgr.queued()]
    assert names == ["010-aaa.md", "020-mmm.md", "030-zzz.md"]


def test_task_name_strips_md_suffix(dirs):
    add_task(dirs, "044-something.md")
    mgr = make_mgr(dirs)
    assert mgr.all_tasks()[0].name == "044-something"


# ---------------------------------------------------------------------------
# next_task / navigation
# ---------------------------------------------------------------------------

def test_next_task_returns_none_when_empty(dirs):
    mgr = make_mgr(dirs)
    assert mgr.next_task() is None


def test_next_task_returns_first_queued(dirs):
    add_task(dirs, "010-first.md")
    add_task(dirs, "020-second.md")
    mgr = make_mgr(dirs)
    assert mgr.next_task().filename == "010-first.md"


def test_next_task_returns_running_task_on_resume(dirs):
    add_task(dirs, "010-first.md")
    add_task(dirs, "020-second.md")
    dirs["state"].write_text(json.dumps({"running": "020-second.md", "started_at": "t"}))
    mgr = make_mgr(dirs)
    # Should resume the running task, not skip to the next queued one
    assert mgr.next_task().filename == "020-second.md"


def test_next_task_returns_queued_when_no_running(dirs):
    add_task(dirs, "010-first.md")
    mgr = make_mgr(dirs)
    task = mgr.next_task()
    assert task.state == TaskState.QUEUED


# ---------------------------------------------------------------------------
# mark_running
# ---------------------------------------------------------------------------

def test_mark_running_updates_state(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    assert mgr.running().filename == "001-alpha.md"


def test_mark_running_persists_to_disk(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    state = json.loads(dirs["state"].read_text())
    assert state["running"] == "001-alpha.md"
    assert state["started_at"] is not None


def test_mark_running_writes_log(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    log = (dirs["logs"] / "001-alpha.log").read_text()
    assert "START" in log


# ---------------------------------------------------------------------------
# mark_done
# ---------------------------------------------------------------------------

def test_mark_done_moves_file(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    mgr.mark_done("001-alpha.md")
    assert not (dirs["queue"] / "001-alpha.md").exists()
    assert (dirs["done"] / "001-alpha.md").exists()


def test_mark_done_clears_running_state(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    mgr.mark_done("001-alpha.md")
    assert mgr.running() is None


def test_mark_done_writes_log(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    mgr.mark_done("001-alpha.md")
    log = (dirs["logs"] / "001-alpha.log").read_text()
    assert "DONE" in log


def test_mark_done_nonexistent_file_does_not_raise(dirs):
    mgr = make_mgr(dirs)
    mgr.mark_done("999-ghost.md")  # should not raise


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------

def test_mark_failed_moves_file(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    mgr.mark_failed("001-alpha.md", note="tests could not pass")
    assert not (dirs["queue"] / "001-alpha.md").exists()
    assert (dirs["failed"] / "001-alpha.md").exists()


def test_mark_failed_clears_running_state(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    mgr.mark_failed("001-alpha.md")
    assert mgr.running() is None


def test_mark_failed_writes_log_with_note(dirs):
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_failed("001-alpha.md", note="unclear spec")
    log = (dirs["logs"] / "001-alpha.log").read_text()
    assert "FAIL" in log
    assert "unclear spec" in log


def test_mark_failed_nonexistent_file_does_not_raise(dirs):
    mgr = make_mgr(dirs)
    mgr.mark_failed("999-ghost.md", "gone")  # should not raise


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status_returns_correct_counts(dirs):
    add_task(dirs, "001-q1.md")
    add_task(dirs, "002-q2.md")
    add_task(dirs, "010-done.md", folder="done")
    add_task(dirs, "011-fail.md", folder="failed")
    dirs["state"].write_text(json.dumps({"running": "001-q1.md", "started_at": "t"}))
    mgr = make_mgr(dirs)
    s = mgr.status()
    assert s["queued"] == ["002-q2.md"]
    assert s["running"] == ["001-q1.md"]
    assert s["completed"] == ["010-done.md"]
    assert s["failed"] == ["011-fail.md"]


def test_status_empty(dirs):
    mgr = make_mgr(dirs)
    s = mgr.status()
    assert s == {"queued": [], "running": [], "completed": [], "failed": []}


# ---------------------------------------------------------------------------
# generate_morning_report()
# ---------------------------------------------------------------------------

def test_morning_report_created(dirs):
    add_task(dirs, "001-alpha.md")
    add_task(dirs, "010-done.md", folder="done")
    mgr = make_mgr(dirs)
    report = mgr.generate_morning_report()
    assert dirs["report"].exists()
    assert "Morning Report" in report


def test_morning_report_sections(dirs):
    add_task(dirs, "001-queued.md")
    add_task(dirs, "002-done.md", folder="done")
    add_task(dirs, "003-fail.md", folder="failed")
    mgr = make_mgr(dirs)
    report = mgr.generate_morning_report()
    assert "Queued" in report
    assert "001-queued.md" in report
    assert "Completed" in report
    assert "002-done.md" in report
    assert "Failed" in report
    assert "003-fail.md" in report


def test_morning_report_summary_counts(dirs):
    add_task(dirs, "001-q.md")
    add_task(dirs, "002-d.md", folder="done")
    mgr = make_mgr(dirs)
    report = mgr.generate_morning_report()
    assert "Queued:    1" in report
    assert "Completed: 1" in report


def test_morning_report_omits_empty_sections(dirs):
    mgr = make_mgr(dirs)
    report = mgr.generate_morning_report()
    assert "## Queued" not in report
    assert "## Completed" not in report
    assert "## Failed" not in report


# ---------------------------------------------------------------------------
# Resume after interruption
# ---------------------------------------------------------------------------

def test_resume_after_interruption_detects_running_task(dirs):
    """If a task was marked running but not finished, the next QueueManager
    instance (simulating restart after crash) sees it as RUNNING."""
    add_task(dirs, "001-alpha.md")
    dirs["state"].write_text(json.dumps({"running": "001-alpha.md", "started_at": "2026-06-19"}))

    mgr = make_mgr(dirs)  # fresh instance — simulates restart
    assert mgr.running() is not None
    assert mgr.running().filename == "001-alpha.md"
    assert mgr.next_task().filename == "001-alpha.md"


def test_resume_corrupted_state_gracefully_recovers(dirs):
    dirs["state"].write_text("not valid json{{{")
    mgr = make_mgr(dirs)  # should not raise
    assert mgr.running() is None


# ---------------------------------------------------------------------------
# Logs directory created on demand
# ---------------------------------------------------------------------------

def test_logs_dir_created_on_first_write(dirs):
    assert not dirs["logs"].exists()
    add_task(dirs, "001-alpha.md")
    mgr = make_mgr(dirs)
    mgr.mark_running("001-alpha.md")
    assert dirs["logs"].exists()


# ---------------------------------------------------------------------------
# done_dir / failed_dir created on demand
# ---------------------------------------------------------------------------

def test_done_dir_created_on_mark_done(tmp_path):
    q = tmp_path / "queue"
    d = tmp_path / "done_new"  # does not exist yet
    f = tmp_path / "failed_new"
    q.mkdir()
    (q / "001.md").write_text("task")
    mgr = QueueManager(
        queue_dir=q,
        done_dir=d,
        failed_dir=f,
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        state_file=tmp_path / ".state.json",
    )
    mgr.mark_done("001.md")
    assert d.exists()
    assert (d / "001.md").exists()


def test_failed_dir_created_on_mark_failed(tmp_path):
    q = tmp_path / "queue"
    d = tmp_path / "done_new"
    f = tmp_path / "failed_new"  # does not exist yet
    q.mkdir()
    (q / "001.md").write_text("task")
    mgr = QueueManager(
        queue_dir=q,
        done_dir=d,
        failed_dir=f,
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        state_file=tmp_path / ".state.json",
    )
    mgr.mark_failed("001.md", "oops")
    assert f.exists()
    assert (f / "001.md").exists()
