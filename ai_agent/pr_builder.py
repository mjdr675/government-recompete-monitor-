"""
PR Builder — generates GitHub pull request drafts from git state.

Collects:
  - Changed files (git diff --name-only vs base branch)
  - Commits since base branch (git log --oneline)
  - Completed tasks from ai_agent/done/
  - Test results (optional pytest run)

Saves a draft to ai_agent/pr_drafts/<timestamp>-<slug>.md.

Usage:
  from ai_agent.pr_builder import build_pr_draft
  draft = build_pr_draft(base_branch="main")

CLI:
  python -m ai_agent.pr_builder
  python -m ai_agent.pr_builder --base main --run-tests
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
_AGENT_DIR = Path(__file__).parent
PR_DRAFTS_DIR = _AGENT_DIR / "pr_drafts"


@dataclass
class PRDraft:
    title: str
    description: str
    completed_tasks: list[str]
    changed_files: list[str]
    commits: list[str]
    test_summary: str
    base_branch: str
    generated_at: str
    draft_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    """Run a git command and return stdout. Returns empty string on error."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _get_changed_files(base_branch: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return files changed vs base_branch (three-dot diff)."""
    output = _git("diff", "--name-only", f"{base_branch}...HEAD", cwd=repo_root)
    return [f for f in output.splitlines() if f.strip()] if output else []


def _get_commits(base_branch: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return one-line commit messages since base_branch diverged."""
    output = _git("log", "--oneline", f"{base_branch}...HEAD", cwd=repo_root)
    return [c for c in output.splitlines() if c.strip()] if output else []


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def _get_completed_tasks(done_dir: Path) -> list[str]:
    """Return sorted task stems from the done/ directory."""
    if not done_dir.exists():
        return []
    return sorted(p.stem for p in done_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_tests(repo_root: Path = REPO_ROOT) -> str:
    """Run pytest and return a one-line summary string."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (result.stdout + result.stderr).strip()
    lines = [ln for ln in output.splitlines() if ln.strip()]
    return lines[-1] if lines else "(no test output)"


# ---------------------------------------------------------------------------
# Title / description generation
# ---------------------------------------------------------------------------

def _generate_title(commits: list[str], completed_tasks: list[str]) -> str:
    """Generate a concise PR title from task names or commit messages."""
    if completed_tasks:
        last = completed_tasks[-1]
        parts = last.split("-", 1)
        if len(parts) == 2 and parts[0].isdigit():
            slug = parts[1].replace("-", " ").title()
            return f"Task {parts[0]}: {slug}"
        return last.replace("-", " ").title()
    if commits:
        # Strip leading 7-char SHA + space
        msg = commits[0]
        if len(msg) > 8:
            return msg[8:].strip()
        return msg
    return "Automated engineering update"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:40].strip("_")


def _generate_description(
    title: str,
    completed_tasks: list[str],
    changed_files: list[str],
    commits: list[str],
    test_summary: str,
    base_branch: str,
    generated_at: str,
) -> str:
    """Render the PR body as Markdown."""
    lines: list[str] = ["## Summary", ""]

    if completed_tasks:
        lines += ["### Completed Tasks", ""]
        for task in completed_tasks:
            lines.append(f"- {task}")
        lines.append("")

    lines += ["## Changed Files", ""]
    if changed_files:
        for f in changed_files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- (no file changes vs base branch)")
    lines.append("")

    lines += ["## Commits", ""]
    if commits:
        for c in commits:
            lines.append(f"- {c}")
    else:
        lines.append("- (no new commits vs base branch)")
    lines.append("")

    lines += [
        "## Tests",
        "",
        "```",
        test_summary,
        "```",
        "",
        "---",
        f"*Generated by ai_agent/pr_builder.py at {generated_at}"
        f" against `{base_branch}`*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_pr_draft(
    base_branch: str = "main",
    run_tests: bool = False,
    repo_root: Path = REPO_ROOT,
    drafts_dir: Optional[Path] = None,
    done_dir: Optional[Path] = None,
) -> PRDraft:
    """
    Generate a PR draft from the current git state and save it to disk.

    Args:
        base_branch: Branch to diff against (default: ``"main"``).
        run_tests:   Run pytest to collect a live test summary.
        repo_root:   Repository root path.
        drafts_dir:  Directory for saved drafts (default: ``ai_agent/pr_drafts/``).
        done_dir:    Directory of completed task files (default: ``ai_agent/done/``).

    Returns:
        ``PRDraft`` with all collected data and ``draft_path`` set to the
        saved file.
    """
    if drafts_dir is None:
        drafts_dir = PR_DRAFTS_DIR
    if done_dir is None:
        done_dir = _AGENT_DIR / "done"

    ts = datetime.now(timezone.utc)
    generated_at = ts.strftime("%Y-%m-%d %H:%M UTC")

    changed_files = _get_changed_files(base_branch, repo_root)
    commits = _get_commits(base_branch, repo_root)
    completed_tasks = _get_completed_tasks(done_dir)

    if run_tests:
        test_summary = _run_tests(repo_root)
    else:
        test_summary = "(tests not run — pass run_tests=True or --run-tests flag)"

    title = _generate_title(commits, completed_tasks)
    description = _generate_description(
        title=title,
        completed_tasks=completed_tasks,
        changed_files=changed_files,
        commits=commits,
        test_summary=test_summary,
        base_branch=base_branch,
        generated_at=generated_at,
    )

    draft = PRDraft(
        title=title,
        description=description,
        completed_tasks=completed_tasks,
        changed_files=changed_files,
        commits=commits,
        test_summary=test_summary,
        base_branch=base_branch,
        generated_at=generated_at,
    )

    drafts_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{ts.strftime('%Y%m%d_%H%M%S')}_{_slug(title)}.md"
    draft_path = drafts_dir / filename
    draft_path.write_text(f"# PR Draft: {title}\n\n{description}\n", encoding="utf-8")
    draft.draft_path = draft_path

    return draft


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ai_agent.pr_builder",
        description="Generate a GitHub PR draft from the current git state",
    )
    parser.add_argument(
        "--base", default="main", metavar="BRANCH",
        help="Base branch to diff against (default: main)",
    )
    parser.add_argument(
        "--run-tests", action="store_true",
        help="Run pytest to collect a live test summary",
    )
    args = parser.parse_args(argv)

    draft = build_pr_draft(base_branch=args.base, run_tests=args.run_tests)
    print(f"[PR_BUILDER] Title: {draft.title}")
    print(f"[PR_BUILDER] Draft: {draft.draft_path}")
    print(f"[PR_BUILDER] Changed files: {len(draft.changed_files)}")
    print(f"[PR_BUILDER] Commits:       {len(draft.commits)}")
    print(f"[PR_BUILDER] Done tasks:    {len(draft.completed_tasks)}")
    print(f"[PR_BUILDER] Tests:         {draft.test_summary}")


if __name__ == "__main__":
    _main()
