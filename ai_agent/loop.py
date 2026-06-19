"""
Autonomous execution loop.

Selects the next queued task, runs the LLM engineering pipeline, applies the
patch, validates pytest passes and a commit was created, then advances to the
next task. Stops when the queue is empty or consecutive failures trigger
escalation.

Flow per task:
  next_task() → mark_running()
    → assign_specialist() → LLM plan() [with retry + feedback]
    → review() → save_patch()
    → patcher.execute() [apply → test → commit or rollback]
    → validate pytest + commit
    → mark_done()  or  mark_failed() → [escalate after N failures]

CLI:
  python -m ai_agent.loop                  # dry-run, one task
  python -m ai_agent.loop --all            # dry-run, all tasks
  python -m ai_agent.loop --apply          # apply + commit, one task
  python -m ai_agent.loop --apply --all    # apply + commit, all tasks
  python -m ai_agent.loop --apply --daemon # keep running after queue drains
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from ai_agent import patcher as patcher_module
from ai_agent.manager import (
    QueueManager,
    TaskInfo,
    assign_specialist,
    save_patch,
    REPO_ROOT,
    QUEUE_DIR,
    DONE_DIR,
    FAILED_DIR,
    LOGS_DIR,
    MORNING_REPORT_PATH,
)
from ai_agent.memory import get_memory
from ai_agent.reviewer import review

_AGENT_DIR = Path(__file__).parent
_DEFAULT_ESCALATE_FILE = _AGENT_DIR / "ESCALATE.md"

# Seconds to wait between daemon idle checks (queue empty)
_DAEMON_IDLE_INTERVAL = 300
_DAEMON_MAX_IDLE = 10


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class LoopResult(str, Enum):
    DONE = "done"             # patch applied and committed
    DRY_RUN = "dry_run"      # patch saved, not applied
    FAILED = "failed"         # all retries exhausted
    QUEUE_EMPTY = "empty"
    ESCALATED = "escalated"


@dataclass
class TaskOutcome:
    filename: str
    result: LoopResult
    attempt: int = 1
    patch_path: Optional[Path] = None
    commit_sha: Optional[str] = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Helpers (module-level so they can be patched in tests)
# ---------------------------------------------------------------------------

def load_task(task_info: TaskInfo, queue_dir: Path) -> dict:
    """Parse a queue .md file into the specialist task dict format."""
    path = queue_dir / task_info.filename
    if not path.exists():
        return {
            "title": task_info.name,
            "body": "",
            "source": task_info.filename,
            "status": "OPEN",
        }
    lines = path.read_text().splitlines()
    title = lines[0].lstrip("#").strip() if lines else task_info.name
    body = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
    return {"title": title, "body": body, "source": task_info.filename, "status": "OPEN"}


def call_with_retry(fn, max_retries: int = 3, base_delay: float = 2.0):
    """
    Call fn() with exponential backoff on transient errors.
    Does NOT retry configuration errors (missing API key, missing package).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if any(s in str(exc) for s in ("not set", "not installed", "API key")):
                raise  # configuration error — fail fast
            last_exc = exc
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


def _run_tests(repo_root: Path) -> tuple[bool, str]:
    """Run pytest independently. Returns (passed, combined_output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def _current_sha(repo_root: Path) -> str:
    """Return the current HEAD commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class AutonomousLoop:
    """
    End-to-end autonomous task execution from ai_agent/queue/.

    Each call to run_one() processes exactly one task. run_loop() processes
    all tasks until the queue is empty or escalation is triggered.

    Escalation: after max_consecutive_failures tasks fail in a row, the loop
    writes ai_agent/ESCALATE.md and stops. Delete that file to resume.
    """

    def __init__(
        self,
        mgr: QueueManager,
        dry_run: bool = True,
        max_plan_attempts: int = 2,
        max_llm_retries: int = 3,
        max_consecutive_failures: int = 3,
        sleep_between_tasks: float = 0.0,
        repo_root: Path = REPO_ROOT,
        escalate_file: Path = _DEFAULT_ESCALATE_FILE,
    ) -> None:
        self.mgr = mgr
        self.dry_run = dry_run
        self.max_plan_attempts = max_plan_attempts
        self.max_llm_retries = max_llm_retries
        self.max_consecutive_failures = max_consecutive_failures
        self.sleep_between_tasks = sleep_between_tasks
        self.repo_root = repo_root
        self.escalate_file = escalate_file
        self._consecutive_failures: int = 0
        self._results: list[TaskOutcome] = []
        self._stop_reason: LoopResult = LoopResult.QUEUE_EMPTY

    # -- Public API --

    def run_one(self) -> LoopResult:
        """
        Select and process the next task in the queue.

        Returns the outcome for that task, or QUEUE_EMPTY / ESCALATED if the
        loop cannot proceed.
        """
        if self.escalate_file.exists():
            print(f"[LOOP] Blocked — escalation file exists: {self.escalate_file}")
            print("[LOOP] Resolve the issues and delete it to resume.")
            return LoopResult.ESCALATED

        task_info = self.mgr.next_task()
        if task_info is None:
            return LoopResult.QUEUE_EMPTY

        start = time.monotonic()
        pre_sha = _current_sha(self.repo_root)

        self.mgr.mark_running(task_info.filename)
        self._log(task_info.filename, f"START  dry_run={self.dry_run}")

        task = load_task(task_info, self.mgr.queue_dir)
        memory = self._init_memory()
        specialist = assign_specialist(task)
        self._log(task_info.filename, f"ROLE   {specialist.ROLE}")

        feedback = ""
        outcome: Optional[TaskOutcome] = None

        for attempt in range(1, self.max_plan_attempts + 1):
            if attempt > 1:
                self._log(
                    task_info.filename,
                    f"RETRY  attempt={attempt} feedback={feedback[:100]}",
                )

            # 1. Plan — LLM call with retry and optional failure feedback
            try:
                patch_content = self._call_plan(task, specialist, memory, feedback)
            except Exception as exc:
                outcome = self._record_failure(task_info, f"LLM error: {exc}", attempt, start)
                break

            # 2. Review — regex safety check
            safe, violations = review(patch_content)
            if not safe:
                feedback = f"reviewer blocked: {', '.join(violations)}"
                self._log(task_info.filename, f"REVIEW {feedback}")
                if attempt == self.max_plan_attempts:
                    outcome = self._record_failure(task_info, feedback, attempt, start)
                continue  # retry with feedback

            self._log(task_info.filename, "REVIEW passed")

            # 3. Save patch to patches/
            patch_path = save_patch(task, specialist.ROLE, patch_content)
            self._log(task_info.filename, f"PATCH  {patch_path.name}")

            # 4a. Dry-run: save and mark done without touching the codebase
            if self.dry_run:
                self.mgr.mark_done(task_info.filename)
                elapsed = time.monotonic() - start
                self._log(task_info.filename, f"DONE   dry_run elapsed={elapsed:.1f}s")
                outcome = TaskOutcome(
                    filename=task_info.filename,
                    result=LoopResult.DRY_RUN,
                    attempt=attempt,
                    patch_path=patch_path,
                    elapsed_seconds=elapsed,
                )
                self._consecutive_failures = 0
                break

            # 4b. Apply — patcher runs tests, commits on pass, rolls back on fail
            self._log(task_info.filename, "APPLY  running patcher...")
            apply_result = patcher_module.execute(
                patch_path=patch_path,
                repo_root=self.repo_root,
                dry_run=False,
            )

            if not apply_result.success:
                if apply_result.rolled_back:
                    tr = apply_result.test_result
                    tail = (tr.stdout[-400:] if tr else "")
                    feedback = f"tests failed after apply (rolled back): {tail}"
                elif apply_result.validation and not apply_result.validation.valid:
                    feedback = (
                        "patch validation failed: "
                        + "; ".join(apply_result.validation.errors)
                    )
                else:
                    feedback = apply_result.error or "apply failed"
                self._log(task_info.filename, f"APPLY  FAILED {feedback[:120]}")
                if attempt == self.max_plan_attempts:
                    outcome = self._record_failure(task_info, feedback, attempt, start)
                continue  # retry with feedback

            # 5. Independent validation: pytest must pass
            tests_ok, test_output = _run_tests(self.repo_root)
            if not tests_ok:
                feedback = f"post-apply pytest failed: {test_output[-300:]}"
                self._log(task_info.filename, f"VALIDATE {feedback[:120]}")
                if attempt == self.max_plan_attempts:
                    outcome = self._record_failure(task_info, feedback, attempt, start)
                continue

            # 6. Independent validation: a new commit must exist
            post_sha = _current_sha(self.repo_root)
            commit_sha = apply_result.commit_sha or (post_sha if post_sha != pre_sha else None)
            if not commit_sha:
                feedback = "no new commit detected after apply"
                self._log(task_info.filename, f"VALIDATE {feedback}")
                if attempt == self.max_plan_attempts:
                    outcome = self._record_failure(task_info, feedback, attempt, start)
                continue

            # 7. All checks passed — mark done
            self.mgr.mark_done(task_info.filename)
            elapsed = time.monotonic() - start
            self._log(task_info.filename, f"DONE   commit={commit_sha} elapsed={elapsed:.1f}s")
            outcome = TaskOutcome(
                filename=task_info.filename,
                result=LoopResult.DONE,
                attempt=attempt,
                patch_path=patch_path,
                commit_sha=commit_sha,
                elapsed_seconds=elapsed,
            )
            self._consecutive_failures = 0
            break

        if outcome is None:
            outcome = self._record_failure(
                task_info, "exhausted all attempts", self.max_plan_attempts, start
            )

        self._results.append(outcome)

        if outcome.result == LoopResult.FAILED:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_consecutive_failures:
                self._escalate()
                self._stop_reason = LoopResult.ESCALATED
                return LoopResult.ESCALATED

        return outcome.result

    def run_loop(self) -> list[TaskOutcome]:
        """
        Process all queued tasks until the queue is empty or escalation fires.

        Generates morning_report.md on completion. Returns all task outcomes.
        """
        while True:
            result = self.run_one()
            if result in (LoopResult.QUEUE_EMPTY, LoopResult.ESCALATED):
                self._stop_reason = result
                break
            if self.sleep_between_tasks > 0:
                time.sleep(self.sleep_between_tasks)
        self.mgr.generate_morning_report()
        return list(self._results)

    # -- Private helpers --

    def _call_plan(
        self, task: dict, specialist, memory, feedback: str
    ) -> str:
        """Invoke specialist.plan() with failure feedback injected into the task body."""
        if feedback:
            task = {
                **task,
                "body": (
                    task["body"]
                    + f"\n\n## Previous Attempt Feedback\n\n{feedback}\n\n"
                    "Please address the above issue in your revised patch.\n"
                ),
            }
        return call_with_retry(
            lambda: specialist.plan(task, memory=memory),
            max_retries=self.max_llm_retries,
        )

    def _init_memory(self):
        try:
            mem = get_memory(self.repo_root)
            mem.update()
            return mem
        except Exception:
            return None

    def _record_failure(
        self, task_info: TaskInfo, error: str, attempt: int, start: float
    ) -> TaskOutcome:
        self.mgr.mark_failed(task_info.filename, error[:200])
        elapsed = time.monotonic() - start
        self._log(task_info.filename, f"FAILED {error[:200]} elapsed={elapsed:.1f}s")
        return TaskOutcome(
            filename=task_info.filename,
            result=LoopResult.FAILED,
            attempt=attempt,
            error=error,
            elapsed_seconds=elapsed,
        )

    def _log(self, filename: str, message: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[LOOP] {filename}  {message}")
        self.mgr._write_log(filename, f"[{ts}] {message}")

    def _escalate(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        recent = [r for r in self._results if r.result == LoopResult.FAILED]
        lines = [
            f"# Escalation Notice — {ts}",
            "",
            f"**{self._consecutive_failures} consecutive failures.**"
            " Human review required before the loop can continue.",
            "",
            "## Recent Failures",
            "",
        ]
        for r in recent[-self.max_consecutive_failures:]:
            lines.append(f"- `{r.filename}`: {r.error or '(no detail)'}")
        lines += [
            "",
            "## Resolution",
            "",
            "1. Review per-task logs in `ai_agent/logs/`",
            "2. Fix the task specification or underlying issue",
            "3. Delete this file to allow the loop to resume",
            "",
        ]
        self.escalate_file.write_text("\n".join(lines))
        print(f"[LOOP] ESCALATED — wrote {self.escalate_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary(outcomes: list[TaskOutcome]) -> None:
    done = sum(1 for o in outcomes if o.result in (LoopResult.DONE, LoopResult.DRY_RUN))
    failed = sum(1 for o in outcomes if o.result == LoopResult.FAILED)
    print(f"\n[LOOP] Summary: {done} succeeded, {failed} failed, {len(outcomes)} total")
    for o in outcomes:
        marker = "✓" if o.result in (LoopResult.DONE, LoopResult.DRY_RUN) else "✗"
        sha = f" [{o.commit_sha}]" if o.commit_sha else ""
        err = f" — {o.error[:60]}" if o.error else ""
        attempts = f" (attempt {o.attempt})" if o.attempt > 1 else ""
        print(f"  {marker} {o.filename}{sha}{err}{attempts}")


def _main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m ai_agent.loop",
        description="Autonomous engineering loop — processes tasks from ai_agent/queue/",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply patches and commit (default: dry-run, patches saved only)",
    )
    parser.add_argument(
        "--all", action="store_true", dest="run_all",
        help="Process all queued tasks (default: one task)",
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Keep checking for new tasks after queue drains (implies --all)",
    )
    parser.add_argument(
        "--max-failures", type=int, default=3, metavar="N",
        help="Consecutive failures before escalating (default: 3)",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.0, metavar="SECS",
        help="Seconds to sleep between tasks (default: 0)",
    )
    parser.add_argument(
        "--attempts", type=int, default=2, metavar="N",
        help="Max LLM plan attempts per task, with feedback (default: 2)",
    )
    args = parser.parse_args(argv)

    dry_run = not args.apply
    run_all = args.run_all or args.daemon

    mode = "DRY-RUN (patches saved, not applied)" if dry_run else "APPLY (patches applied and committed)"
    print(f"[LOOP] Mode: {mode}")
    print(f"[LOOP] Queue: {QUEUE_DIR}")

    mgr = QueueManager()
    loop = AutonomousLoop(
        mgr=mgr,
        dry_run=dry_run,
        max_plan_attempts=args.attempts,
        max_consecutive_failures=args.max_failures,
        sleep_between_tasks=args.sleep,
    )

    if args.daemon:
        idle = 0
        while idle < _DAEMON_MAX_IDLE:
            outcomes = loop.run_loop()
            if loop._stop_reason == LoopResult.ESCALATED:
                break
            if not outcomes:
                idle += 1
                print(
                    f"[LOOP] Queue empty — sleeping {_DAEMON_IDLE_INTERVAL}s "
                    f"(idle {idle}/{_DAEMON_MAX_IDLE})"
                )
                time.sleep(_DAEMON_IDLE_INTERVAL)
            else:
                idle = 0
                _print_summary(outcomes)
        print("[LOOP] Daemon exiting.")
    elif run_all:
        outcomes = loop.run_loop()
        _print_summary(outcomes)
    else:
        result = loop.run_one()
        print(f"[LOOP] Result: {result}")
        if loop._results:
            _print_summary(loop._results)


if __name__ == "__main__":
    _main()
