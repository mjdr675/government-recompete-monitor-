"""
AI CTO — strategic planning module for the autonomous engineering system.

Analyzes repository state, reviews engineering memory and technical debt, and
produces an advisory recommendation for the next highest-ROI task.

IMPORTANT: This module is advisory only. It never implements tasks, writes
application code, or takes autonomous action. All outputs are reports and
recommendations for human or agent review.

Usage:
  from ai_agent.cto import generate_cto_report, write_report, update_roadmap

  report = generate_cto_report()
  write_report(report)               # writes ai_agent/CTO_REPORT.md
  update_roadmap(report)             # appends strategic notes to company/ROADMAP.md
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
_AGENT_DIR = Path(__file__).parent

DEFAULT_REPORT_PATH = _AGENT_DIR / "CTO_REPORT.md"
DEFAULT_ROADMAP_PATH = REPO_ROOT / "company" / "ROADMAP.md"

# ---------------------------------------------------------------------------
# Complexity scoring
# ---------------------------------------------------------------------------

_COMPLEXITY_SCORE: dict[str, int] = {
    "XS": 5,
    "S": 4,
    "M": 3,
    "L": 2,
    "XL": 1,
}
_DEFAULT_COMPLEXITY_SCORE = 3

# Bonus added per task directly unblocked by completing this task.
_BLOCKING_BONUS = 3

# Penalty applied when any hard dependency is unmet.
_UNMET_DEP_PENALTY = 100


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class QueueEntry:
    filename: str          # e.g. "056-min-value-filter.md"
    number: int            # e.g. 56
    title: str
    complexity: str        # XS / S / M / L / XL / unknown
    dependencies: list[int]  # task numbers this task depends on
    raw_content: str


@dataclass
class TechDebtItem:
    description: str
    location: str      # file or area
    severity: str      # low / medium / high
    blocking_tasks: list[str] = field(default_factory=list)


@dataclass
class RepositorySnapshot:
    queued_tasks: list[QueueEntry]
    completed_task_numbers: set[int]
    failed_task_numbers: set[int]
    git_log: list[str]
    test_count: int
    tech_debt: list[TechDebtItem]
    generated_at: str


@dataclass
class CTORecommendation:
    task_filename: str
    task_title: str
    rationale: str
    estimated_complexity: str
    score: float
    tasks_unblocked: list[int]


@dataclass
class CTOReport:
    snapshot: RepositorySnapshot
    recommendation: Optional[CTORecommendation]
    roadmap_notes: list[str]
    generated_at: str


# ---------------------------------------------------------------------------
# Queue parsing
# ---------------------------------------------------------------------------

_RE_TASK_NUMBER = re.compile(r"^(\d+)-")
_RE_COMPLEXITY = re.compile(r"\*\*Complexity:\*\*\s*([A-Z]+)")
_RE_TITLE_H1 = re.compile(r"^#\s+Task\s+\d+\s+[—–-]+\s+(.+)$", re.MULTILINE)
_RE_DEP_TASK = re.compile(r"Task\s+(\d{3,})\b")
_RE_DEPS_SECTION = re.compile(
    r"##\s+Hard\s+Dependencies\s*\n(.*?)(?=\n##|\Z)", re.DOTALL | re.IGNORECASE
)


def parse_task_file(path: Path) -> QueueEntry:
    """Parse a single task Markdown file into a QueueEntry."""
    filename = path.name
    content = path.read_text(encoding="utf-8", errors="replace")

    m = _RE_TASK_NUMBER.match(filename)
    number = int(m.group(1)) if m else 0

    m = _RE_TITLE_H1.search(content)
    title = m.group(1).strip() if m else filename.removesuffix(".md")

    m = _RE_COMPLEXITY.search(content)
    complexity = m.group(1).upper() if m else "unknown"

    deps: list[int] = []
    m = _RE_DEPS_SECTION.search(content)
    if m:
        dep_text = m.group(1)
        # Only parse if not "None" or "none"
        if not re.search(r"\bNone\b", dep_text, re.IGNORECASE):
            deps = [int(n) for n in _RE_DEP_TASK.findall(dep_text)]

    return QueueEntry(
        filename=filename,
        number=number,
        title=title,
        complexity=complexity,
        dependencies=deps,
        raw_content=content,
    )


def scan_queue(queue_dir: Path) -> list[QueueEntry]:
    """Return all queue entries sorted by task number."""
    if not queue_dir.exists():
        return []
    entries = []
    for md in sorted(queue_dir.glob("*.md")):
        try:
            entries.append(parse_task_file(md))
        except Exception:
            pass
    return sorted(entries, key=lambda e: e.number)


def _task_numbers_in_dir(directory: Path) -> set[int]:
    """Return the set of task numbers found in a directory of *.md files."""
    if not directory.exists():
        return set()
    nums: set[int] = set()
    for md in directory.glob("*.md"):
        m = _RE_TASK_NUMBER.match(md.name)
        if m:
            nums.add(int(m.group(1)))
    return nums


# ---------------------------------------------------------------------------
# Technical debt scanning
# ---------------------------------------------------------------------------

_DEBT_PATTERNS: list[tuple[str, str, str, list[str]]] = [
    # (grep_pattern, description, severity, blocking_tasks)
    (
        r"subprocess\.Popen",
        "subprocess.Popen used for ingest — should be a Celery background task",
        "medium",
        ["065-celery-ingest.md"],
    ),
    (
        r"sqlite3\.connect",
        "sqlite3.connect() called directly — should go through get_connection() abstraction",
        "medium",
        ["061-postgresql-provision.md"],
    ),
    (
        r"\bTODO\b",
        "TODO comment in source code",
        "low",
        [],
    ),
    (
        r"\bFIXME\b",
        "FIXME comment in source code",
        "medium",
        [],
    ),
    (
        r"\bHACK\b",
        "HACK comment in source code",
        "low",
        [],
    ),
]


def scan_tech_debt(repo_root: Path) -> list[TechDebtItem]:
    """
    Grep Python source files for known debt patterns.

    Returns one TechDebtItem per pattern that has at least one match.
    Does not modify any files.
    """
    py_files = list(repo_root.glob("*.py")) + list((repo_root / "ai_agent").glob("*.py"))
    items: list[TechDebtItem] = []

    for pattern, description, severity, blocking in _DEBT_PATTERNS:
        hits: list[str] = []
        for py_file in py_files:
            try:
                text = py_file.read_text(encoding="utf-8", errors="replace")
                for lineno, line in enumerate(text.splitlines(), 1):
                    if re.search(pattern, line):
                        hits.append(f"{py_file.name}:{lineno}")
            except OSError:
                pass

        if hits:
            location = ", ".join(hits[:5])  # cap display at 5 locations
            if len(hits) > 5:
                location += f" (+{len(hits) - 5} more)"
            items.append(TechDebtItem(
                description=description,
                location=location,
                severity=severity,
                blocking_tasks=blocking,
            ))

    return items


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _get_git_log(repo_root: Path, limit: int = 10) -> list[str]:
    result = subprocess.run(
        ["git", "log", "--oneline", f"-{limit}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def _count_tests(repo_root: Path) -> int:
    """Return the number of collected pytest tests (0 on failure)."""
    pytest_bin = shutil.which("pytest")
    if not pytest_bin:
        return 0
    result = subprocess.run(
        [pytest_bin, "--collect-only", "-q", "--tb=no"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    for line in reversed(output.splitlines()):
        m = re.search(r"(\d+)\s+(?:test[s]?\s+)?collected", line)
        if m:
            return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Scoring and recommendation
# ---------------------------------------------------------------------------

def _build_dependency_index(entries: list[QueueEntry]) -> dict[int, list[int]]:
    """
    Return a map: task_number → list of task numbers that depend on it.

    This lets us count how many tasks each task unblocks.
    """
    index: dict[int, list[int]] = {}
    for entry in entries:
        for dep in entry.dependencies:
            index.setdefault(dep, []).append(entry.number)
    return index


def score_task(
    entry: QueueEntry,
    completed: set[int],
    dep_index: dict[int, list[int]],
) -> float:
    """
    Compute a priority score for a queued task. Higher is better.

    Factors:
    - Complexity: XS=5, S=4, M=3, L=2, XL=1 (smaller → faster → higher score)
    - Blocking bonus: +3 per task this task directly unblocks
    - Unmet dependency penalty: -100 per unmet hard dependency
    """
    base = _COMPLEXITY_SCORE.get(entry.complexity, _DEFAULT_COMPLEXITY_SCORE)

    # Bonus for unblocking other tasks
    tasks_unblocked = dep_index.get(entry.number, [])
    bonus = len(tasks_unblocked) * _BLOCKING_BONUS

    # Penalty for unmet dependencies
    penalty = sum(
        _UNMET_DEP_PENALTY for dep in entry.dependencies if dep not in completed
    )

    return float(base + bonus - penalty)


def recommend_next_task(
    entries: list[QueueEntry],
    completed: set[int],
) -> Optional[CTORecommendation]:
    """
    Return the highest-scoring queued task, or None if queue is empty.
    """
    if not entries:
        return None

    dep_index = _build_dependency_index(entries)

    best: Optional[QueueEntry] = None
    best_score = float("-inf")

    for entry in entries:
        s = score_task(entry, completed, dep_index)
        if s > best_score:
            best_score = s
            best = entry

    if best is None:
        return None

    tasks_unblocked = dep_index.get(best.number, [])
    unmet_deps = [d for d in best.dependencies if d not in completed]

    if unmet_deps:
        rationale = (
            f"Score {best_score:.0f}. "
            f"NOTE: has unmet dependencies on tasks {unmet_deps}. "
            f"All other tasks also have unmet dependencies or are lower priority."
        )
    elif tasks_unblocked:
        rationale = (
            f"Score {best_score:.0f}. "
            f"Completing this task directly unblocks {len(tasks_unblocked)} future "
            f"task(s): {tasks_unblocked}. "
            f"Highest ROI single action in the current queue."
        )
    else:
        rationale = (
            f"Score {best_score:.0f}. "
            f"Complexity {best.complexity} with no hard dependencies — "
            f"fastest path to a completed task."
        )

    return CTORecommendation(
        task_filename=best.filename,
        task_title=best.title,
        rationale=rationale,
        estimated_complexity=best.complexity,
        score=best_score,
        tasks_unblocked=tasks_unblocked,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_repo_state(
    repo_root: Path = REPO_ROOT,
    agent_dir: Path = _AGENT_DIR,
    count_tests: bool = True,
) -> RepositorySnapshot:
    """
    Collect current repository state: queue, done, failed, git log, tests, debt.

    Args:
        repo_root:    Repository root directory.
        agent_dir:    ai_agent/ directory.
        count_tests:  Run pytest --collect-only to count tests (adds ~5s).

    Returns:
        :class:`RepositorySnapshot` with all collected data.
    """
    queue_dir = agent_dir / "queue"
    done_dir = agent_dir / "done"
    failed_dir = agent_dir / "failed"

    queued = scan_queue(queue_dir)
    completed = _task_numbers_in_dir(done_dir)
    failed = _task_numbers_in_dir(failed_dir)
    git_log = _get_git_log(repo_root)
    test_count = _count_tests(repo_root) if count_tests else 0
    debt = scan_tech_debt(repo_root)

    return RepositorySnapshot(
        queued_tasks=queued,
        completed_task_numbers=completed,
        failed_task_numbers=failed,
        git_log=git_log,
        test_count=test_count,
        tech_debt=debt,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def generate_cto_report(
    repo_root: Path = REPO_ROOT,
    agent_dir: Path = _AGENT_DIR,
    count_tests: bool = True,
) -> CTOReport:
    """
    Generate a full CTO strategic planning report.

    Returns:
        :class:`CTOReport` with snapshot, recommendation, and roadmap notes.
    """
    snapshot = collect_repo_state(repo_root, agent_dir, count_tests=count_tests)
    rec = recommend_next_task(snapshot.queued_tasks, snapshot.completed_task_numbers)

    roadmap_notes: list[str] = []
    if snapshot.tech_debt:
        high = [d for d in snapshot.tech_debt if d.severity == "high"]
        medium = [d for d in snapshot.tech_debt if d.severity == "medium"]
        if high:
            roadmap_notes.append(f"HIGH severity debt: {len(high)} item(s) require attention.")
        if medium:
            roadmap_notes.append(f"MEDIUM severity debt: {len(medium)} item(s) — schedule soon.")

    dep_index = _build_dependency_index(snapshot.queued_tasks)
    high_blockers = [
        e for e in snapshot.queued_tasks
        if len(dep_index.get(e.number, [])) >= 2
        and all(d in snapshot.completed_task_numbers for d in e.dependencies)
    ]
    if high_blockers:
        names = [e.filename for e in high_blockers[:3]]
        roadmap_notes.append(
            f"High-value blockers with no unmet deps: {names}. "
            "Prioritize to unchain the dependency graph."
        )

    return CTOReport(
        snapshot=snapshot,
        recommendation=rec,
        roadmap_notes=roadmap_notes,
        generated_at=snapshot.generated_at,
    )


def write_report(
    report: CTOReport,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Write a Markdown CTO report to *output_path*.

    Returns the path of the written file.
    """
    if output_path is None:
        output_path = DEFAULT_REPORT_PATH

    snap = report.snapshot
    dep_index = _build_dependency_index(snap.queued_tasks)

    lines: list[str] = [
        "# CTO Strategic Report",
        "",
        f"*Generated: {report.generated_at}*",
        "",
        "---",
        "",
        "## Repository State",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tasks in queue | {len(snap.queued_tasks)} |",
        f"| Tasks completed | {len(snap.completed_task_numbers)} |",
        f"| Tasks failed | {len(snap.failed_task_numbers)} |",
        f"| Test count | {snap.test_count if snap.test_count else 'n/a'} |",
        "",
    ]

    if snap.git_log:
        lines += ["## Recent Commits", ""]
        for entry in snap.git_log[:5]:
            lines.append(f"- {entry}")
        lines.append("")

    # --- Recommendation ---
    if report.recommendation:
        rec = report.recommendation
        lines += [
            "## Recommended Next Task",
            "",
            f"**`{rec.task_filename}`** — {rec.task_title}",
            "",
            f"- **Complexity:** {rec.estimated_complexity}",
            f"- **Priority score:** {rec.score:.1f}",
            f"- **Rationale:** {rec.rationale}",
        ]
        if rec.tasks_unblocked:
            lines.append(f"- **Directly unblocks:** tasks {rec.tasks_unblocked}")
        lines.append("")
    else:
        lines += ["## Recommended Next Task", "", "Queue is empty.", ""]

    # --- Full queue ---
    if snap.queued_tasks:
        lines += ["## Task Queue", ""]
        lines += ["| # | File | Title | Complexity | Deps | Score |"]
        lines += ["|---|------|-------|------------|------|-------|"]
        for entry in snap.queued_tasks:
            s = score_task(entry, snap.completed_task_numbers, dep_index)
            deps_str = str(entry.dependencies) if entry.dependencies else "—"
            lines.append(
                f"| {entry.number} | {entry.filename} | {entry.title[:40]} "
                f"| {entry.complexity} | {deps_str} | {s:.0f} |"
            )
        lines.append("")

    # --- Technical debt ---
    if snap.tech_debt:
        lines += ["## Technical Debt", ""]
        for item in snap.tech_debt:
            lines.append(f"### [{item.severity.upper()}] {item.description}")
            lines.append(f"- **Location:** `{item.location}`")
            if item.blocking_tasks:
                lines.append(f"- **Blocking:** {item.blocking_tasks}")
            lines.append("")

    # --- Roadmap notes ---
    if report.roadmap_notes:
        lines += ["## Strategic Notes", ""]
        for note in report.roadmap_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines += [
        "---",
        "",
        "*This report is advisory only. No code was written or changed by the CTO module.*",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def update_roadmap(
    report: CTOReport,
    roadmap_path: Optional[Path] = None,
) -> Path:
    """
    Append a CTO review section to ROADMAP.md with the current recommendation
    and strategic notes.

    Returns the path of the updated file.
    """
    if roadmap_path is None:
        roadmap_path = DEFAULT_ROADMAP_PATH

    existing = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else ""

    rec = report.recommendation
    rec_line = (
        f"  - **Recommended next:** `{rec.task_filename}` — {rec.task_title} "
        f"(complexity {rec.estimated_complexity}, score {rec.score:.0f})"
        if rec else "  - **Recommended next:** queue empty"
    )

    notes_block = ""
    if report.roadmap_notes:
        notes_block = "\n".join(f"  - {n}" for n in report.roadmap_notes)
        notes_block = "\n\n  **Strategic notes:**\n" + notes_block

    section = (
        f"\n\n## CTO Review — {report.generated_at}\n\n"
        f"  - Tasks in queue: {len(report.snapshot.queued_tasks)}\n"
        f"  - Tasks completed: {len(report.snapshot.completed_task_numbers)}\n"
        f"{rec_line}"
        f"{notes_block}\n"
    )

    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_path.write_text(existing + section, encoding="utf-8")
    return roadmap_path
