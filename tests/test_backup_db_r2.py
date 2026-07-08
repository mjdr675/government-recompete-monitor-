"""Tests for scripts/backup_db.sh — Cloudflare R2 off-site upload + local behavior.

These are hermetic: a fake `aws` CLI (a small bash stub that stores objects in a
local directory) stands in for Cloudflare R2, so no real credentials or network
are involved. The stub honors FAKE_S3_FAIL to simulate upload/download failures
and lists "old" objects by mtime so retention can be exercised.
"""
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKUP_SH = REPO_ROOT / "scripts" / "backup_db.sh"

# A fake `aws` that emulates just the subcommands backup_db.sh uses, backed by a
# local directory ($FAKE_S3_DIR/<bucket>/<key>).
AWS_STUB = r"""#!/usr/bin/env bash
set -u
# strip "--endpoint-url URL"
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --endpoint-url) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
set -- "${args[@]}"
root="${FAKE_S3_DIR:?FAKE_S3_DIR unset}"
svc="${1:-}"; shift || true
s3fs() { local p="${1#s3://}"; printf '%s/%s' "$root" "$p"; }

if [ "$svc" = "s3" ]; then
  op="${1:-}"; shift || true
  a=(); for x in "$@"; do [ "$x" = "--only-show-errors" ] || a+=("$x"); done
  set -- "${a[@]}"
  case "$op" in
    cp)
      src="$1"; dst="$2"
      if [[ "$src" == s3://* ]]; then
        [ "${FAKE_S3_FAIL:-}" = "download" ] && { echo "fake download failure" >&2; exit 1; }
        fp="$(s3fs "$src")"; [ -f "$fp" ] || { echo "fake: key not found" >&2; exit 1; }
        cp "$fp" "$dst"
      else
        [ "${FAKE_S3_FAIL:-}" = "upload" ] && { echo "fake upload failure" >&2; exit 1; }
        fp="$(s3fs "$dst")"; mkdir -p "$(dirname "$fp")"; cp "$src" "$fp"
      fi
      ;;
    rm) rm -f "$(s3fs "$1")" ;;
  esac
elif [ "$svc" = "s3api" ]; then
  bucket=""
  while [ $# -gt 0 ]; do case "$1" in --bucket) bucket="$2"; shift 2 ;; *) shift ;; esac; done
  bdir="$root/$bucket"
  [ -d "$bdir" ] || exit 0
  # Emit keys older than FAKE_RETAIN_DAYS (default 14) by mtime — stands in for
  # the LastModified<cutoff query the real script sends.
  find "$bdir" -type f -name 'backup_*' -mtime +"${FAKE_RETAIN_DAYS:-14}" -printf '%P\n'
fi
exit 0
"""


# A controllable `sqlite3` stand-in for the CLI-path tests. It emulates the only
# two invocations backup_db.sh makes — `.backup '<path>'` (used to snapshot) and
# `PRAGMA integrity_check;` (used to verify). The integrity result is driven by
# FAKE_SQLITE3_RESULT: "ok" → prints ok/exit 0; anything else mimics real sqlite3
# on a corrupt file (error to stderr, no stdout, nonzero exit).
SQLITE3_STUB = r"""#!/usr/bin/env bash
set -u
db="${1:-}"; sql="${2:-}"
case "$sql" in
  .backup*)
    tgt="${sql#.backup }"; tgt="${tgt#\'}"; tgt="${tgt%\'}"
    cp "$db" "$tgt"; exit $? ;;
  *integrity_check*)
    if [ "${FAKE_SQLITE3_RESULT:-ok}" = "ok" ]; then echo "ok"; exit 0
    else echo "Error: file is not a database" >&2; exit 1; fi ;;
  *) exit 0 ;;
esac
"""


@pytest.fixture(scope="session")
def sqlite3_free_bin(tmp_path_factory):
    """A PATH dir symlinking every real executable EXCEPT `sqlite3`, so
    `command -v sqlite3` is deterministically FALSE regardless of the host. This
    forces backup_db.sh onto its python3 fallback and stops a host sqlite3 from
    silently satisfying the check (CodeRabbit #2)."""
    d = tmp_path_factory.mktemp("nosqlite3")
    seen = set()
    for pdir in os.environ.get("PATH", "").split(os.pathsep):
        pd = Path(pdir)
        if not pd.is_dir():
            continue
        for exe in pd.iterdir():
            if exe.name == "sqlite3" or exe.name in seen:
                continue
            try:
                if not exe.is_dir() and os.access(exe, os.X_OK):
                    (d / exe.name).symlink_to(exe)
                    seen.add(exe.name)
            except OSError:
                pass
    return d


def with_sqlite3_stub(env, tmp_path, result="ok"):
    """Copy of `env` with the controllable `sqlite3` stub prepended to PATH, so
    `command -v sqlite3` is TRUE and resolves to the stub (never the host). Used
    to exercise the sqlite3-CLI verification branch deterministically."""
    d = tmp_path / "sqlite3bin"
    d.mkdir(exist_ok=True)
    s = d / "sqlite3"
    s.write_text(SQLITE3_STUB)
    s.chmod(0o755)
    e = dict(env)
    e["PATH"] = f"{d}{os.pathsep}{e['PATH']}"
    e["FAKE_SQLITE3_RESULT"] = result
    return e


@pytest.fixture
def env_setup(tmp_path, sqlite3_free_bin):
    """A tmp SQLite 'db', a local backup dir, a fake-S3 dir, and a stub `aws`.

    PATH is built from a sqlite3-free bin so the default env deterministically
    exercises the python3 fallback; CLI-path tests opt in via with_sqlite3_stub."""
    db = tmp_path / "contracts.db"
    # A REAL, valid SQLite database so verify_backup's PRAGMA integrity_check
    # returns "ok".
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO contracts (name) VALUES (?)", [(f"c{i}",) for i in range(5)])
    con.commit()
    con.close()
    backup_dir = tmp_path / "backups"
    fake_s3 = tmp_path / "s3"
    fake_s3.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    aws = bindir / "aws"
    aws.write_text(AWS_STUB)
    aws.chmod(0o755)

    base = dict(os.environ)
    base.update(
        # bindir (aws stub) first, then the sqlite3-free real toolchain — NO host
        # sqlite3 leaks in, so `command -v sqlite3` is false by default.
        PATH=f"{bindir}{os.pathsep}{sqlite3_free_bin}",
        RECOMPETE_BACKUP_DIR=str(backup_dir),
        DB_PATH=str(db),
        FAKE_S3_DIR=str(fake_s3),
    )
    base.pop("DATABASE_URL", None)  # force the SQLite path
    return {
        "tmp": tmp_path, "db": db, "backup_dir": backup_dir,
        "fake_s3": fake_s3, "env": base,
    }


def run_backup(env, label="predeploy", cwd=None):
    return subprocess.run(
        ["bash", str(BACKUP_SH), label],
        env=env, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
    )


def r2_env(env, **over):
    e = dict(env)
    e.update(
        R2_ENDPOINT="https://fake.r2.cloudflarestorage.com",
        R2_ACCESS_KEY_ID="AKIA_FAKE",
        R2_SECRET_ACCESS_KEY="secret_fake",
        R2_BUCKET="recompete-backups",
    )
    e.update(over)
    return e


def backups_in(d):
    return sorted(Path(d).glob("backup_*.gz")) if Path(d).exists() else []


# ── local behavior (unchanged when R2 is not configured) ──────────────────────
def test_local_backup_when_r2_unset(env_setup):
    r = run_backup(env_setup["env"], cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert backups_in(env_setup["backup_dir"]), "no local backup written"
    assert (env_setup["backup_dir"] / ".last_backup_ok").exists()
    assert "local backup only" in r.stdout


# ── fail-closed on partial/misconfigured R2 (before any snapshot) ─────────────
def test_partial_r2_config_fails_closed(env_setup):
    env = dict(env_setup["env"])
    env["R2_BUCKET"] = "recompete-backups"  # only one of four → misconfig
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 1
    assert "partially configured" in (r.stdout + r.stderr)
    assert not backups_in(env_setup["backup_dir"]), "must abort before snapshotting"


# ── happy path: upload + restore-verify ───────────────────────────────────────
def test_r2_upload_and_verify(env_setup):
    env = r2_env(env_setup["env"])
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    local = backups_in(env_setup["backup_dir"])
    assert local, "no local backup written"
    # object landed in the fake bucket, byte-identical to the local archive
    uploaded = list((env_setup["fake_s3"] / "recompete-backups").glob("backup_*.gz"))
    assert len(uploaded) == 1
    assert uploaded[0].read_bytes() == local[0].read_bytes()
    assert "R2 upload verified" in r.stdout


# ── fail-closed when the upload itself fails ──────────────────────────────────
def test_r2_upload_failure_aborts(env_setup):
    env = r2_env(env_setup["env"], FAKE_S3_FAIL="upload")
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 1
    assert "R2 upload failed" in (r.stdout + r.stderr)


# ── fail-closed when the restore-verification re-download fails ───────────────
def test_r2_download_verify_failure_aborts(env_setup):
    env = r2_env(env_setup["env"], FAKE_S3_FAIL="download")
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 1
    assert "re-download failed" in (r.stdout + r.stderr)


# ── python3 fallback path (sqlite3 CLI deterministically absent) ──────────────
def test_backup_runs_integrity_check_without_sqlite3_cli(env_setup):
    # env_setup's PATH has no sqlite3, so verify_backup MUST use the python3
    # fallback and actually run PRAGMA integrity_check — not just the gzip layer.
    env = r2_env(env_setup["env"])
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout + r.stderr
    assert "PRAGMA integrity_check=ok" in out
    assert "verified gzip layer only" not in out


def test_corrupt_db_fails_integrity_check_closed_python3(env_setup):
    # Corrupt DB via the python3 fallback → must FAIL and abort BEFORE any upload,
    # never fall through to the gzip-only pass.
    env_setup["db"].write_bytes(b"SQLite format 3\x00" + b"\x00" * 512)  # not a real DB
    env = r2_env(env_setup["env"])
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 1, r.stderr + r.stdout
    assert "integrity_check failed" in (r.stdout + r.stderr)
    assert "verified gzip layer only" not in (r.stdout + r.stderr)
    bucket = env_setup["fake_s3"] / "recompete-backups"
    assert not (bucket.exists() and list(bucket.glob("backup_*.gz")))


# ── sqlite3-CLI verification branch (deterministic via stub) ──────────────────
def test_sqlite3_cli_path_good_verifies(env_setup):
    # With the sqlite3 stub present, verify_backup takes the CLI branch and passes
    # on a healthy integrity_check.
    env = with_sqlite3_stub(r2_env(env_setup["env"]), env_setup["tmp"], result="ok")
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout + r.stderr
    assert "PRAGMA integrity_check=ok" in out
    assert "verified gzip layer only" not in out


def test_sqlite3_cli_path_corrupt_fails_closed(env_setup):
    # CodeRabbit #1: when the sqlite3 CLI reports corruption (nonzero exit, no
    # stdout), verify_backup must FAIL closed — NOT treat empty output as
    # "tool absent" and pass on the gzip layer. Also must not upload to R2.
    env = with_sqlite3_stub(r2_env(env_setup["env"]), env_setup["tmp"], result="corrupt")
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 1, r.stderr + r.stdout
    assert "integrity_check failed" in (r.stdout + r.stderr)
    assert "verified gzip layer only" not in (r.stdout + r.stderr)
    bucket = env_setup["fake_s3"] / "recompete-backups"
    assert not (bucket.exists() and list(bucket.glob("backup_*.gz")))


# ── retention: objects older than the window are pruned from R2 ───────────────
def test_r2_retention_prunes_old(env_setup):
    bucket = env_setup["fake_s3"] / "recompete-backups"
    bucket.mkdir(parents=True)
    old = bucket / "backup_2000-01-01_000000_old.db.gz"
    old.write_bytes(b"old")
    twenty_days_ago = time.time() - 20 * 86400
    os.utime(old, (twenty_days_ago, twenty_days_ago))

    env = r2_env(env_setup["env"])
    r = run_backup(env, cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert not old.exists(), "old (>14d) R2 object should have been pruned"
    # the freshly uploaded object remains
    assert list(bucket.glob("backup_*.gz")), "current backup must be retained"
