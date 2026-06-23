"""Tests for scripts/notify.sh — Discord notification wrapper."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

from tools import registry

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "notify.sh"


def test_script_exists():
    assert SCRIPT.exists(), f"scripts/notify.sh not found at {SCRIPT}"


def test_script_is_executable():
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/notify.sh is not executable"


def test_script_uses_registry_for_ae():
    text = SCRIPT.read_text()
    # No hardcoded paths or venv coupling may remain in runtime code...
    assert "/home/michael/autonomous-engineering" not in text
    assert "/usr/local/bin" not in text
    assert "activate" not in text
    assert "which ae" not in text
    # ...and `ae` must be detected through the central tool registry.
    assert "registry" in text


def test_script_contains_repo_label():
    text = SCRIPT.read_text()
    assert "Repo: Recompete.us" in text


def test_script_contains_branch_detection():
    text = SCRIPT.read_text()
    assert "rev-parse --abbrev-ref HEAD" in text


def test_ae_resolution_contract():
    """`ae` is resolved through the central registry, never a hardcoded path.

    Validates behaviour, not filesystem layout. When `ae` is absent (e.g. in CI)
    the registry reports it unavailable and the test is skipped — notify.sh
    degrades gracefully in that case. When present, the contract must hold."""
    tool = registry.get("ae")
    if not tool.available:
        assert tool.path is None
        pytest.skip("ae not installed (CI/portable env); notify.sh degrades gracefully")
    assert tool.path is not None
    assert Path(tool.path).exists()


def test_script_exits_nonzero_without_event_arg():
    """Running notify.sh with no arguments should fail (ae notify requires an event)."""
    env = {**os.environ, "AE_DISCORD_WEBHOOK_URL": ""}
    result = subprocess.run(
        [str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0


def test_script_help_passes_through():
    """notify.sh -- --help should print ae notify usage without error."""
    env = {**os.environ, "AE_DISCORD_WEBHOOK_URL": ""}
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "notify" in result.stdout.lower() or "Usage" in result.stdout
