"""
Tests for ai_agent/daemon.py — DaemonRunner and is_usage_limit_error.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_agent.daemon import (
    USAGE_LIMIT_PATTERNS,
    DaemonConfig,
    DaemonRunner,
    is_usage_limit_error,
)
from ai_agent.loop import AutonomousLoop, LoopResult, TaskOutcome


# ---------------------------------------------------------------------------
# is_usage_limit_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "usage limit exceeded",
    "usage_limit_exceeded",
    "rate_limit_error",
    "overloaded_error",
    "you've reached your usage limit",
    "reached the rate limit",
    "Too many requests",              # case-insensitive
    "Retry after 60 seconds",        # case-insensitive
    "Claude Pro usage limit reached",
    "monthly usage limit",
    "credit balance is too low",
    "insufficient_quota",
])
def test_is_usage_limit_error_detects_known_patterns(text: str) -> None:
    assert is_usage_limit_error(text) is True


@pytest.mark.parametrize("text", [
    "ANTHROPIC_API_KEY not set",
    "tests failed after apply",
    "reviewer blocked: git push origin main",
    "no new commit detected",
    "patch validation failed",
    "",
    "random unrelated error",
])
def test_is_usage_limit_error_ignores_non_limit_text(text: str) -> None:
    assert is_usage_limit_error(text) is False


def test_usage_limit_patterns_list_is_nonempty() -> None:
    assert len(USAGE_LIMIT_PATTERNS) > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(side_effects: list) -> AutonomousLoop:
    """Return a mock AutonomousLoop whose run_one() yields side_effects in order."""
    loop = MagicMock(spec=AutonomousLoop)
    loop.run_one.side_effect = side_effects
    loop._results = []
    loop.mgr = MagicMock()
    loop.mgr.running.return_value = None
    return loop


def _make_runner(loop, **cfg_kwargs) -> DaemonRunner:
    cfg = DaemonConfig(
        idle_sleep_seconds=0,   # no sleeping in tests
        max_idle_checks=cfg_kwargs.pop("max_idle_checks", 2),
        **cfg_kwargs,
    )
    return DaemonRunner(loop=loop, config=cfg, log_fn=lambda _: None)


def _failed_outcome(error: str) -> TaskOutcome:
    o = MagicMock(spec=TaskOutcome)
    o.result = LoopResult.FAILED
    o.error = error
    return o


def _done_outcome() -> TaskOutcome:
    o = MagicMock(spec=TaskOutcome)
    o.result = LoopResult.DONE
    o.error = None
    return o


# ---------------------------------------------------------------------------
# DaemonRunner.run() — stop reasons
# ---------------------------------------------------------------------------

def test_daemon_stops_on_max_idle(tmp_path: Path) -> None:
    """Queue empty for max_idle_checks consecutive calls → stop_reason='max_idle'."""
    loop = _make_loop([LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    runner = _make_runner(loop, max_idle_checks=2)
    reason = runner.run()
    assert reason == "max_idle"


def test_daemon_stops_on_escalation() -> None:
    loop = _make_loop([LoopResult.ESCALATED])
    runner = _make_runner(loop)
    reason = runner.run()
    assert reason == "escalated"


def test_daemon_stops_on_max_tasks_per_window() -> None:
    loop = _make_loop([LoopResult.DONE, LoopResult.DONE, LoopResult.DONE])
    loop._results = [_done_outcome(), _done_outcome(), _done_outcome()]
    runner = _make_runner(loop, max_tasks_per_window=2)
    reason = runner.run()
    assert reason == "max_tasks_per_window"
    # Should have stopped after processing 2 tasks, not called run_one a 3rd time
    assert loop.run_one.call_count == 2


def test_daemon_tracks_tasks_this_window() -> None:
    loop = _make_loop([LoopResult.DONE, LoopResult.DRY_RUN, LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop._results = [_done_outcome(), _done_outcome()]
    runner = _make_runner(loop, max_tasks_per_window=100)
    runner.run()
    assert runner._tasks_this_window == 2


def test_daemon_stops_on_max_runtime(monkeypatch) -> None:
    """Simulate max_runtime_minutes elapsed before first task runs."""
    loop = _make_loop([LoopResult.DONE])

    # Call 1 (in __init__) → _start_time = 0
    # Call 2+ (in run() loop check) → 300 min → exceeds 1 min limit
    call_count = [0]

    def fake_monotonic():
        call_count[0] += 1
        return 0.0 if call_count[0] == 1 else 300.0 * 60.0

    monkeypatch.setattr("ai_agent.daemon.time.monotonic", fake_monotonic)

    runner = _make_runner(loop, max_runtime_minutes=1.0)
    reason = runner.run()
    assert reason == "max_runtime"
    loop.run_one.assert_not_called()


def test_daemon_processes_tasks_until_queue_empty() -> None:
    """Normal happy path: two tasks, then queue empties."""
    outcomes = [_done_outcome(), _done_outcome()]
    loop = _make_loop([LoopResult.DONE, LoopResult.DONE, LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop._results = outcomes
    runner = _make_runner(loop, max_tasks_per_window=100)
    reason = runner.run()
    assert reason == "max_idle"
    assert runner._tasks_this_window == 2


# ---------------------------------------------------------------------------
# Usage-limit detection
# ---------------------------------------------------------------------------

def test_daemon_sleeps_after_usage_limit_error(monkeypatch) -> None:
    """When run_one returns FAILED with a usage-limit error, daemon sleeps."""
    bad_outcome = _failed_outcome("rate_limit_error: too many requests")
    loop = _make_loop([LoopResult.FAILED, LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop._results = [bad_outcome]

    sleep_calls = []

    def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr("ai_agent.daemon.time.sleep", fake_sleep)

    runner = _make_runner(loop, sleep_minutes_after_usage_limit=0.05)  # 3 seconds
    runner.run()

    assert len(sleep_calls) > 0


def test_daemon_does_not_sleep_for_non_limit_failures() -> None:
    """Non-usage-limit task failures do not trigger the usage-limit sleep path."""
    bad_outcome = _failed_outcome("patch validation failed: file not found")
    loop = _make_loop([LoopResult.FAILED, LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop._results = [bad_outcome]

    sleep_calls: list[float] = []

    runner = _make_runner(loop)
    # Patch _interruptible_sleep so we can detect if it's called for usage limit
    original_handle = runner._handle_usage_limit

    called = [False]

    def spy_handle():
        called[0] = True
        original_handle()

    runner._handle_usage_limit = spy_handle  # type: ignore[method-assign]
    runner.run()

    assert called[0] is False


# ---------------------------------------------------------------------------
# SIGTERM / safe shutdown
# ---------------------------------------------------------------------------

def test_daemon_shutdown_flag_stops_loop() -> None:
    """If _shutdown_requested is set before run(), loop exits immediately."""
    loop = _make_loop([LoopResult.DONE])
    runner = _make_runner(loop)
    runner._shutdown_requested = True
    reason = runner.run()
    assert reason == "shutdown_requested"
    loop.run_one.assert_not_called()


def test_daemon_shutdown_flag_set_by_signal_handler(monkeypatch) -> None:
    """The installed signal handler sets _shutdown_requested."""
    import signal as signal_mod

    captured_handlers: dict[int, object] = {}

    def fake_signal(signum, handler):
        captured_handlers[signum] = handler

    monkeypatch.setattr("ai_agent.daemon.signal.signal", fake_signal)

    loop = _make_loop([])
    runner = _make_runner(loop)
    runner._shutdown_requested = True  # prevent the actual run loop
    runner.run()

    assert signal_mod.SIGTERM in captured_handlers
    assert signal_mod.SIGINT in captured_handlers

    # Call the handler and verify it sets the flag
    runner._shutdown_requested = False
    handler = captured_handlers[signal_mod.SIGTERM]
    handler(signal_mod.SIGTERM, None)
    assert runner._shutdown_requested is True


# ---------------------------------------------------------------------------
# Resume-after-reboot logging
# ---------------------------------------------------------------------------

def test_daemon_logs_interrupted_task_on_startup() -> None:
    """If the queue has a RUNNING task, the daemon logs a resume notice."""
    from ai_agent.manager import TaskInfo, TaskState

    interrupted = TaskInfo(filename="042-old-task.md", state=TaskState.RUNNING, started_at="2026-01-01T00:00:00Z")
    loop = _make_loop([LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop.mgr.running.return_value = interrupted

    log_lines: list[str] = []
    runner = DaemonRunner(loop=loop, config=DaemonConfig(idle_sleep_seconds=0, max_idle_checks=1), log_fn=log_lines.append)
    runner.run()

    assert any("042-old-task.md" in line for line in log_lines)
    assert any("resume" in line.lower() for line in log_lines)


def test_daemon_no_resume_log_when_no_interrupted_task() -> None:
    """No resume notice when queue has no interrupted task."""
    loop = _make_loop([LoopResult.QUEUE_EMPTY, LoopResult.QUEUE_EMPTY])
    loop.mgr.running.return_value = None

    log_lines: list[str] = []
    runner = DaemonRunner(loop=loop, config=DaemonConfig(idle_sleep_seconds=0, max_idle_checks=1), log_fn=log_lines.append)
    runner.run()

    assert not any("resume" in line.lower() and "interrupted" in line.lower() for line in log_lines)


# ---------------------------------------------------------------------------
# DaemonConfig defaults
# ---------------------------------------------------------------------------

def test_daemon_config_defaults() -> None:
    cfg = DaemonConfig()
    assert cfg.max_tasks_per_window == 10
    assert cfg.sleep_minutes_after_usage_limit == 60.0
    assert cfg.max_runtime_minutes == 240.0
    assert cfg.idle_sleep_seconds == 300.0
    assert cfg.max_idle_checks == 10
