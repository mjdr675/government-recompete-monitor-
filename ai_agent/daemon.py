"""
Daemon runner for the autonomous agent loop.

Wraps AutonomousLoop with:
- SIGTERM/SIGINT safe shutdown (sets a flag, checked between tasks)
- Usage-limit detection — sleeps and resumes automatically
- max_tasks_per_window — caps tasks per invocation
- max_runtime_minutes — hard wall-clock cap
- Logs interrupted-task detection on startup (resume after reboot)
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ai_agent.loop import AutonomousLoop, LoopResult

# Error text patterns that indicate a Claude/session usage limit
USAGE_LIMIT_PATTERNS = [
    "usage limit exceeded",
    "usage_limit_exceeded",
    "rate_limit_error",
    "overloaded_error",
    "you've reached your usage limit",
    "reached the rate limit",
    "too many requests",
    "retry after",
    "claude pro usage limit",
    "monthly usage limit",
    "credit balance is too low",
    "insufficient_quota",
]


def is_usage_limit_error(text: str) -> bool:
    """Return True if text contains a Claude/session usage-limit signal."""
    lower = text.lower()
    return any(p in lower for p in USAGE_LIMIT_PATTERNS)


@dataclass
class DaemonConfig:
    """Tuning knobs for daemon operation. Conservative defaults avoid runaway usage."""
    max_tasks_per_window: int = 10
    sleep_minutes_after_usage_limit: float = 60.0
    max_runtime_minutes: float = 240.0
    idle_sleep_seconds: float = 300.0
    max_idle_checks: int = 10


class DaemonRunner:
    """
    Runs AutonomousLoop continuously as a background daemon.

    Lifecycle:
    1. Install SIGTERM/SIGINT handlers (graceful shutdown after current task)
    2. Log any interrupted task found in queue state (resume-after-reboot detection)
    3. Loop: run_one(), enforce per-window and runtime caps, sleep when idle
    4. On usage-limit failure: log, sleep sleep_minutes_after_usage_limit, resume
    5. On SIGTERM/SIGINT: finish the current task, then exit cleanly
    """

    def __init__(
        self,
        loop: AutonomousLoop,
        config: Optional[DaemonConfig] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._loop = loop
        self._config = config or DaemonConfig()
        self._log = log_fn or (lambda msg: print(f"[DAEMON] {msg}"))
        self._shutdown_requested = False
        self._tasks_this_window = 0
        self._start_time = time.monotonic()

    # -- Public API --

    def run(self) -> str:
        """
        Main daemon loop. Blocks until a stop condition is reached.
        Returns a short stop-reason string for logging/testing.
        """
        self._install_signal_handlers()
        self._log_resume_check()
        self._log(
            f"Daemon started. pid={os.getpid()} "
            f"max_tasks={self._config.max_tasks_per_window} "
            f"max_runtime={self._config.max_runtime_minutes:.0f}m"
        )

        idle_count = 0
        stop_reason = "queue_empty"

        try:
            while not self._shutdown_requested:
                elapsed_min = (time.monotonic() - self._start_time) / 60.0
                if elapsed_min >= self._config.max_runtime_minutes:
                    stop_reason = "max_runtime"
                    self._log(
                        f"Reached max_runtime_minutes={self._config.max_runtime_minutes:.0f} — stopping."
                    )
                    break

                if self._tasks_this_window >= self._config.max_tasks_per_window:
                    stop_reason = "max_tasks_per_window"
                    self._log(
                        f"Reached max_tasks_per_window={self._config.max_tasks_per_window} — stopping."
                    )
                    break

                result = self._loop.run_one()

                if result in (LoopResult.DONE, LoopResult.DRY_RUN):
                    self._tasks_this_window += 1
                    idle_count = 0

                elif result == LoopResult.FAILED:
                    self._tasks_this_window += 1
                    idle_count = 0
                    last = self._loop._results[-1] if self._loop._results else None
                    if last and last.error and is_usage_limit_error(last.error):
                        self._handle_usage_limit()
                        if self._shutdown_requested:
                            break

                elif result == LoopResult.ESCALATED:
                    stop_reason = "escalated"
                    self._log("Escalation file present — stopping daemon.")
                    break

                elif result == LoopResult.QUEUE_EMPTY:
                    idle_count += 1
                    if idle_count >= self._config.max_idle_checks:
                        stop_reason = "max_idle"
                        self._log(
                            f"Queue empty for {idle_count} consecutive checks — stopping."
                        )
                        break
                    self._log(
                        f"Queue empty — sleeping {self._config.idle_sleep_seconds:.0f}s "
                        f"(idle {idle_count}/{self._config.max_idle_checks})"
                    )
                    self._interruptible_sleep(self._config.idle_sleep_seconds)

        except Exception as exc:
            stop_reason = f"error: {exc}"
            self._log(f"Unexpected error in daemon loop: {exc}")

        if self._shutdown_requested:
            stop_reason = "shutdown_requested"

        self._log(
            f"Daemon stopped. reason={stop_reason} "
            f"tasks_completed={self._tasks_this_window}"
        )
        return stop_reason

    # -- Private helpers --

    def _log_resume_check(self) -> None:
        """Log if the queue manager has an interrupted (RUNNING) task from a prior run."""
        try:
            interrupted = self._loop.mgr.running()
            if interrupted:
                self._log(
                    f"Detected interrupted task from prior run: {interrupted.filename} "
                    f"(started {interrupted.started_at}) — will resume it first."
                )
        except Exception:
            pass

    def _handle_usage_limit(self) -> None:
        """Log, write a state note, sleep, then resume."""
        sleep_secs = self._config.sleep_minutes_after_usage_limit * 60.0
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self._log(
            f"[{ts}] Usage limit detected — pausing for "
            f"{self._config.sleep_minutes_after_usage_limit:.0f} minutes "
            f"then resuming. tasks_this_window={self._tasks_this_window}"
        )
        self._interruptible_sleep(sleep_secs)
        if not self._shutdown_requested:
            self._log("Resuming after usage-limit sleep.")

    def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in 1-second ticks so SIGTERM/SIGINT are processed promptly."""
        end = time.monotonic() + seconds
        while not self._shutdown_requested:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))

    def _install_signal_handlers(self) -> None:
        def _handler(signum, frame):  # noqa: ARG001
            self._log(f"Signal {signum} received — will stop after current task.")
            self._shutdown_requested = True

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
