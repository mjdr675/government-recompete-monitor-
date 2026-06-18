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

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_agent import backend_engineer, frontend_engineer, qa_engineer
from ai_agent import devops_engineer, docs_writer
from ai_agent import llm as llm_module
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
# Apply stage (gated — enable with APPLY_PATCH=true + DRY_RUN=false)
# ---------------------------------------------------------------------------

def apply_patch(patch_content: str) -> None:
    """
    Future: parse Before/After blocks and write file changes.
    Blocked until APPLY_PATCH=true is set explicitly.
    """
    print("[APPLY] apply_patch() is not implemented yet.")
    print("[APPLY] Set APPLY_PATCH=true only after reviewing the patch file.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = True) -> None:
    apply_patch_enabled = os.environ.get("APPLY_PATCH", "false").lower() == "true"

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

    # --- Call specialist (hits LLM) ---
    print(f"\n[{role.upper()}] Calling LLM...")
    try:
        patch_content = specialist.plan(task)
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
        print("\n[APPLY] APPLY_PATCH=true and DRY_RUN=false — applying patch...")
        apply_patch(patch_content)
    elif not dry_run and apply_patch_enabled and not safe:
        print("\n[APPLY] Patch blocked by review — not applied.")
    else:
        print(
            "\n[DRY_RUN] Patch not applied.\n"
            "To apply: set DRY_RUN=false APPLY_PATCH=true (after reviewing the patch)."
        )
