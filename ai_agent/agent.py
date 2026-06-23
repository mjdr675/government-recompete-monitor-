"""
AI agent entry point — delegates to manager.py for multi-agent orchestration.

Usage:
    DRY_RUN=true python ai_agent/agent.py        # plan only (default)
    DRY_RUN=false python ai_agent/agent.py       # enable edits + commits

Set up:
    cp ai_agent/.env.example ai_agent/.env
    # fill in ANTHROPIC_API_KEY in ai_agent/.env
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AGENT_DIR = Path(__file__).parent
REPO_ROOT = AGENT_DIR.parent
TASK_FILE = REPO_ROOT / "TASK.md"
HANDOFF_FILE = REPO_ROOT / "HANDOFF.md"

# Make repo root importable when running as `python ai_agent/agent.py`
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
AGENT_BRANCH = os.environ.get("AGENT_BRANCH", "ai-agent")

# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS = [
    r"git\s+push",
    r"rm\s+-rf",
    r"\.env",
    r"shutil\.rmtree",
    r"os\.remove",
    r"DROP\s+TABLE",
    r"ANTHROPIC_API_KEY",
    r"OPENAI_API_KEY",
    r"sk-",
]

def is_safe_command(cmd: str) -> bool:
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            print(f"[SAFETY BLOCK] Refused command matching '{pattern}': {cmd!r}")
            return False
    return True


def run(cmd: str, capture: bool = True) -> str:
    """Run a shell command safely. Blocks dangerous patterns."""
    if not is_safe_command(cmd):
        return ""
    result = subprocess.run(
        cmd, shell=True, cwd=REPO_ROOT,
        capture_output=capture, text=True
    )
    return (result.stdout or "").strip()

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def current_branch() -> str:
    return run("git rev-parse --abbrev-ref HEAD")


def git_status() -> str:
    return run("git status --short")


def git_log(n: int = 5) -> str:
    return run(f"git log --oneline -{n}")

# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------

def load_tasks() -> list[dict]:
    """Parse TASK.md and return list of task dicts."""
    if not TASK_FILE.exists():
        print(f"[ERROR] {TASK_FILE} not found.")
        sys.exit(1)

    tasks = []
    current = None
    for line in TASK_FILE.read_text().splitlines():
        m = re.match(r"^###\s+\[(\w+)\]\s+(.+)$", line)
        if m:
            if current:
                tasks.append(current)
            current = {"status": m.group(1), "title": m.group(2), "body": ""}
        elif current:
            current["body"] += line + "\n"

    if current:
        tasks.append(current)

    return tasks


def next_open_task(tasks: list[dict]) -> dict | None:
    return next((t for t in tasks if t["status"] == "OPEN"), None)

# ---------------------------------------------------------------------------
# Plan step (placeholder for AI call)
# ---------------------------------------------------------------------------

def plan_task(task: dict) -> str:
    """
    Generate a plan for the given task.

    TODO: replace the stub below with a real API call, e.g.:

        import anthropic
        client = anthropic.Anthropic()           # reads ANTHROPIC_API_KEY
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    Or with the OpenAI SDK:

        from openai import OpenAI
        client = OpenAI()                        # reads OPENAI_API_KEY
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    """
    prompt = f"""
You are a lead engineer for a Flask + SQLite government contract intelligence app.

Task: {task['title']}

Details:
{task['body'].strip()}

Current git status:
{git_status() or '(clean)'}

Recent commits:
{git_log()}

Write a concise step-by-step plan to complete this task.
Be specific about which files and functions to change.
Do not write any code yet — plan only.
""".strip()

    # --- STUB: replace with real API call ---
    print("\n[AI STUB] Would send this prompt to the AI API:\n")
    print("=" * 60)
    print(prompt)
    print("=" * 60)
    return "[PLAN STUB] Connect an AI API to generate a real plan."


# ---------------------------------------------------------------------------
# Edit / test / commit stubs
# ---------------------------------------------------------------------------

def edit_files(plan: str) -> bool:
    """
    TODO: parse the plan and apply edits.
    In the real version this calls the AI again with a 'now implement it' prompt
    and applies the returned file patches.
    """
    print("\n[STUB] edit_files() — not implemented yet.")
    return False


def run_tests() -> bool:
    """Run the test suite and return True if it passes."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
    return result.returncode == 0


def commit_changes(task: dict) -> bool:
    """
    Stage changed files and commit.
    Blocked entirely in DRY_RUN mode.
    git push is always blocked by the safety layer.
    """
    if DRY_RUN:
        print("[DRY RUN] Skipping commit.")
        return False
    branch = current_branch()
    if branch != AGENT_BRANCH:
        print(f"[SAFETY BLOCK] On branch '{branch}', expected '{AGENT_BRANCH}'. Refusing to commit.")
        return False
    run(f'git add -A && git commit -m "agent: {task["title"]}"')
    return True


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------

def write_handoff(task: dict, plan: str, committed: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = (
        f"\n## {ts} — {task['title']}\n"
        f"**Status:** {'committed' if committed else 'dry-run / plan only'}\n\n"
        f"**Plan:**\n{plan}\n\n"
        f"**Git status after run:**\n```\n{git_status() or '(clean)'}\n```\n"
    )
    with open(HANDOFF_FILE, "a") as f:
        f.write(entry)
    print(f"\n[HANDOFF] Written to {HANDOFF_FILE}")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("AI AGENT — government-recompete-monitor")
    print(f"DRY_RUN : {DRY_RUN}")
    print(f"Branch  : {current_branch()}")
    print(f"Repo    : {REPO_ROOT}")
    print("=" * 60)

    # Safety: check branch in non-dry-run mode
    if not DRY_RUN and current_branch() != AGENT_BRANCH:
        print(f"\n[SAFETY BLOCK] DRY_RUN=false but branch is '{current_branch()}', not '{AGENT_BRANCH}'.")
        print("Create and switch to the agent branch first:")
        print(f"    git checkout -b {AGENT_BRANCH}")
        sys.exit(1)

    print("\n--- Git status ---")
    print(git_status() or "(clean)")
    print("\n--- Recent commits ---")
    print(git_log())

    # Delegate to manager for task selection, role assignment, planning, and logging
    from ai_agent.manager import run as manager_run
    manager_run(dry_run=DRY_RUN)

    print("\n[AGENT] Run complete.")
    if DRY_RUN:
        print("Set DRY_RUN=false (and connect an AI API) to enable edits.")


if __name__ == "__main__":
    main()
