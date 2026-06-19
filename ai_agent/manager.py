"""
Manager — orchestrates the full pipeline:
  load tasks → assign specialist → call LLM → review patch → save patch
  → (if APPLY_PATCH=true and DRY_RUN=false) apply changes

Environment switches:
  DRY_RUN=true      Never edit files. Show patch and write HANDOFF.md. (default)
  DRY_RUN=false     Enable the apply stage.
  APPLY_PATCH=true  Actually apply the patch. Requires DRY_RUN=false.
                    Disabled by default — enable only after review.
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ai_agent import backend_engineer, frontend_engineer, qa_engineer
from ai_agent import devops_engineer, docs_writer
from ai_agent import llm as llm_module
from ai_agent.memory import get_memory
from ai_agent.patcher import execute as patcher_execute, list_pending
from ai_agent.reviewer import review

REPO_ROOT = Path(__file__).parent.parent
HANDOFF_FILE = REPO_ROOT / "HANDOFF.md"
TASK_LOG_FILE = REPO_ROOT / "TASK_LOG.md"
PATCHES_DIR = REPO_ROOT / "patches"

BACKLOG_ORDER = [
    REPO_ROOT / "backlog" / "critical.md",
    REPO_ROOT / "backlog" / "bugs.md",
    REPO_ROOT / "backlog" / "high.md",
    REPO_ROOT / "backlog" / "medium.md",
    REPO_ROOT / "TASK.md",
]

SPECIALISTS = [
    devops_engineer,
    qa_engineer,
    frontend_engineer,
    docs_writer,
    backend_engineer,   # default — checked last
]

# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def _parse_tasks(path: Path) -> list[dict]:
    tasks, current = [], None
    for line in path.read_text().splitlines():
        m = re.match(r"^###\s+\[(\w+)\]\s+(.+)$", line)
        if m:
            if current:
                tasks.append(current)
            current = {"status": m.group(1), "title": m.group(2),
                       "body": "", "source": path.name}
        elif current:
            current["body"] += line + "\n"
    if current:
        tasks.append(current)
    return tasks


def load_all_tasks() -> list[dict]:
    tasks = []
    for path in BACKLOG_ORDER:
        if path.exists():
            tasks.extend(_parse_tasks(path))
    return tasks


def next_open_task(tasks: list[dict]) -> dict | None:
    return next((t for t in tasks if t["status"] == "OPEN"), None)

# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------

def assign_specialist(task: dict):
    for specialist in SPECIALISTS:
        if specialist.can_handle(task):
            return specialist
    return backend_engineer

# ---------------------------------------------------------------------------
# Patch saving
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:40].strip("_")


def save_patch(task: dict, role: str, content: str) -> Path:
    PATCHES_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{role}_{_slug(task['title'])}.md"
    path = PATCHES_DIR / filename
    header = (
        f"# Proposed Patch\n"
        f"**Task:** {task['title']}  \n"
        f"**Source:** {task['source']}  \n"
        f"**Role:** {role}  \n"
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}  \n"
        f"**Status:** proposed — not applied  \n\n"
        f"---\n\n"
    )
    path.write_text(header + content)
    return path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_handoff(task: dict, role: str, patch_content: str,
                  patch_path: Path, safe: bool, violations: list[str]) -> None:
    review_status = "PASSED" if safe else f"BLOCKED — {', '.join(violations)}"
    entry = (
        f"\n## {_ts()} — [{role.upper()}] {task['title']}\n"
        f"**Source:** {task['source']}  \n"
        f"**Role:** {role}  \n"
        f"**Review:** {review_status}  \n"
        f"**Patch saved:** `{patch_path.relative_to(REPO_ROOT)}`  \n\n"
        f"<details><summary>Proposed patch</summary>\n\n"
        f"{patch_content}\n"
        f"</details>\n"
    )
    with open(HANDOFF_FILE, "a") as f:
        f.write(entry)
    print(f"[HANDOFF] Written to {HANDOFF_FILE.name}")


def write_task_log(task: dict, role: str, outcome: str) -> None:
    if not TASK_LOG_FILE.exists():
        TASK_LOG_FILE.write_text(
            "# TASK_LOG.md — Run History\n\n"
            "| Timestamp | Role | Task | Source | Outcome |\n"
            "|---|---|---|---|---|\n"
        )
    with open(TASK_LOG_FILE, "a") as f:
        f.write(f"| {_ts()} | {role} | {task['title'][:60]} "
                f"| {task['source']} | {outcome} |\n")
    print(f"[TASK_LOG] Written to {TASK_LOG_FILE.name}")

# ---------------------------------------------------------------------------
# Apply stage — delegates to patcher.execute()
# ---------------------------------------------------------------------------

def apply_patch(patch_path: Path, dry_run: bool) -> None:
    result = patcher_execute(
        patch_path=patch_path,
        repo_root=REPO_ROOT,
        dry_run=dry_run,
        handoff_path=HANDOFF_FILE,
        task_log_path=TASK_LOG_FILE,
    )
    if result.success and result.commit_sha:
        print(f"[APPLY] Committed: {result.commit_sha}")
    elif result.rolled_back:
        print(f"[APPLY] Tests failed — repository restored. Report: {result.failure_report}")
    elif not result.success:
        print(f"[APPLY] Failed: {result.error}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = True) -> None:
    apply_patch_enabled = os.environ.get("APPLY_PATCH", "false").lower() == "true"

    # --- Repository memory: update index for changed files ---
    mem = get_memory(REPO_ROOT)
    index_result = mem.update()
    s = mem.stats()
    print(f"\n[MEMORY] Index updated — {index_result['indexed']} re-indexed, "
          f"{index_result['skipped']} unchanged")
    print(f"[MEMORY] {s['files']} files | {s['functions']} functions | "
          f"{s['routes']} routes | {s['templates']} template refs")

    print("\n[MANAGER] Loading tasks...")
    tasks = load_all_tasks()
    open_count = sum(1 for t in tasks if t["status"] == "OPEN")
    print(f"[MANAGER] {open_count} open tasks found.")

    task = next_open_task(tasks)
    if not task:
        print("[MANAGER] No OPEN tasks. Nothing to do.")
        return

    specialist = assign_specialist(task)
    role = specialist.ROLE

    print(f"\n[MANAGER] Task   : {task['title']}")
    print(f"[MANAGER] Source : {task['source']}")
    print(f"[MANAGER] Role   : {role}")

    # --- LLM availability check ---
    if not llm_module.available():
        print("\n[LLM] ANTHROPIC_API_KEY not set or anthropic not installed.")
        print("[LLM] Set the key and run: pip install anthropic")
        write_task_log(task, role, "skipped — no LLM key")
        return

    # --- Call specialist — passes memory so it can query the index ---
    print(f"\n[{role.upper()}] Calling LLM...")
    try:
        patch_content = specialist.plan(task, memory=mem)
    except Exception as exc:
        print(f"[ERROR] LLM call failed: {exc}")
        write_task_log(task, role, f"error — {exc}")
        return

    # --- Review ---
    print("\n[REVIEW] Scanning patch for dangerous patterns...")
    safe, violations = review(patch_content)
    if safe:
        print("[REVIEW] PASSED — no dangerous patterns found.")
    else:
        print(f"[REVIEW] BLOCKED — violations: {violations}")

    # --- Save patch ---
    patch_path = save_patch(task, role, patch_content)
    print(f"\n[PATCH] Saved to {patch_path.relative_to(REPO_ROOT)}")

    # --- Show patch ---
    print("\n" + "=" * 60)
    print(patch_content)
    print("=" * 60)

    # --- Write logs ---
    outcome = "patch-saved" if safe else f"blocked:{','.join(violations)}"
    write_handoff(task, role, patch_content, patch_path, safe, violations)
    write_task_log(task, role, outcome)

    # --- Apply gate ---
    if not dry_run and apply_patch_enabled and safe:
        print("\n[APPLY] APPLY_PATCH=true and DRY_RUN=false — executing patcher...")
        apply_patch(patch_path, dry_run=False)
    elif not dry_run and apply_patch_enabled and not safe:
        print("\n[APPLY] Patch blocked by reviewer — not applied.")
    else:
        print(
            "\n[DRY_RUN] Patch saved for review. To apply:\n"
            f"  DRY_RUN=false APPLY_PATCH=true python ai_agent/agent.py\n"
            f"  or: python -m ai_agent.patcher --apply"
        )


# ---------------------------------------------------------------------------
# Queue-based task manager (Task 044)
# ---------------------------------------------------------------------------

_AGENT_DIR = Path(__file__).parent

QUEUE_DIR = _AGENT_DIR / "queue"
DONE_DIR = _AGENT_DIR / "done"
FAILED_DIR = _AGENT_DIR / "failed"
LOGS_DIR = _AGENT_DIR / "logs"
MORNING_REPORT_PATH = _AGENT_DIR / "morning_report.md"
QUEUE_STATE_FILE = _AGENT_DIR / ".queue_state.json"


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    filename: str
    state: TaskState
    started_at: str | None = None
    note: str = ""

    @property
    def name(self) -> str:
        return self.filename.removesuffix(".md")


class QueueManager:
    """
    Manages the ai_agent/queue/ task pipeline.

    State machine:  queued → running → completed
                                     ↘ failed

    State is persisted in .queue_state.json so a crashed or interrupted
    run can be detected and resumed on the next invocation.

    Usage:
        mgr = QueueManager()
        task = mgr.next_task()          # first queued (or interrupted)
        mgr.mark_running(task.filename)
        # ... do work ...
        mgr.mark_done(task.filename)    # moves file to done/
        mgr.generate_morning_report()   # writes morning_report.md
    """

    def __init__(
        self,
        queue_dir: Path = QUEUE_DIR,
        done_dir: Path = DONE_DIR,
        failed_dir: Path = FAILED_DIR,
        logs_dir: Path = LOGS_DIR,
        report_path: Path = MORNING_REPORT_PATH,
        state_file: Path = QUEUE_STATE_FILE,
    ) -> None:
        self.queue_dir = queue_dir
        self.done_dir = done_dir
        self.failed_dir = failed_dir
        self.logs_dir = logs_dir
        self.report_path = report_path
        self._state_file = state_file
        self._state: dict = self._load_state()

    # -- State persistence --

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(self) -> None:
        self._state_file.write_text(json.dumps(self._state, indent=2))

    # -- Task discovery --

    def _md_files(self, directory: Path) -> list[str]:
        if not directory.exists():
            return []
        return sorted(p.name for p in directory.glob("*.md"))

    def all_tasks(self) -> list[TaskInfo]:
        """Return all known tasks across all state buckets, sorted by filename."""
        running_file = self._state.get("running")
        tasks: list[TaskInfo] = []

        for name in self._md_files(self.done_dir):
            tasks.append(TaskInfo(filename=name, state=TaskState.COMPLETED))

        for name in self._md_files(self.failed_dir):
            tasks.append(TaskInfo(filename=name, state=TaskState.FAILED))

        for name in self._md_files(self.queue_dir):
            if name == running_file:
                tasks.append(TaskInfo(
                    filename=name,
                    state=TaskState.RUNNING,
                    started_at=self._state.get("started_at"),
                ))
            else:
                tasks.append(TaskInfo(filename=name, state=TaskState.QUEUED))

        return tasks

    def queued(self) -> list[TaskInfo]:
        return [t for t in self.all_tasks() if t.state == TaskState.QUEUED]

    def running(self) -> TaskInfo | None:
        return next((t for t in self.all_tasks() if t.state == TaskState.RUNNING), None)

    def completed(self) -> list[TaskInfo]:
        return [t for t in self.all_tasks() if t.state == TaskState.COMPLETED]

    def failed(self) -> list[TaskInfo]:
        return [t for t in self.all_tasks() if t.state == TaskState.FAILED]

    def next_task(self) -> TaskInfo | None:
        """Returns the running (interrupted) task if any, otherwise the first queued task."""
        r = self.running()
        if r:
            return r
        q = self.queued()
        return q[0] if q else None

    # -- State transitions --

    def mark_running(self, filename: str) -> None:
        """Mark a queued task as running and persist state."""
        self._state = {"running": filename, "started_at": _ts()}
        self._save_state()
        self._write_log(filename, f"START {_ts()}")

    def mark_done(self, filename: str) -> None:
        """Move task file to done/ and clear running state."""
        self._move(self.queue_dir / filename, self.done_dir / filename)
        if self._state.get("running") == filename:
            self._state = {"running": None, "started_at": None}
            self._save_state()
        self._write_log(filename, f"DONE  {_ts()}")

    def mark_failed(self, filename: str, note: str = "") -> None:
        """Move task file to failed/ and clear running state."""
        self._move(self.queue_dir / filename, self.failed_dir / filename)
        if self._state.get("running") == filename:
            self._state = {"running": None, "started_at": None}
            self._save_state()
        self._write_log(filename, f"FAIL  {_ts()} {note}".rstrip())

    @staticmethod
    def _move(src: Path, dst: Path) -> None:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)

    # -- Logging --

    def _write_log(self, filename: str, message: str) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        stem = filename.removesuffix(".md")
        log_path = self.logs_dir / f"{stem}.log"
        with open(log_path, "a") as f:
            f.write(message + "\n")

    # -- Status / reporting --

    def status(self) -> dict[str, list[str]]:
        tasks = self.all_tasks()
        return {
            "queued":    [t.filename for t in tasks if t.state == TaskState.QUEUED],
            "running":   [t.filename for t in tasks if t.state == TaskState.RUNNING],
            "completed": [t.filename for t in tasks if t.state == TaskState.COMPLETED],
            "failed":    [t.filename for t in tasks if t.state == TaskState.FAILED],
        }

    def generate_morning_report(self) -> str:
        """Write ai_agent/morning_report.md and return its contents."""
        s = self.status()
        lines = [
            f"# Morning Report — {_ts()}",
            "",
            "## Summary",
            f"- Queued:    {len(s['queued'])}",
            f"- Running:   {len(s['running'])}",
            f"- Completed: {len(s['completed'])}",
            f"- Failed:    {len(s['failed'])}",
            "",
        ]

        if s["running"]:
            lines += ["## In Progress", ""]
            for fname in s["running"]:
                started = self._state.get("started_at", "unknown")
                lines.append(f"- `{fname}` (started {started})")
            lines.append("")

        if s["queued"]:
            lines += ["## Queued", ""]
            for fname in s["queued"]:
                lines.append(f"- `{fname}`")
            lines.append("")

        if s["completed"]:
            lines += ["## Completed", ""]
            for fname in s["completed"]:
                lines.append(f"- `{fname}`")
            lines.append("")

        if s["failed"]:
            lines += ["## Failed", ""]
            for fname in s["failed"]:
                lines.append(f"- `{fname}`")
            lines.append("")

        report = "\n".join(lines)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(report)
        return report

    def print_status(self) -> None:
        s = self.status()
        print(f"\n[QUEUE] Status at {_ts()}")
        print(f"  queued:    {len(s['queued'])}")
        print(f"  running:   {len(s['running'])}")
        print(f"  completed: {len(s['completed'])}")
        print(f"  failed:    {len(s['failed'])}")

        r = self.running()
        if r:
            started = r.started_at or "unknown"
            print(f"\n[QUEUE] Currently running: {r.filename}  (started {started})")
            print("[QUEUE] This task may have been interrupted — resume or mark done/failed.")

        nxt = self.next_task()
        if nxt and nxt.state == TaskState.QUEUED:
            print(f"\n[QUEUE] Next up: {nxt.filename}")


# ---------------------------------------------------------------------------
# CLI entry point for QueueManager
# ---------------------------------------------------------------------------

def _queue_cli(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ai_agent.manager",
        description="AI task queue manager",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show queue status")
    sub.add_parser("next", help="Show the next task to work on")
    sub.add_parser("report", help="Generate morning_report.md")

    p_start = sub.add_parser("start", help="Mark a task as running")
    p_start.add_argument("filename", help="e.g. 044-ai-engineering-manager.md")

    p_done = sub.add_parser("done", help="Mark a task as completed")
    p_done.add_argument("filename")

    p_fail = sub.add_parser("fail", help="Mark a task as failed")
    p_fail.add_argument("filename")
    p_fail.add_argument("note", nargs="?", default="", help="Optional failure note")

    args = parser.parse_args(argv)
    mgr = QueueManager()

    if args.cmd == "status" or args.cmd is None:
        mgr.print_status()

    elif args.cmd == "next":
        task = mgr.next_task()
        if task:
            print(f"[QUEUE] Next: {task.filename}  ({task.state})")
        else:
            print("[QUEUE] No tasks pending.")

    elif args.cmd == "report":
        report = mgr.generate_morning_report()
        print(report)
        print(f"[QUEUE] Report written to {mgr.report_path}")

    elif args.cmd == "start":
        mgr.mark_running(args.filename)
        print(f"[QUEUE] Marked running: {args.filename}")

    elif args.cmd == "done":
        mgr.mark_done(args.filename)
        print(f"[QUEUE] Marked done: {args.filename}")

    elif args.cmd == "fail":
        mgr.mark_failed(args.filename, args.note)
        print(f"[QUEUE] Marked failed: {args.filename}")


if __name__ == "__main__":
    _queue_cli()
