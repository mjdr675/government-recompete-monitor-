"""
Manager agent — orchestrates the multi-agent system.

Responsibilities:
- Read backlog files (critical → bugs → high → medium → TASK.md)
- Pick the highest-priority OPEN task
- Assign it to the right specialist role
- Get a plan from that specialist
- Write the plan to HANDOFF.md
- Log the run to TASK_LOG.md

Does not edit application files in this version.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Specialist agents
from ai_agent import backend_engineer, frontend_engineer, qa_engineer
from ai_agent import devops_engineer, docs_writer

REPO_ROOT = Path(__file__).parent.parent
HANDOFF_FILE = REPO_ROOT / "HANDOFF.md"
TASK_LOG_FILE = REPO_ROOT / "TASK_LOG.md"
TASK_FILE = REPO_ROOT / "TASK.md"

BACKLOG_ORDER = [
    REPO_ROOT / "backlog" / "critical.md",
    REPO_ROOT / "backlog" / "bugs.md",
    REPO_ROOT / "backlog" / "high.md",
    REPO_ROOT / "backlog" / "medium.md",
    TASK_FILE,
    # ideas.md is never auto-picked — humans promote tasks from it manually
]

SPECIALISTS = [
    devops_engineer,
    qa_engineer,
    frontend_engineer,
    docs_writer,
    backend_engineer,   # default — checked last
]

# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------

def _parse_tasks(path: Path) -> list[dict]:
    tasks = []
    current = None
    source = path.name
    for line in path.read_text().splitlines():
        m = re.match(r"^###\s+\[(\w+)\]\s+(.+)$", line)
        if m:
            if current:
                tasks.append(current)
            current = {
                "status": m.group(1),
                "title": m.group(2),
                "body": "",
                "source": source,
            }
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
    return backend_engineer   # safe default


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_handoff(task: dict, role: str, plan: str) -> None:
    ts = _timestamp()
    entry = (
        f"\n## {ts} — [{role.upper()}] {task['title']}\n"
        f"**Source:** {task['source']}  \n"
        f"**Assigned to:** {role}  \n"
        f"**Status:** plan generated (dry-run)\n\n"
        f"**Plan:**\n{plan}\n"
    )
    with open(HANDOFF_FILE, "a") as f:
        f.write(entry)
    print(f"[HANDOFF] Written to {HANDOFF_FILE.name}")


def write_task_log(task: dict, role: str, plan: str) -> None:
    ts = _timestamp()
    # Create file with header if it doesn't exist
    if not TASK_LOG_FILE.exists():
        TASK_LOG_FILE.write_text(
            "# TASK_LOG.md — Completed / Attempted Task History\n\n"
            "Append-only log. Each row = one agent run.\n\n"
            "| Timestamp | Role | Task | Source | Outcome |\n"
            "|---|---|---|---|---|\n"
        )
    with open(TASK_LOG_FILE, "a") as f:
        title_short = task["title"][:60]
        f.write(f"| {ts} | {role} | {title_short} | {task['source']} | plan-only |\n")
    print(f"[TASK_LOG] Written to {TASK_LOG_FILE.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = True) -> None:
    print("\n[MANAGER] Loading tasks from backlog + TASK.md...")
    tasks = load_all_tasks()
    open_tasks = [t for t in tasks if t["status"] == "OPEN"]
    print(f"[MANAGER] {len(open_tasks)} open tasks across {len(BACKLOG_ORDER)} sources.")

    task = next_open_task(tasks)
    if not task:
        print("[MANAGER] No OPEN tasks found. Nothing to do.")
        return

    specialist = assign_specialist(task)
    role = specialist.ROLE

    print(f"\n[MANAGER] Selected task : {task['title']}")
    print(f"[MANAGER] Source        : {task['source']}")
    print(f"[MANAGER] Assigned to   : {role}")

    print(f"\n[{role.upper()}] Generating plan...")
    plan = specialist.plan(task)
    print(f"\n--- Plan ---\n{plan}")

    write_handoff(task, role, plan)
    write_task_log(task, role, plan)

    if dry_run:
        print("\n[MANAGER] DRY_RUN=true — no files edited, no commits made.")
    else:
        print("\n[MANAGER] DRY_RUN=false — edit/commit step would run here.")
