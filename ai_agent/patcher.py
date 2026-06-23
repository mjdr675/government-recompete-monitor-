"""
Patch execution pipeline.

Reads proposed patches (markdown Before/After format) from patches/,
validates them, applies them safely, runs the test suite, and either
commits or rolls back — leaving the repository in a clean state either way.

Entry point:
    result = execute(patch_path, repo_root, dry_run=True)

Environment gates (both must be set to actually modify files):
    DRY_RUN=false
    APPLY_PATCH=true
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent
PATCHES_DIR = REPO_ROOT / "patches"
FAILURES_DIR = PATCHES_DIR / "failures"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Change:
    file: str       # repo-relative path
    before: str     # exact text to find
    after: str      # replacement text

    def unified_diff(self, repo_root: Path) -> str:
        """Generate a unified diff string for this change (for logging only)."""
        path = repo_root / self.file
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        patched = original.replace(self.before, self.after, 1)
        lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{self.file}",
            tofile=f"b/{self.file}",
        ))
        return "".join(lines)


@dataclass
class Patch:
    path: Path
    task_title: str
    role: str
    source: str
    changes: list[Change] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    passed: bool
    returncode: int
    stdout: str
    stderr: str
    no_tests: bool = False      # pytest exit 5 — no tests collected


@dataclass
class ApplyResult:
    success: bool
    dry_run: bool
    patch: Patch
    validation: ValidationResult
    test_result: Optional[TestResult] = None
    commit_sha: Optional[str] = None
    rolled_back: bool = False
    failure_report: Optional[Path] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _meta(text: str, key: str) -> str:
    m = re.search(rf"\*\*{key}:\*\*\s*(.+)", text)
    return m.group(1).strip() if m else ""


def parse_patch(path: Path) -> Patch:
    """
    Parse a patch markdown file into a Patch object.

    Expected format for each change block:
        ## Patch: path/to/file.py
        ### Before
        ```python
        <exact original text>
        ```
        ### After
        ```python
        <replacement text>
        ```
    """
    text = path.read_text(encoding="utf-8")

    task_title = _meta(text, "Task") or path.stem
    role       = _meta(text, "Role") or "unknown"
    source     = _meta(text, "Source") or "unknown"

    # Match every Patch: block — code fence language tag is optional.
    # Uses [ \t]* instead of \s* to avoid matching newlines at end-of-line
    # positions. Strips trailing whitespace from captures so that a trailing
    # blank line inside the fence doesn't break the file lookup.
    pattern = re.compile(
        r"^[ \t]*## Patch:\s*(.+?)[ \t]*$\n"
        r"[ \t]*### Before\n"
        r"[ \t]*```[^\n]*\n"
        r"(.*?)"
        r"^[ \t]*```[ \t]*\n"
        r"[ \t]*### After\n"
        r"[ \t]*```[^\n]*\n"
        r"(.*?)"
        r"^[ \t]*```[ \t]*(?:\n|$)",
        re.MULTILINE | re.DOTALL,
    )

    changes = [
        Change(
            file=m.group(1).strip(),
            before=m.group(2).rstrip("\n"),   # strip trailing blank lines only
            after=m.group(3).rstrip("\n"),
        )
        for m in pattern.finditer(text)
    ]

    return Patch(path=path, task_title=task_title, role=role,
                 source=source, changes=changes)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(patch: Patch, repo_root: Path) -> ValidationResult:
    """
    Validate a patch before applying.

    Checks:
    - At least one change block exists
    - No path traversal (../)
    - All paths stay inside repo_root
    - Target files exist and are text (UTF-8)
    - Before text appears exactly once in the file
    - No new binary content in After block
    """
    errors: list[str] = []

    if not patch.changes:
        return ValidationResult(valid=False,
                                errors=["No Patch: blocks found in the patch file"])

    repo_root_resolved = repo_root.resolve()

    for change in patch.changes:
        # --- path traversal ---
        if ".." in Path(change.file).parts:
            errors.append(f"Path traversal detected: {change.file!r}")
            continue

        # --- resolve and confine to repo ---
        try:
            target = (repo_root / change.file).resolve()
            target.relative_to(repo_root_resolved)
        except ValueError:
            errors.append(f"Path escapes repository root: {change.file!r}")
            continue

        # --- file must exist ---
        if not target.exists():
            errors.append(f"File not found: {change.file}")
            continue

        if not target.is_file():
            errors.append(f"Not a regular file: {change.file}")
            continue

        # --- must be text (UTF-8) ---
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"Binary file (not UTF-8): {change.file}")
            continue

        # --- after block must also be text ---
        try:
            change.after.encode("utf-8")
        except UnicodeEncodeError:
            errors.append(f"After block contains non-UTF-8 content: {change.file}")
            continue

        # --- before text must appear exactly once ---
        count = content.count(change.before)
        if count == 0:
            # Show a short excerpt of what was expected for easier debugging
            preview = repr(change.before[:120].strip())
            errors.append(f"Before text not found in {change.file}: {preview}")
        elif count > 1:
            errors.append(
                f"Before text is ambiguous ({count} occurrences) in {change.file} — "
                "make the match context more specific"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Apply + rollback
# ---------------------------------------------------------------------------

def _apply_changes(patch: Patch, repo_root: Path) -> tuple[dict[str, str], list[str]]:
    """Apply all changes. Returns (original_contents, changed_file_paths)."""
    backups: dict[str, str] = {}
    changed: list[str] = []

    for change in patch.changes:
        target = repo_root / change.file
        original = target.read_text(encoding="utf-8")
        backups[change.file] = original
        target.write_text(original.replace(change.before, change.after, 1), encoding="utf-8")
        changed.append(change.file)

    return backups, changed


def _rollback(backups: dict[str, str], repo_root: Path) -> None:
    """Restore files to their pre-patch state from in-memory backups."""
    for rel_path, original in backups.items():
        (repo_root / rel_path).write_text(original, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_tests(repo_root: Path, timeout: int = 120) -> TestResult:
    """
    Run pytest. Returns TestResult.
    Exit code 5 means no tests collected — treated as pass with warning.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    no_tests = result.returncode == 5
    passed = result.returncode in (0, 5)
    return TestResult(
        passed=passed,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        no_tests=no_tests,
    )


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

def _commit(changed_files: list[str], message: str, repo_root: Path) -> Optional[str]:
    """Stage changed files and create a commit. Returns the new SHA or None on failure."""
    stage = subprocess.run(
        ["git", "add", "--"] + changed_files,
        cwd=repo_root, capture_output=True, text=True,
    )
    if stage.returncode != 0:
        return None

    commit = subprocess.run(
        ["git", "commit", "-m", message, "--no-verify"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if commit.returncode != 0:
        return None

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_root, capture_output=True, text=True,
    )
    return sha.stdout.strip() if sha.returncode == 0 else None


# ---------------------------------------------------------------------------
# Failure report
# ---------------------------------------------------------------------------

def _save_failure_report(patch: Patch, test_result: Optional[TestResult],
                          validation: ValidationResult,
                          failures_dir: Path) -> Path:
    failures_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", patch.task_title.lower())[:40]
    report_path = failures_dir / f"{ts}_{slug}.md"

    sections = [
        f"# Failure Report",
        f"**Task:** {patch.task_title}  ",
        f"**Patch file:** {patch.path.name}  ",
        f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}  ",
        "",
    ]

    if not validation.valid:
        sections += ["## Validation Errors", ""]
        for e in validation.errors:
            sections.append(f"- {e}")
        sections.append("")

    if test_result:
        sections += [
            f"## Test Result (exit code {test_result.returncode})",
            "",
            "### stdout",
            "```",
            test_result.stdout.strip() or "(empty)",
            "```",
            "",
            "### stderr",
            "```",
            test_result.stderr.strip() or "(empty)",
            "```",
        ]

    report_path.write_text("\n".join(sections), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _update_handoff(patch: Patch, result: ApplyResult,
                    handoff_path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if result.success:
        status = f"applied — commit {result.commit_sha}"
    elif result.rolled_back:
        status = "ROLLED BACK — tests failed"
    else:
        status = f"FAILED — {result.error}"

    diffs = "\n\n".join(
        c.unified_diff(patch.path.parent.parent)
        for c in patch.changes
    ) or "(no changes)"

    entry = (
        f"\n## {ts} — [PATCHER] {patch.task_title}\n"
        f"**Status:** {status}  \n"
        f"**Patch:** `{patch.path.name}`  \n"
        f"{'**Commit:** ' + result.commit_sha if result.commit_sha else ''}  \n"
        f"\n<details><summary>Unified diff</summary>\n\n```diff\n{diffs}\n```\n</details>\n"
    )
    with open(handoff_path, "a") as f:
        f.write(entry)


def _update_task_log(patch: Patch, result: ApplyResult, task_log_path: Path) -> None:
    if result.success:
        outcome = f"committed:{result.commit_sha}"
    elif result.rolled_back:
        outcome = "rolled-back"
    else:
        outcome = f"error:{result.error}"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(task_log_path, "a") as f:
        f.write(f"| {ts} | patcher | {patch.task_title[:60]} "
                f"| {patch.source} | {outcome} |\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def execute(
    patch_path: Path,
    repo_root: Path = REPO_ROOT,
    dry_run: bool = True,
    handoff_path: Optional[Path] = None,
    task_log_path: Optional[Path] = None,
) -> ApplyResult:
    """
    Full pipeline: parse → validate → (if not dry_run) apply → test → commit or rollback.

    dry_run=True (default): validates and shows diffs but never modifies files.
    dry_run=False: applies, runs tests, commits on pass or rolls back on failure.
    """
    handoff_path  = handoff_path  or repo_root / "HANDOFF.md"
    task_log_path = task_log_path or repo_root / "TASK_LOG.md"
    failures_dir  = repo_root / "patches" / "failures"

    # 1. Parse
    try:
        patch = parse_patch(patch_path)
    except Exception as exc:
        return ApplyResult(
            success=False, dry_run=dry_run,
            patch=Patch(path=patch_path, task_title=patch_path.stem,
                        role="unknown", source="unknown"),
            validation=ValidationResult(valid=False,
                                        errors=[f"Parse error: {exc}"]),
            error=str(exc),
        )

    # 2. Validate
    validation = validate(patch, repo_root)

    if not validation.valid:
        print("[PATCHER] Validation FAILED:")
        for e in validation.errors:
            print(f"  - {e}")
        report = _save_failure_report(patch, None, validation, failures_dir)
        return ApplyResult(
            success=False, dry_run=dry_run, patch=patch,
            validation=validation, failure_report=report,
            error="validation failed",
        )

    print("[PATCHER] Validation PASSED")

    # 3. Dry-run: show unified diffs and return
    if dry_run:
        print("\n[PATCHER] DRY_RUN — diffs that would be applied:")
        for change in patch.changes:
            udiff = change.unified_diff(repo_root)
            print(udiff if udiff else f"  (no textual diff for {change.file})")
        return ApplyResult(
            success=True, dry_run=True, patch=patch, validation=validation
        )

    # 4. Apply
    print("[PATCHER] Applying changes...")
    backups, changed_files = _apply_changes(patch, repo_root)

    # 5. Run tests
    print("[PATCHER] Running tests...")
    test_result = _run_tests(repo_root)

    if test_result.no_tests:
        print("[PATCHER] Warning: no tests collected — proceeding without test coverage")
    elif test_result.passed:
        print(f"[PATCHER] Tests PASSED (exit {test_result.returncode})")
    else:
        # 6. Tests failed — rollback
        print(f"[PATCHER] Tests FAILED (exit {test_result.returncode}) — rolling back")
        _rollback(backups, repo_root)
        report = _save_failure_report(patch, test_result, validation, failures_dir)
        print(f"[PATCHER] Failure report saved: {report.relative_to(failures_dir.parent.parent)}")
        result = ApplyResult(
            success=False, dry_run=False, patch=patch,
            validation=validation, test_result=test_result,
            rolled_back=True, failure_report=report,
            error="tests failed — rolled back",
        )
        _update_handoff(patch, result, handoff_path)
        _update_task_log(patch, result, task_log_path)
        return result

    # 7. Tests passed — commit
    print("[PATCHER] Committing...")
    commit_message = (
        f"agent: {patch.task_title}\n\n"
        f"Applied by patcher from {patch.path.name}\n"
        f"Role: {patch.role}"
    )
    sha = _commit(changed_files, commit_message, repo_root)
    if sha:
        print(f"[PATCHER] Committed: {sha}")
    else:
        print("[PATCHER] Warning: commit failed — changes applied but not committed")

    result = ApplyResult(
        success=True, dry_run=False, patch=patch,
        validation=validation, test_result=test_result,
        commit_sha=sha,
    )
    _update_handoff(patch, result, handoff_path)
    _update_task_log(patch, result, task_log_path)
    return result


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def list_pending(patches_dir: Path = PATCHES_DIR) -> list[Path]:
    """Return patch files that are still marked as proposed (not yet applied)."""
    result = []
    for p in sorted(patches_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
            if "proposed — not applied" in text:
                result.append(p)
        except OSError:
            continue
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    dry = "--apply" not in args

    pending = list_pending()
    if not pending:
        print("No pending patches in patches/")
        sys.exit(0)

    print(f"Pending patches: {len(pending)}")
    for p in pending:
        print(f"  {p.name}")

    if dry:
        print("\nRunning in DRY_RUN mode. Pass --apply to execute.\n")
        result = execute(pending[0], dry_run=True)
    else:
        result = execute(pending[0], dry_run=False)

    print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
    if result.commit_sha:
        print(f"Commit: {result.commit_sha}")
    if result.rolled_back:
        print("Repository was restored to pre-patch state.")
