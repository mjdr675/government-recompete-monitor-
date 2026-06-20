"""
Engineering Metrics — collects and reports on agent task execution.

Sources:
  - ai_agent/done/      → completed task count
  - ai_agent/failed/    → failed task count
  - ai_agent/logs/      → elapsed time, retries, commit SHAs, roles
  - git log             → commit history
  - pytest --collect-only → test count

Output: ai_agent/metrics.md

Usage:
  from ai_agent.metrics import collect_metrics, generate_metrics_report
  metrics = collect_metrics()
  path = generate_metrics_report(metrics)

CLI:
  python -m ai_agent.metrics
  python -m ai_agent.metrics --run-tests
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
_AGENT_DIR = Path(__file__).parent
METRICS_PATH = _AGENT_DIR / "metrics.md"

_RE_ELAPSED = re.compile(r"elapsed=(\d+\.?\d*)s")
_RE_RETRY = re.compile(r"\bRETRY\b")
_RE_DONE = re.compile(r"\bDONE\b.*commit=([a-f0-9]+)")
_RE_ROLE = re.compile(r"\bROLE\s+(\w+)")
_RE_TESTS_COLLECTED = re.compile(r"(\d+)\s+(?:test[s]?\s+)?collected")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TaskMetrics:
    filename: str
    status: str                      # "completed" | "failed"
    elapsed_seconds: Optional[float] = None
    retries: int = 0
    commit_sha: Optional[str] = None
    role: Optional[str] = None


@dataclass
class EngMetrics:
    tasks_completed: int
    tasks_failed: int
    success_rate: float              # 0.0–1.0
    total_retries: int
    avg_time_seconds: Optional[float]
    test_count: int
    commit_history: list[str]
    task_details: list[TaskMetrics]
    generated_at: str


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def _parse_log(log_path: Path) -> TaskMetrics:
    """Parse a single task log file into a TaskMetrics record."""
    stem = log_path.stem
    status = "completed"
    elapsed: Optional[float] = None
    retries = 0
    commit_sha: Optional[str] = None
    role: Optional[str] = None

    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return TaskMetrics(filename=stem, status="unknown")

    for line in text.splitlines():
        m = _RE_ELAPSED.search(line)
        if m:
            elapsed = float(m.group(1))

        if _RE_RETRY.search(line):
            retries += 1

        m = _RE_DONE.search(line)
        if m:
            commit_sha = m.group(1)
            status = "completed"

        if "FAILED" in line or "FAIL  " in line:
            status = "failed"

        m = _RE_ROLE.search(line)
        if m:
            role = m.group(1)

    return TaskMetrics(
        filename=stem,
        status=status,
        elapsed_seconds=elapsed,
        retries=retries,
        commit_sha=commit_sha,
        role=role,
    )


def _parse_logs(logs_dir: Path) -> list[TaskMetrics]:
    """Parse all task log files in logs_dir. Skips daemon/system logs."""
    if not logs_dir.exists():
        return []
    results = []
    for log_path in sorted(logs_dir.glob("*.log")):
        stem = log_path.stem
        # Skip system/daemon logs that aren't per-task
        if stem in ("daemon", "claude-pro-waiter"):
            continue
        # Skip failure-report files (they're .md, but just in case)
        if "failure-report" in stem:
            continue
        results.append(_parse_log(log_path))
    return results


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _get_commit_history(repo_root: Path, limit: int = 20) -> list[str]:
    """Return the most recent commit one-liners."""
    result = subprocess.run(
        ["git", "log", "--oneline", f"-{limit}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Test count
# ---------------------------------------------------------------------------

def _count_tests(repo_root: Path) -> int:
    """Return the number of collected pytest tests."""
    pytest_bin = shutil.which("pytest") or sys.executable
    cmd = (
        [pytest_bin, "--collect-only", "-q", "--tb=no"]
        if shutil.which("pytest")
        else [pytest_bin, "-m", "pytest", "--collect-only", "-q", "--tb=no"]
    )
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    for line in reversed(output.splitlines()):
        m = _RE_TESTS_COLLECTED.search(line)
        if m:
            return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_metrics(
    agent_dir: Path = _AGENT_DIR,
    repo_root: Path = REPO_ROOT,
    run_tests: bool = True,
) -> EngMetrics:
    """
    Collect engineering metrics from the repository state.

    Args:
        agent_dir:  Path to ai_agent/ directory.
        repo_root:  Repository root.
        run_tests:  Count tests via pytest --collect-only.

    Returns:
        :class:`EngMetrics` with all collected data.
    """
    done_dir = agent_dir / "done"
    failed_dir = agent_dir / "failed"
    logs_dir = agent_dir / "logs"

    tasks_completed = len(list(done_dir.glob("*.md"))) if done_dir.exists() else 0
    tasks_failed = len(list(failed_dir.glob("*.md"))) if failed_dir.exists() else 0
    total = tasks_completed + tasks_failed
    success_rate = tasks_completed / total if total > 0 else 0.0

    task_details = _parse_logs(logs_dir)
    total_retries = sum(t.retries for t in task_details)

    timed = [t.elapsed_seconds for t in task_details if t.elapsed_seconds is not None]
    avg_time = sum(timed) / len(timed) if timed else None

    test_count = _count_tests(repo_root) if run_tests else 0
    commit_history = _get_commit_history(repo_root)

    return EngMetrics(
        tasks_completed=tasks_completed,
        tasks_failed=tasks_failed,
        success_rate=success_rate,
        total_retries=total_retries,
        avg_time_seconds=avg_time,
        test_count=test_count,
        commit_history=commit_history,
        task_details=task_details,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def generate_metrics_report(
    metrics: EngMetrics,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Render *metrics* as Markdown and write to *output_path*.

    Returns the path of the written file.
    """
    if output_path is None:
        output_path = METRICS_PATH

    avg_str = (
        f"{metrics.avg_time_seconds:.1f}s"
        if metrics.avg_time_seconds is not None
        else "n/a"
    )
    rate_pct = f"{metrics.success_rate * 100:.1f}%"

    lines: list[str] = [
        "# Engineering Metrics",
        "",
        f"*Generated: {metrics.generated_at}*",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tasks completed | {metrics.tasks_completed} |",
        f"| Tasks failed | {metrics.tasks_failed} |",
        f"| Success rate | {rate_pct} |",
        f"| Total retries | {metrics.total_retries} |",
        f"| Avg time per task | {avg_str} |",
        f"| Tests in suite | {metrics.test_count} |",
        "",
    ]

    if metrics.task_details:
        lines += ["## Task Details", ""]
        lines += ["| Task | Status | Role | Elapsed | Retries | Commit |"]
        lines += ["|------|--------|------|---------|---------|--------|"]
        for t in metrics.task_details:
            elapsed = f"{t.elapsed_seconds:.1f}s" if t.elapsed_seconds is not None else "—"
            commit = t.commit_sha[:7] if t.commit_sha else "—"
            role = t.role or "—"
            lines.append(
                f"| {t.filename} | {t.status} | {role} | {elapsed} | {t.retries} | {commit} |"
            )
        lines.append("")

    if metrics.commit_history:
        lines += ["## Recent Commits", ""]
        for c in metrics.commit_history:
            lines.append(f"- {c}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ai_agent.metrics",
        description="Collect and report engineering metrics",
    )
    parser.add_argument(
        "--run-tests", action="store_true",
        help="Count tests via pytest --collect-only (adds a few seconds)",
    )
    parser.add_argument(
        "--output", default=None, metavar="PATH",
        help=f"Output path (default: {METRICS_PATH})",
    )
    args = parser.parse_args(argv)

    output_path = Path(args.output) if args.output else None
    metrics = collect_metrics(run_tests=args.run_tests)
    path = generate_metrics_report(metrics, output_path=output_path)

    print(f"[METRICS] Tasks completed:  {metrics.tasks_completed}")
    print(f"[METRICS] Tasks failed:     {metrics.tasks_failed}")
    print(f"[METRICS] Success rate:     {metrics.success_rate * 100:.1f}%")
    print(f"[METRICS] Total retries:    {metrics.total_retries}")
    avg = f"{metrics.avg_time_seconds:.1f}s" if metrics.avg_time_seconds is not None else "n/a"
    print(f"[METRICS] Avg time/task:    {avg}")
    print(f"[METRICS] Tests in suite:   {metrics.test_count}")
    print(f"[METRICS] Report written:   {path}")


if __name__ == "__main__":
    _main()
