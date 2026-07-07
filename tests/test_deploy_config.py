"""Static validation of the Railway / Nixpacks deploy config (nixpacks.toml).

These are hermetic parse-only checks — no build, no network, no Railway. They
lock in the fix for the PR #45 build failure: Ubuntu "noble" has no `awscli` apt
installation candidate, so `awscli` must NOT be an apt package; it is instead
pip-installed in the build phase. They also guard the fail-closed start command
(backup must run before gunicorn via `&&`).
"""
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NIXPACKS = REPO_ROOT / "nixpacks.toml"


@pytest.fixture(scope="module")
def cfg():
    with open(NIXPACKS, "rb") as fh:
        return tomllib.load(fh)


def test_nixpacks_exists():
    assert NIXPACKS.is_file(), "nixpacks.toml must exist for Railway builds"


def test_awscli_not_in_apt_packages(cfg):
    # Regression guard for build 7852b515: `awscli` has no apt candidate on noble.
    apt = cfg.get("phases", {}).get("setup", {}).get("aptPkgs", [])
    offending = [p for p in apt if "awscli" in p.lower() or p.lower() == "aws"]
    assert not offending, (
        f"awscli must not be an apt package (no noble candidate); found {offending}. "
        "Install it via the build phase instead."
    )


def test_awscli_installed_via_build_phase(cfg):
    # The AWS CLI must be provisioned some non-apt way (pip/venv) in the build phase.
    cmds = cfg.get("phases", {}).get("build", {}).get("cmds", [])
    joined = "\n".join(cmds).lower()
    assert "awscli" in joined, "build phase must install awscli (e.g. pip install awscli)"
    assert "pip install" in joined and "awscli" in joined, (
        "awscli should be pip-installed in the build phase"
    )
    # And it must land on PATH (symlinked or installed into a PATH dir).
    assert "/usr/local/bin/aws" in joined or "ensurepath" in joined, (
        "the aws entrypoint must be placed on PATH (e.g. symlink into /usr/local/bin)"
    )


def test_start_command_is_fail_closed_backup_then_gunicorn(cfg):
    # Preserve the fail-closed contract: backup runs BEFORE gunicorn, gated by &&.
    start = cfg.get("start", {}).get("cmd", "")
    assert "backup_db.sh predeploy" in start, "start cmd must run the pre-start backup"
    assert "gunicorn" in start, "start cmd must launch gunicorn"
    assert "&&" in start, "backup and gunicorn must be chained with && (fail-closed)"
    assert start.index("backup_db.sh") < start.index("gunicorn"), (
        "backup must run BEFORE gunicorn"
    )
