"""
Integration tests for ai_agent/patcher.py.

Each test gets an isolated temporary git repository with real files and a
committed baseline — no mocking. Tests cover the full pipeline including
rollback on test failure.
"""

import subprocess
import textwrap
from pathlib import Path

import pytest

from ai_agent.patcher import (
    Change, Patch, ValidationResult,
    parse_patch, validate, execute, list_pending,
    _apply_changes, _rollback, _run_tests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, cwd=cwd,
        capture_output=True, text=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a committed Python file and a passing test."""
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)

    # Source file to patch
    (repo / "calc.py").write_text(textwrap.dedent("""\
        def add(a, b):
            return a + b

        def subtract(a, b):
            return a - b
    """))

    # Passing test suite
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_calc.py").write_text(textwrap.dedent("""\
        from calc import add, subtract

        def test_add():
            assert add(1, 2) == 3

        def test_subtract():
            assert subtract(5, 3) == 2
    """))

    _git(["add", "."], repo)
    _git(["commit", "-m", "initial"], repo)
    return repo


def _make_patch_file(patches_dir: Path, task: str, file: str,
                     before: str, after: str, role: str = "backend") -> Path:
    """
    Build a patch file in the exact format that patcher.py expects.
    Does NOT use textwrap.dedent — embedded before/after strings contain
    meaningful indentation that dedent would destroy.
    """
    patches_dir.mkdir(parents=True, exist_ok=True)
    slug = task.lower().replace(" ", "_")[:30]
    path = patches_dir / f"20260101_000000_{slug}.md"
    # Ensure before/after end with a newline so the closing fence is on its own line
    b = before if before.endswith("\n") else before + "\n"
    a = after  if after.endswith("\n")  else after  + "\n"
    content = (
        f"# Proposed Patch\n"
        f"**Task:** {task}\n"
        f"**Source:** high.md\n"
        f"**Role:** {role}\n"
        f"**Status:** proposed — not applied\n"
        f"\n---\n\n"
        f"## Summary\nTest patch.\n\n"
        f"## Files to Change\n- {file}\n\n"
        f"## Patch: {file}\n"
        f"### Before\n"
        f"```python\n"
        f"{b}"
        f"```\n"
        f"### After\n"
        f"```python\n"
        f"{a}"
        f"```\n"
    )
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParsePatch:
    def test_parse_metadata(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Add multiply", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        )
        patch = parse_patch(pf)
        assert patch.task_title == "Add multiply"
        assert patch.role == "backend"
        assert patch.source == "high.md"

    def test_parse_changes(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "My task", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(x, y):\n    return x + y\n",
        )
        patch = parse_patch(pf)
        assert len(patch.changes) == 1
        assert patch.changes[0].file == "calc.py"
        assert "def add(a, b)" in patch.changes[0].before
        assert "def add(x, y)" in patch.changes[0].after

    def test_parse_no_blocks_returns_empty(self, tmp_path: Path) -> None:
        pf = tmp_path / "empty.md"
        pf.write_text("# Proposed Patch\n**Task:** nothing\n\nNo patch blocks here.\n")
        patch = parse_patch(pf)
        assert patch.changes == []

    def test_parse_multiple_blocks(self, tmp_path: Path) -> None:
        pf = tmp_path / "multi.md"
        pf.write_text(textwrap.dedent("""\
            # Proposed Patch
            **Task:** Two files
            **Source:** high.md
            **Role:** backend
            **Status:** proposed — not applied

            ## Patch: file_a.py
            ### Before
            ```python
            x = 1
            ```
            ### After
            ```python
            x = 2
            ```

            ## Patch: file_b.py
            ### Before
            ```python
            y = 1
            ```
            ### After
            ```python
            y = 2
            ```
        """))
        patch = parse_patch(pf)
        assert len(patch.changes) == 2
        assert patch.changes[0].file == "file_a.py"
        assert patch.changes[1].file == "file_b.py"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_patch_passes(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Task", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return a + b + 0\n",
        )
        patch = parse_patch(pf)
        result = validate(patch, repo)
        assert result.valid, result.errors

    def test_no_changes_fails(self, tmp_path: Path) -> None:
        pf = tmp_path / "no_changes.md"
        pf.write_text("# Proposed Patch\n**Task:** nothing\n\n(no blocks)\n")
        patch = parse_patch(pf)
        result = validate(patch, tmp_path)
        assert not result.valid
        assert any("No Patch:" in e for e in result.errors)

    def test_file_not_found(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="nonexistent.py", before="x", after="y")],
        )
        result = validate(patch, repo)
        assert not result.valid
        assert any("not found" in e for e in result.errors)

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="../outside.py", before="x", after="y")],
        )
        result = validate(patch, repo)
        assert not result.valid
        assert any("traversal" in e.lower() for e in result.errors)

    def test_before_not_found(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="calc.py",
                            before="def totally_missing_function():\n    pass\n",
                            after="def replaced():\n    pass\n")],
        )
        result = validate(patch, repo)
        assert not result.valid
        assert any("not found" in e for e in result.errors)

    def test_ambiguous_before_blocked(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        # Write a file with a repeated pattern
        (repo / "dup.py").write_text("x = 1\nx = 1\n")
        _git(["add", "dup.py"], repo)
        _git(["commit", "-m", "add dup"], repo)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="dup.py", before="x = 1\n", after="x = 2\n")],
        )
        result = validate(patch, repo)
        assert not result.valid
        assert any("ambiguous" in e for e in result.errors)

    def test_binary_file_blocked(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        _git(["add", "img.png"], repo)
        _git(["commit", "-m", "add binary"], repo)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="img.png", before="PNG", after="JPG")],
        )
        result = validate(patch, repo)
        assert not result.valid
        assert any("Binary" in e for e in result.errors)

    def test_absolute_path_outside_repo_blocked(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="/etc/passwd", before="root", after="hacked")],
        )
        result = validate(patch, repo)
        assert not result.valid


# ---------------------------------------------------------------------------
# Apply + rollback unit tests
# ---------------------------------------------------------------------------

class TestApplyRollback:
    def test_apply_modifies_file(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="calc.py",
                            before="def add(a, b):\n    return a + b\n",
                            after="def add(a, b):\n    return a + b  # patched\n")],
        )
        _apply_changes(patch, repo)
        content = (repo / "calc.py").read_text()
        assert "# patched" in content

    def test_rollback_restores_original(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        original = (repo / "calc.py").read_text()
        patch = Patch(
            path=tmp_path / "x.md", task_title="t", role="r", source="s",
            changes=[Change(file="calc.py",
                            before="def add(a, b):\n    return a + b\n",
                            after="def add(a, b):\n    return 999\n")],
        )
        backups, _ = _apply_changes(patch, repo)
        assert (repo / "calc.py").read_text() != original
        _rollback(backups, repo)
        assert (repo / "calc.py").read_text() == original


# ---------------------------------------------------------------------------
# execute() — full pipeline integration tests
# ---------------------------------------------------------------------------

class TestExecute:
    def test_dry_run_does_not_modify_files(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        original = (repo / "calc.py").read_text()
        pf = _make_patch_file(
            repo / "patches", "Dry run task", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return a + b  # dry\n",
        )
        result = execute(pf, repo_root=repo, dry_run=True)
        assert result.dry_run is True
        assert result.success is True
        assert (repo / "calc.py").read_text() == original

    def test_dry_run_validation_failure(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Bad patch", "calc.py",
            "def this_does_not_exist():\n    pass\n",
            "def replaced():\n    pass\n",
        )
        result = execute(pf, repo_root=repo, dry_run=True)
        assert result.success is False
        assert not result.validation.valid

    def test_successful_apply_commits(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Add docstring", "calc.py",
            "def add(a, b):\n    return a + b\n",
            'def add(a, b):\n    """Return sum."""\n    return a + b\n',
        )
        log_before = _git(["log", "--oneline"], repo).stdout.strip()

        result = execute(
            pf, repo_root=repo, dry_run=False,
            handoff_path=repo / "HANDOFF.md",
            task_log_path=repo / "TASK_LOG.md",
        )

        assert result.success is True
        assert result.rolled_back is False
        assert result.commit_sha is not None
        assert '"""Return sum."""' in (repo / "calc.py").read_text()

        log_after = _git(["log", "--oneline"], repo).stdout.strip()
        assert len(log_after.splitlines()) == len(log_before.splitlines()) + 1

    def test_failed_tests_trigger_rollback(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        original = (repo / "calc.py").read_text()

        # This patch breaks the add() function — tests will fail
        pf = _make_patch_file(
            repo / "patches", "Break add", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return a - b  # intentionally broken\n",
        )

        result = execute(
            pf, repo_root=repo, dry_run=False,
            handoff_path=repo / "HANDOFF.md",
            task_log_path=repo / "TASK_LOG.md",
        )

        # Pipeline should have rolled back
        assert result.success is False
        assert result.rolled_back is True
        assert result.test_result is not None
        assert not result.test_result.passed

        # File must be restored
        assert (repo / "calc.py").read_text() == original

        # No new commit
        log = _git(["log", "--oneline"], repo).stdout.strip().splitlines()
        assert len(log) == 1  # only the initial commit

        # Failure report must exist
        assert result.failure_report is not None
        assert result.failure_report.exists()

    def test_rollback_leaves_no_partial_state(self, tmp_path: Path) -> None:
        """After rollback, git status must show no modified files."""
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Break subtract", "calc.py",
            "def subtract(a, b):\n    return a - b\n",
            "def subtract(a, b):\n    return None  # broken\n",
        )
        execute(pf, repo_root=repo, dry_run=False,
                handoff_path=repo / "HANDOFF.md",
                task_log_path=repo / "TASK_LOG.md")

        status = _git(["status", "--porcelain"], repo).stdout.strip()
        # Only untracked files (patches/) are acceptable — no modified tracked files
        modified = [line for line in status.splitlines()
                    if line.startswith(" M") or line.startswith("M ")]
        assert modified == [], f"Unexpected modified files after rollback: {modified}"

    def test_handoff_updated_on_success(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        handoff = repo / "HANDOFF.md"
        handoff.write_text("# HANDOFF\n")
        pf = _make_patch_file(
            repo / "patches", "Minor fix", "calc.py",
            "def add(a, b):\n    return a + b\n",
            'def add(a, b):\n    """Add two numbers."""\n    return a + b\n',
        )
        execute(pf, repo_root=repo, dry_run=False,
                handoff_path=handoff, task_log_path=repo / "TASK_LOG.md")
        content = handoff.read_text()
        assert "Minor fix" in content
        assert "PATCHER" in content

    def test_task_log_updated_on_rollback(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        task_log = repo / "TASK_LOG.md"
        task_log.write_text("| Timestamp | Role | Task | Source | Outcome |\n|---|---|---|---|---|\n")
        pf = _make_patch_file(
            repo / "patches", "Rollback task", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return BROKEN\n",
        )
        execute(pf, repo_root=repo, dry_run=False,
                handoff_path=repo / "HANDOFF.md", task_log_path=task_log)
        content = task_log.read_text()
        assert "rolled-back" in content

    def test_failure_report_contains_test_output(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        pf = _make_patch_file(
            repo / "patches", "Cause failure", "calc.py",
            "def add(a, b):\n    return a + b\n",
            "def add(a, b):\n    return 0\n",
        )
        result = execute(pf, repo_root=repo, dry_run=False,
                         handoff_path=repo / "HANDOFF.md",
                         task_log_path=repo / "TASK_LOG.md")
        assert result.failure_report is not None
        report_text = result.failure_report.read_text()
        assert "Test Result" in report_text


# ---------------------------------------------------------------------------
# list_pending()
# ---------------------------------------------------------------------------

class TestListPending:
    def test_finds_pending_patches(self, tmp_path: Path) -> None:
        patches_dir = tmp_path / "patches"
        patches_dir.mkdir()
        p = patches_dir / "test.md"
        p.write_text("**Status:** proposed — not applied\n")
        assert p in list_pending(patches_dir)

    def test_ignores_non_pending(self, tmp_path: Path) -> None:
        patches_dir = tmp_path / "patches"
        patches_dir.mkdir()
        p = patches_dir / "done.md"
        p.write_text("**Status:** applied\n")
        assert p not in list_pending(patches_dir)

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        patches_dir = tmp_path / "patches"
        patches_dir.mkdir()
        assert list_pending(patches_dir) == []
