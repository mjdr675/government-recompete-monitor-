"""Tests for scripts/notify.sh — Discord notification wrapper."""
import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "notify.sh"
AE_BIN = Path("/home/michael/autonomous-engineering/.venv/bin/ae")


def test_script_exists():
    assert SCRIPT.exists(), f"scripts/notify.sh not found at {SCRIPT}"


def test_script_is_executable():
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/notify.sh is not executable"


def test_script_contains_ae_venv_path():
    text = SCRIPT.read_text()
    assert "/home/michael/autonomous-engineering/.venv" in text


def test_script_contains_repo_label():
    text = SCRIPT.read_text()
    assert "Repo: Recompete.us" in text


def test_script_contains_branch_detection():
    text = SCRIPT.read_text()
    assert "rev-parse --abbrev-ref HEAD" in text


def test_ae_binary_exists():
    assert AE_BIN.exists(), f"ae binary not found at {AE_BIN}"


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
