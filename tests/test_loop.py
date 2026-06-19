"""
Unit tests for ai_agent/loop.py.

All external calls (LLM, patcher, git, pytest subprocess) are mocked.
QueueManager uses real tmp_path directories so state transitions are verified
against the actual filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from ai_agent.eng_memory import EngineeringMemory
from ai_agent.loop import (
    AutonomousLoop,
    LoopResult,
    TaskOutcome,
    call_with_retry,
    load_task,
)
from ai_agent.manager import QueueManager, TaskInfo, TaskState


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _eng_memory_mock(monkeypatch):
    """
    Prevent EngineeringMemory from writing to the real ai_agent/ directory
    during loop tests.  Exposed as a fixture so specific tests can assert on
    it by declaring '_eng_memory_mock' as a parameter.
    """
    mock_instance = MagicMock(spec=EngineeringMemory)
    mock_instance.build_context.return_value = ""
    success_result = MagicMock()
    success_result.error = None
    success_result.docs_updated = []
    success_result.docs_unchanged = []
    mock_instance.update_from_llm.return_value = success_result
    monkeypatch.setattr("ai_agent.loop.EngineeringMemory", lambda *a, **kw: mock_instance)
    yield mock_instance


@pytest.fixture()
def dirs(tmp_path: Path) -> dict[str, Path]:
    q = tmp_path / "queue"
    d = tmp_path / "done"
    f = tmp_path / "failed"
    q.mkdir()
    d.mkdir()
    f.mkdir()
    return {
        "queue": q,
        "done": d,
        "failed": f,
        "logs": tmp_path / "logs",
        "report": tmp_path / "morning_report.md",
        "state": tmp_path / ".queue_state.json",
        "escalate": tmp_path / "ESCALATE.md",
        "root": tmp_path,
    }


def make_mgr(dirs: dict) -> QueueManager:
    return QueueManager(
        queue_dir=dirs["queue"],
        done_dir=dirs["done"],
        failed_dir=dirs["failed"],
        logs_dir=dirs["logs"],
        report_path=dirs["report"],
        state_file=dirs["state"],
    )


def make_loop(dirs: dict, dry_run: bool = True, **kwargs) -> AutonomousLoop:
    return AutonomousLoop(
        mgr=make_mgr(dirs),
        dry_run=dry_run,
        escalate_file=dirs["escalate"],
        repo_root=dirs["root"],
        **kwargs,
    )


def add_task(dirs: dict, name: str, content: str = "") -> Path:
    path = dirs["queue"] / name
    path.write_text(content or f"# {name}\n\nDo something.\n")
    return path


# A valid patch string that passes the reviewer (no dangerous patterns)
VALID_PATCH = """\
## Summary
Add a constant.

## Files to Change
- calc.py

## Patch: calc.py
### Before
```python
X = 1
```
### After
```python
X = 2
```
"""


def _mock_specialist(patch_content: str = VALID_PATCH, role: str = "backend") -> MagicMock:
    spec = MagicMock()
    spec.ROLE = role
    spec.plan.return_value = patch_content
    return spec


def _apply_success(commit_sha: str = "abc1234") -> MagicMock:
    r = MagicMock()
    r.success = True
    r.commit_sha = commit_sha
    r.rolled_back = False
    r.validation = MagicMock(valid=True, errors=[])
    r.test_result = None
    r.error = None
    return r


def _apply_rolled_back(test_output: str = "FAILED test_x") -> MagicMock:
    r = MagicMock()
    r.success = False
    r.commit_sha = None
    r.rolled_back = True
    r.validation = MagicMock(valid=True, errors=[])
    r.test_result = MagicMock(stdout=test_output, returncode=1)
    r.error = "tests failed — rolled back"
    return r


def _apply_validation_fail(errors: list[str]) -> MagicMock:
    r = MagicMock()
    r.success = False
    r.commit_sha = None
    r.rolled_back = False
    r.validation = MagicMock(valid=False, errors=errors)
    r.test_result = None
    r.error = "validation failed"
    return r


# ---------------------------------------------------------------------------
# load_task
# ---------------------------------------------------------------------------

def test_load_task_parses_title_and_body(tmp_path: Path) -> None:
    p = tmp_path / "044-example.md"
    p.write_text("# Task 044 — Example\n\nDo the thing.\n\nDetails here.\n")
    info = TaskInfo(filename="044-example.md", state=TaskState.QUEUED)
    task = load_task(info, tmp_path)
    assert task["title"] == "Task 044 — Example"
    assert "Do the thing" in task["body"]
    assert task["source"] == "044-example.md"
    assert task["status"] == "OPEN"


def test_load_task_handles_missing_file(tmp_path: Path) -> None:
    info = TaskInfo(filename="999-ghost.md", state=TaskState.QUEUED)
    task = load_task(info, tmp_path)
    assert task["title"] == "999-ghost"
    assert task["body"] == ""


def test_load_task_single_line_file(tmp_path: Path) -> None:
    p = tmp_path / "001.md"
    p.write_text("# Title only")
    info = TaskInfo(filename="001.md", state=TaskState.QUEUED)
    task = load_task(info, tmp_path)
    assert task["title"] == "Title only"
    assert task["body"] == ""


# ---------------------------------------------------------------------------
# call_with_retry
# ---------------------------------------------------------------------------

def test_call_with_retry_succeeds_first_try() -> None:
    fn = MagicMock(return_value="ok")
    assert call_with_retry(fn, max_retries=2, base_delay=0) == "ok"
    assert fn.call_count == 1


def test_call_with_retry_retries_on_transient_error() -> None:
    fn = MagicMock(side_effect=[RuntimeError("timeout"), "ok"])
    assert call_with_retry(fn, max_retries=2, base_delay=0) == "ok"
    assert fn.call_count == 2


def test_call_with_retry_exhausts_all_retries() -> None:
    fn = MagicMock(side_effect=RuntimeError("always fails"))
    with pytest.raises(RuntimeError, match="always fails"):
        call_with_retry(fn, max_retries=2, base_delay=0)
    assert fn.call_count == 3  # initial + 2 retries


def test_call_with_retry_no_retry_on_not_set() -> None:
    fn = MagicMock(side_effect=RuntimeError("ANTHROPIC_API_KEY not set"))
    with pytest.raises(RuntimeError):
        call_with_retry(fn, max_retries=3, base_delay=0)
    assert fn.call_count == 1


def test_call_with_retry_no_retry_on_not_installed() -> None:
    fn = MagicMock(side_effect=RuntimeError("anthropic not installed"))
    with pytest.raises(RuntimeError):
        call_with_retry(fn, max_retries=3, base_delay=0)
    assert fn.call_count == 1


def test_call_with_retry_no_retry_on_api_key_error() -> None:
    fn = MagicMock(side_effect=RuntimeError("API key missing"))
    with pytest.raises(RuntimeError):
        call_with_retry(fn, max_retries=3, base_delay=0)
    assert fn.call_count == 1


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — empty queue
# ---------------------------------------------------------------------------

def test_run_one_empty_queue(dirs: dict) -> None:
    loop = make_loop(dirs)
    assert loop.run_one() == LoopResult.QUEUE_EMPTY


def test_run_one_blocked_by_escalation_file(dirs: dict) -> None:
    add_task(dirs, "001.md")
    dirs["escalate"].write_text("# Escalation\n")
    loop = make_loop(dirs)
    assert loop.run_one() == LoopResult.ESCALATED
    # Task must still be in queue (not consumed)
    assert (dirs["queue"] / "001.md").exists()


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — dry-run
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_dry_run_marks_task_done(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    loop = make_loop(dirs, dry_run=True)
    result = loop.run_one()

    assert result == LoopResult.DRY_RUN
    assert not (dirs["queue"] / "001-test.md").exists()
    assert (dirs["done"] / "001-test.md").exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_dry_run_does_not_call_patcher(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    with patch("ai_agent.loop.patcher_module.execute") as mock_patcher:
        make_loop(dirs, dry_run=True).run_one()
        mock_patcher.assert_not_called()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_dry_run_records_outcome(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    loop = make_loop(dirs, dry_run=True)
    loop.run_one()

    assert len(loop._results) == 1
    assert loop._results[0].result == LoopResult.DRY_RUN


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — apply success
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, "5 passed"))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_apply_success_marks_done(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_success("abc1234")

    loop = make_loop(dirs, dry_run=False)
    result = loop.run_one()

    assert result == LoopResult.DONE
    assert not (dirs["queue"] / "001-test.md").exists()
    assert (dirs["done"] / "001-test.md").exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, "5 passed"))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_apply_success_records_commit_sha(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_success("deadbeef")

    loop = make_loop(dirs, dry_run=False)
    loop.run_one()

    assert loop._results[0].commit_sha == "deadbeef"


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, "5 passed"))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_apply_success_resets_consecutive_failures(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_success()

    loop = make_loop(dirs, dry_run=False)
    loop._consecutive_failures = 2  # simulate prior failures
    loop.run_one()

    assert loop._consecutive_failures == 0


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — patcher failure with retry
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-same")
@patch("ai_agent.loop._run_tests", return_value=(True, ""))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_patcher_failure_marks_task_failed(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_rolled_back()

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=1)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    assert not (dirs["queue"] / "001-test.md").exists()
    assert (dirs["failed"] / "001-test.md").exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, ""))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_patcher_failure_triggers_retry_with_feedback(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    spec = _mock_specialist()
    mock_assign.return_value = spec
    mock_save.return_value = tmp_path / "patch.md"
    # First attempt fails, second succeeds
    mock_patcher.side_effect = [_apply_rolled_back(), _apply_success()]

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=2)
    result = loop.run_one()

    assert result == LoopResult.DONE
    # Specialist was called twice — second call has failure history in task body
    assert spec.plan.call_count == 2
    second_task = spec.plan.call_args_list[1][0][0]  # first positional arg
    assert "Previous Attempt Failures" in second_task["body"]


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-same")
@patch("ai_agent.loop._run_tests", return_value=(True, ""))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_validation_failure_feedback_included(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    spec = _mock_specialist()
    mock_assign.return_value = spec
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_validation_fail(
        ["Before text not found in calc.py: 'old code'"]
    )

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=2)
    loop.run_one()

    # Second call must include validation error in task body
    if spec.plan.call_count == 2:
        second_task = spec.plan.call_args_list[1][0][0]
        assert "validation failed" in second_task["body"].lower()


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — LLM failure
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_llm_config_error_fails_immediately(mock_assign, mock_sha, mock_mem, dirs):
    add_task(dirs, "001-test.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    assert spec.plan.call_count == 1  # no retry on config error


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_llm_transient_error_retries(mock_assign, mock_sha, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-test.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = [
        RuntimeError("rate limit"),
        RuntimeError("rate limit"),
        VALID_PATCH,
    ]
    mock_assign.return_value = spec

    with patch("ai_agent.loop.save_patch", return_value=tmp_path / "p.md"), \
         patch("ai_agent.loop._run_tests", return_value=(True, "")), \
         patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"]), \
         patch("ai_agent.loop.patcher_module.execute", return_value=_apply_success()):
        loop = make_loop(dirs, dry_run=False, max_llm_retries=3)
        result = loop.run_one()

    assert result == LoopResult.DONE


# ---------------------------------------------------------------------------
# AutonomousLoop.run_one() — post-apply validation
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-same")
@patch("ai_agent.loop._run_tests", return_value=(False, "FAILED test_x"))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_post_apply_test_failure_marks_failed(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    # Patcher says success but independent pytest run fails
    mock_patcher.return_value = _apply_success("abc")

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=1)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    assert (dirs["failed"] / "001-test.md").exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-same")  # SHA never changes
@patch("ai_agent.loop._run_tests", return_value=(True, ""))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_no_new_commit_marks_failed(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem, dirs, tmp_path
):
    add_task(dirs, "001-test.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    # Patcher says success but returns no commit_sha; SHA also unchanged
    r = _apply_success(commit_sha=None)
    r.commit_sha = None
    mock_patcher.return_value = r

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=1)
    result = loop.run_one()

    assert result == LoopResult.FAILED


# ---------------------------------------------------------------------------
# Reviewer blocking
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_reviewer_blocked_patch_marks_failed(mock_assign, mock_sha, mock_mem, dirs):
    add_task(dirs, "001-test.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    # Plan produces a dangerous patch
    spec.plan.return_value = "git push origin main"
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=1)
    result = loop.run_one()

    assert result == LoopResult.FAILED


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, ""))
@patch("ai_agent.loop.assign_specialist")
def test_reviewer_block_then_clean_retry(mock_assign, mock_tests, mock_sha, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-test.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = ["git push origin main", VALID_PATCH]
    mock_assign.return_value = spec

    with patch("ai_agent.loop.save_patch", return_value=tmp_path / "p.md"), \
         patch("ai_agent.loop.patcher_module.execute", return_value=_apply_success()):
        loop = make_loop(dirs, dry_run=False, max_plan_attempts=2)
        result = loop.run_one()

    assert result == LoopResult.DONE
    assert spec.plan.call_count == 2


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_escalation_after_consecutive_failures(mock_assign, mock_sha, mock_mem, dirs):
    for i in range(3):
        add_task(dirs, f"00{i + 1}-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_consecutive_failures=3)
    # Run until escalated
    results = [loop.run_one(), loop.run_one(), loop.run_one()]

    assert LoopResult.ESCALATED in results
    assert dirs["escalate"].exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_escalation_file_contains_failed_tasks(mock_assign, mock_sha, mock_mem, dirs):
    add_task(dirs, "001-broken.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_consecutive_failures=1)
    loop.run_one()

    content = dirs["escalate"].read_text()
    assert "001-broken.md" in content
    assert "Escalation" in content


# ---------------------------------------------------------------------------
# run_loop()
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_run_loop_processes_all_tasks(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    for i in range(3):
        add_task(dirs, f"00{i + 1}-task.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    loop = make_loop(dirs, dry_run=True)
    outcomes = loop.run_loop()

    assert len(outcomes) == 3
    assert all(o.result == LoopResult.DRY_RUN for o in outcomes)
    assert len(list(dirs["done"].glob("*.md"))) == 3


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_run_loop_generates_morning_report(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-task.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    loop = make_loop(dirs, dry_run=True)
    loop.run_loop()

    assert dirs["report"].exists()
    assert "Morning Report" in dirs["report"].read_text()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_run_loop_stops_on_escalation(mock_assign, mock_save, mock_mem, dirs):
    for i in range(5):
        add_task(dirs, f"00{i + 1}-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_consecutive_failures=2)
    outcomes = loop.run_loop()

    assert loop._stop_reason == LoopResult.ESCALATED
    # Should have stopped after 2 failures, not processed all 5
    assert len(outcomes) <= 5


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_run_loop_stop_reason_empty_on_success(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-task.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    loop = make_loop(dirs, dry_run=True)
    loop.run_loop()

    assert loop._stop_reason == LoopResult.QUEUE_EMPTY


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_run_one_writes_task_log(mock_assign, mock_save, mock_mem, dirs, tmp_path):
    add_task(dirs, "001-alpha.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    make_loop(dirs, dry_run=True).run_one()

    log_path = dirs["logs"] / "001-alpha.log"
    assert log_path.exists()
    content = log_path.read_text()
    assert "START" in content
    assert "DONE" in content


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_failed_task_log_contains_error(mock_assign, mock_sha, mock_mem, dirs):
    add_task(dirs, "001-alpha.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    make_loop(dirs, dry_run=False, max_plan_attempts=1).run_one()

    log_path = dirs["logs"] / "001-alpha.log"
    assert "FAILED" in log_path.read_text()


# ---------------------------------------------------------------------------
# Recovery integration: 3-attempt limit, failure reports, early cut-short
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_exactly_3_attempts_made_before_fail(mock_assign, mock_sha, mock_mem, dirs):
    """Loop must make exactly max_plan_attempts LLM calls, no more, no less.
    Uses reviewer-blocking (distinct patches each time) so cut-short does not
    trigger early — all 3 outer attempts must run."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    # Three distinct dangerous patches: reviewer blocks each, cut-short never fires
    spec.plan.side_effect = [
        "git push origin main",
        "rm -rf /tmp/test",
        "DROP TABLE contracts",
    ]
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    assert spec.plan.call_count == 3


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_failure_report_written_after_all_attempts(mock_assign, mock_sha, mock_mem, dirs):
    """A failure report file must exist in logs/ after all attempts are exhausted."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = [
        "git push origin main",
        "rm -rf /tmp/test",
        "DROP TABLE contracts",
    ]
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    loop.run_one()

    report = dirs["logs"] / "001-task-failure-report.md"
    assert report.exists(), "failure report must be written after all retries exhausted"


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_failure_report_contains_all_attempts(mock_assign, mock_sha, mock_mem, dirs):
    """Failure report must document every attempt, not just the last one."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = [
        "git push origin main",
        "rm -rf /tmp/test",
        "DROP TABLE contracts",
    ]
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    loop.run_one()

    report_text = (dirs["logs"] / "001-task-failure-report.md").read_text()
    assert "Attempt 1" in report_text
    assert "Attempt 2" in report_text
    assert "Attempt 3" in report_text


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_early_cutshort_on_identical_patch(mock_assign, mock_sha, mock_mem, dirs, tmp_path):
    """When the same patch is generated twice the loop cuts short after attempt 2."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    # Same patch content both times — identical hash → should_cut_short triggers
    spec.plan.return_value = "git push origin main"  # blocked by reviewer
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    # Should stop at attempt 2, not burn attempt 3
    assert spec.plan.call_count == 2


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_early_cutshort_still_writes_failure_report(mock_assign, mock_sha, mock_mem, dirs):
    """Cut-short path must still produce a failure report."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.return_value = "git push origin main"
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    loop.run_one()

    report = dirs["logs"] / "001-task-failure-report.md"
    assert report.exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_each_retry_recorded_in_failure_report(mock_assign, mock_sha, mock_mem, dirs, tmp_path):
    """Failure report must record each attempt separately with its error."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    # Three distinct patches blocked by reviewer: all 3 outer attempts run
    spec.plan.side_effect = [
        "git push origin main",
        "rm -rf /tmp/test",
        "DROP TABLE contracts",
    ]
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    loop.run_one()

    report_text = (dirs["logs"] / "001-task-failure-report.md").read_text()
    # Report should list 3 attempts (not collapsed into one)
    assert report_text.count("Attempt") >= 3


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_failure_report_path_in_task_outcome(mock_assign, mock_sha, mock_mem, dirs):
    """TaskOutcome.failure_report must point to the written report file."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=1)
    loop.run_one()

    assert len(loop._results) == 1
    outcome = loop._results[0]
    assert outcome.failure_report is not None
    assert outcome.failure_report.exists()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_never_exceeds_max_plan_attempts(mock_assign, mock_sha, mock_mem, dirs):
    """Loop must stop at max_plan_attempts even if no cut-short triggers."""
    add_task(dirs, "001-task.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    # Generate unique patches each attempt so cut-short does NOT trigger
    spec.plan.side_effect = [
        "git push origin main",   # reviewer blocks — attempt 1
        "rm -rf /tmp/test",       # reviewer blocks — attempt 2
        "os.remove('/etc/passwd')", # reviewer blocks — attempt 3
    ]
    mock_assign.return_value = spec

    loop = make_loop(dirs, dry_run=False, max_plan_attempts=3)
    result = loop.run_one()

    assert result == LoopResult.FAILED
    assert spec.plan.call_count == 3  # exactly 3, no more


# ---------------------------------------------------------------------------
# Engineering memory integration
# ---------------------------------------------------------------------------

@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_context_prepended_to_plan_body(
    mock_assign, mock_save, mock_mem, _eng_memory_mock, dirs, tmp_path
):
    """Engineering memory context must appear in the task body passed to plan()."""
    add_task(dirs, "001.md", "# Task\n\noriginal body text\n")
    _eng_memory_mock.build_context.return_value = (
        "# Engineering Memory\n\n## CURRENT_STATE.md\n\nhas content\n"
    )
    spec = _mock_specialist()
    mock_assign.return_value = spec
    mock_save.return_value = tmp_path / "patch.md"

    make_loop(dirs, dry_run=True).run_one()

    called_task = spec.plan.call_args.args[0]
    assert "Engineering Memory" in called_task["body"]
    assert "original body text" in called_task["body"]


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_no_context_when_empty(
    mock_assign, mock_save, mock_mem, _eng_memory_mock, dirs, tmp_path
):
    """When build_context() returns '', no context header is injected."""
    add_task(dirs, "001.md", "# Task\n\nbody text\n")
    _eng_memory_mock.build_context.return_value = ""
    spec = _mock_specialist()
    mock_assign.return_value = spec
    mock_save.return_value = tmp_path / "patch.md"

    make_loop(dirs, dry_run=True).run_one()

    called_task = spec.plan.call_args.args[0]
    assert "Engineering Memory" not in called_task["body"]


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_update_called_after_dry_run(
    mock_assign, mock_save, mock_mem, _eng_memory_mock, dirs, tmp_path
):
    """update_from_llm() must be called once after a successful dry run."""
    add_task(dirs, "001.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"

    make_loop(dirs, dry_run=True).run_one()

    _eng_memory_mock.update_from_llm.assert_called_once()
    kwargs = _eng_memory_mock.update_from_llm.call_args.kwargs
    assert kwargs["task_filename"] == "001.md"
    assert "dry run" in kwargs["outcome_summary"].lower()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", side_effect=["sha-before", "sha-after"])
@patch("ai_agent.loop._run_tests", return_value=(True, "5 passed"))
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.patcher_module.execute")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_update_called_after_apply_success(
    mock_assign, mock_patcher, mock_save, mock_tests, mock_sha, mock_mem,
    _eng_memory_mock, dirs, tmp_path,
):
    """update_from_llm() must include the commit SHA after a real apply."""
    add_task(dirs, "001.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    mock_patcher.return_value = _apply_success("abc1234")

    make_loop(dirs, dry_run=False).run_one()

    _eng_memory_mock.update_from_llm.assert_called_once()
    kwargs = _eng_memory_mock.update_from_llm.call_args.kwargs
    assert "abc1234" in kwargs["outcome_summary"]


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_update_failure_does_not_fail_task(
    mock_assign, mock_save, mock_mem, _eng_memory_mock, dirs, tmp_path
):
    """An exception in update_from_llm() must not propagate or fail the task."""
    add_task(dirs, "001.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    _eng_memory_mock.update_from_llm.side_effect = RuntimeError("memory system exploded")

    result = make_loop(dirs, dry_run=True).run_one()

    assert result == LoopResult.DRY_RUN


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop.save_patch")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_llm_error_triggers_fallback_append(
    mock_assign, mock_save, mock_mem, _eng_memory_mock, dirs, tmp_path
):
    """When update_from_llm returns an error, append_task_completion is called."""
    add_task(dirs, "001.md")
    mock_assign.return_value = _mock_specialist()
    mock_save.return_value = tmp_path / "patch.md"
    error_result = MagicMock()
    error_result.error = "ANTHROPIC_API_KEY not set"
    _eng_memory_mock.update_from_llm.return_value = error_result

    result = make_loop(dirs, dry_run=True).run_one()

    assert result == LoopResult.DRY_RUN
    _eng_memory_mock.append_task_completion.assert_called_once()


@patch("ai_agent.loop.get_memory", return_value=None)
@patch("ai_agent.loop._current_sha", return_value="sha-x")
@patch("ai_agent.loop.assign_specialist")
def test_eng_memory_not_updated_on_task_failure(
    mock_assign, mock_sha, mock_mem, _eng_memory_mock, dirs
):
    """Failed tasks must not trigger a memory update."""
    add_task(dirs, "001.md")
    spec = MagicMock()
    spec.ROLE = "backend"
    spec.plan.side_effect = RuntimeError("ANTHROPIC_API_KEY not set")
    mock_assign.return_value = spec

    make_loop(dirs, dry_run=False, max_plan_attempts=1).run_one()

    _eng_memory_mock.update_from_llm.assert_not_called()
    _eng_memory_mock.append_task_completion.assert_not_called()
