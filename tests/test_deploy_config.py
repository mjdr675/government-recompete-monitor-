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
    # It must land on the RUNTIME PATH. Railway/Nixpacks runs the start command
    # with /opt/venv/bin on PATH (the app venv, where gunicorn lives) but NOT
    # /usr/local/bin. Deploy 3ebd98ed symlinked only into /usr/local/bin and
    # crashed with "'aws' CLI not on PATH", so require the venv location.
    assert "/opt/venv/bin/aws" in joined, (
        "aws must be linked/installed into /opt/venv/bin (on Railway's runtime "
        "PATH); /usr/local/bin alone is NOT on the runtime PATH (deploy 3ebd98ed "
        "crash)"
    )


def test_postgres_client_installed_via_build_phase(cfg):
    """scripts/backup_db.sh's pre-start backup shells out to `pg_dump` when
    DATABASE_URL points at Postgres. pg_dump must be in the built image or the
    fail-closed `&&` start command crash-loops the container (incident: deploy
    519872fd, "pg_dump not on PATH"). Ubuntu noble ships only postgresql-client-16
    and pg_dump refuses to dump a NEWER server (Railway Postgres is 18.4), so the
    build must add the PGDG apt repo and install the v18 client."""
    cmds = cfg.get("phases", {}).get("build", {}).get("cmds", [])
    joined = "\n".join(cmds).lower()
    assert "postgresql-client-18" in joined, (
        "build phase must install postgresql-client-18 (matches the PG 18.4 server; "
        "noble's default client-16 cannot dump an 18 server)"
    )
    assert "apt.postgresql.org" in joined, (
        "postgresql-client-18 is not in noble's default repos — the PGDG apt repo "
        "(apt.postgresql.org) must be added in the build phase"
    )


def test_pg_dump_on_runtime_path(cfg):
    """pg_dump must land on the RUNTIME PATH. Railway runs the start command with
    /opt/venv/bin on PATH but NOT /usr/local/bin (same crash mode that hit `aws`
    in deploy 3ebd98ed), so require the app-venv location."""
    cmds = cfg.get("phases", {}).get("build", {}).get("cmds", [])
    joined = "\n".join(cmds)
    assert "/opt/venv/bin/pg_dump" in joined, (
        "pg_dump must be linked into /opt/venv/bin (on Railway's runtime PATH); "
        "/usr/local/bin alone is NOT on the runtime PATH"
    )


def test_no_postgres_server_package(cfg):
    """Only the client is needed for backups — never install a PostgreSQL server."""
    import re

    setup = " ".join(cfg.get("phases", {}).get("setup", {}).get("aptPkgs", [])).lower()
    build = "\n".join(cfg.get("phases", {}).get("build", {}).get("cmds", [])).lower()
    # postgresql-client-* is fine; a bare postgresql / postgresql-<ver> server is not.
    server = re.search(
        r"\bpostgresql-server\b|install[^\n]*\bpostgresql\b(?!-client)",
        setup + "\n" + build,
    )
    assert server is None, (
        f"must not install a PostgreSQL server package: "
        f"{server.group() if server else ''}"
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
