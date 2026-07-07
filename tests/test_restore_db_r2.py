"""Tests for scripts/restore_db.sh — Cloudflare R2 restore/verify mode.

Hermetic: a fake `aws` CLI backed by a local directory stands in for R2, and the
snapshots are real gzipped SQLite databases built with python3. No real R2,
credentials, or network are involved. Covers: --r2-list, --from-r2 --verify-only
(download + PRAGMA integrity_check + row/schema sanity WITHOUT touching the live
DB), fail-closed on missing creds and on a corrupt snapshot, and an actual
--from-r2 restore.
"""
import gzip
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RESTORE_SH = REPO_ROOT / "scripts" / "restore_db.sh"

AWS_STUB = r"""#!/usr/bin/env bash
set -u
args=(); while [ $# -gt 0 ]; do case "$1" in --endpoint-url) shift 2 ;; *) args+=("$1"); shift ;; esac; done
set -- "${args[@]}"
root="${FAKE_S3_DIR:?}"; svc="${1:-}"; shift || true
s3fs() { local p="${1#s3://}"; printf '%s/%s' "$root" "$p"; }
if [ "$svc" = "s3" ]; then
  op="${1:-}"; shift || true
  a=(); for x in "$@"; do [ "$x" = "--only-show-errors" ] || a+=("$x"); done; set -- "${a[@]}"
  case "$op" in
    cp)
      src="$1"; dst="$2"
      if [[ "$src" == s3://* ]]; then
        [ "${FAKE_S3_FAIL:-}" = "download" ] && { echo "fake download failure" >&2; exit 1; }
        fp="$(s3fs "$src")"; [ -f "$fp" ] || { echo "fake: key not found" >&2; exit 1; }; cp "$fp" "$dst"
      else fp="$(s3fs "$dst")"; mkdir -p "$(dirname "$fp")"; cp "$src" "$fp"; fi ;;
  esac
elif [ "$svc" = "s3api" ]; then
  [ "${FAKE_S3_FAIL:-}" = "list" ] && { echo "fake list-objects failure" >&2; exit 1; }
  bucket=""; while [ $# -gt 0 ]; do case "$1" in --bucket) bucket="$2"; shift 2 ;; *) shift ;; esac; done
  bdir="$root/$bucket"; [ -d "$bdir" ] || exit 0
  # newest first, one key per line (stands in for the reverse(sort_by(LastModified)) query)
  (cd "$bdir" && ls -1t backup_* 2>/dev/null)
fi
exit 0
"""


def make_sqlite_gz(path: Path, rows=3):
    """Write a real, valid gzipped SQLite snapshot to `path`."""
    raw = path.with_suffix(".raw")
    con = sqlite3.connect(raw)
    con.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO contracts (name) VALUES (?)",
                    [(f"c{i}",) for i in range(rows)])
    con.commit()
    con.close()
    with open(raw, "rb") as fh, gzip.open(path, "wb") as out:
        out.write(fh.read())
    raw.unlink()


@pytest.fixture
def env_setup(tmp_path):
    fake_s3 = tmp_path / "s3"
    (fake_s3 / "recompete-backups").mkdir(parents=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    aws = bindir / "aws"
    aws.write_text(AWS_STUB)
    aws.chmod(0o755)
    # a live dev DB for the schema/row comparison
    live = tmp_path / "contracts.db"
    con = sqlite3.connect(live)
    con.execute("CREATE TABLE contracts (id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO contracts (name) VALUES (?)", [(f"live{i}",) for i in range(10)])
    con.commit()
    con.close()

    env = dict(os.environ)
    env.update(
        PATH=f"{bindir}:{os.environ['PATH']}",
        FAKE_S3_DIR=str(fake_s3),
        DB_PATH=str(live),
        R2_ENDPOINT="https://fake.r2", R2_ACCESS_KEY_ID="AK",
        R2_SECRET_ACCESS_KEY="sk", R2_BUCKET="recompete-backups",
    )
    env.pop("DATABASE_URL", None)
    return {"tmp": tmp_path, "bucket": fake_s3 / "recompete-backups", "live": live, "env": env}


def run(env, *args, cwd=None):
    return subprocess.run(["bash", str(RESTORE_SH), *args], env=env,
                          cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def test_r2_list_lists_keys(env_setup):
    make_sqlite_gz(env_setup["bucket"] / "backup_2026-07-01_000000_a.db.gz")
    make_sqlite_gz(env_setup["bucket"] / "backup_2026-07-02_000000_b.db.gz")
    r = run(env_setup["env"], "--r2-list", cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert "backup_2026-07-01_000000_a.db.gz" in r.stdout
    assert "backup_2026-07-02_000000_b.db.gz" in r.stdout


def test_verify_only_validates_without_touching_live_db(env_setup):
    make_sqlite_gz(env_setup["bucket"] / "backup_2026-07-07_000000_x.db.gz", rows=3)
    before = env_setup["live"].read_bytes()
    r = run(env_setup["env"], "--from-r2", "--latest", "--verify-only", cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout + r.stderr
    assert "PRAGMA integrity_check = ok" in out
    assert "[validate] OK" in out
    assert "live database NOT modified" in out
    # live DB must be byte-for-byte unchanged, and no restore/safety-copy occurred
    assert env_setup["live"].read_bytes() == before
    assert not list(env_setup["tmp"].glob("contracts.db.pre-restore.*"))


def test_from_r2_missing_creds_fails_closed(env_setup):
    env = dict(env_setup["env"])
    env.pop("R2_SECRET_ACCESS_KEY", None)  # partial config
    r = run(env, "--from-r2", "--latest", "--verify-only", cwd=env_setup["tmp"])
    assert r.returncode != 0
    assert "R2 not configured" in (r.stdout + r.stderr)


def test_corrupt_snapshot_fails_closed(env_setup):
    # a non-gzip object → gzip -t must fail the validation
    (env_setup["bucket"] / "backup_2026-07-07_000000_bad.db.gz").write_bytes(b"not a gzip file")
    r = run(env_setup["env"], "--from-r2", "--latest", "--verify-only", cwd=env_setup["tmp"])
    assert r.returncode != 0
    assert "gzip integrity check failed" in (r.stdout + r.stderr)
    assert env_setup["live"].exists()  # live DB untouched


def test_verify_only_without_from_r2_is_rejected(env_setup):
    # --verify-only is an R2 rehearsal flag; used for a LOCAL restore it must fail
    # early and never fall through to the destructive overwrite, even with --yes.
    bdir = env_setup["tmp"] / "local-backups"
    bdir.mkdir()
    make_sqlite_gz(bdir / "backup_2026-07-07_000000_x.db.gz", rows=3)
    env = dict(env_setup["env"])
    env["RECOMPETE_BACKUP_DIR"] = str(bdir)
    before = env_setup["live"].read_bytes()
    r = run(env, "--verify-only", "--yes", cwd=env_setup["tmp"])
    assert r.returncode != 0
    assert "--verify-only is only valid together with --from-r2" in (r.stdout + r.stderr)
    # live DB untouched; no restore and no pre-restore safety copy occurred
    assert env_setup["live"].read_bytes() == before
    assert not list(env_setup["tmp"].glob("contracts.db.pre-restore.*"))


def test_r2_list_failure_fails_closed(env_setup):
    # A failed `aws s3api list-objects-v2` must NOT be reported as an empty bucket.
    make_sqlite_gz(env_setup["bucket"] / "backup_2026-07-07_000000_x.db.gz")
    env = dict(env_setup["env"])
    env["FAKE_S3_FAIL"] = "list"
    r = run(env, "--r2-list", cwd=env_setup["tmp"])
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "(none found)" not in out
    assert "R2 listing failed" in out


def test_from_r2_latest_list_failure_fails_closed(env_setup):
    # Latest-key selection must distinguish a listing failure from an empty bucket.
    make_sqlite_gz(env_setup["bucket"] / "backup_2026-07-07_000000_x.db.gz")
    env = dict(env_setup["env"])
    env["FAKE_S3_FAIL"] = "list"
    r = run(env, "--from-r2", "--latest", "--verify-only", cwd=env_setup["tmp"])
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "R2 listing failed" in out
    assert "no backups found" not in out  # must not misreport as empty


def test_from_r2_restore_overwrites_with_yes(env_setup):
    snap = env_setup["bucket"] / "backup_2026-07-07_000000_x.db.gz"
    make_sqlite_gz(snap, rows=3)
    r = run(env_setup["env"], "--from-r2", "--latest", "--yes", cwd=env_setup["tmp"])
    assert r.returncode == 0, r.stderr + r.stdout
    # live DB now holds the snapshot's 3 rows (not the original 10)
    con = sqlite3.connect(env_setup["live"])
    n = con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    con.close()
    assert n == 3
    # a pre-restore safety copy was written
    assert list(env_setup["tmp"].glob("contracts.db.pre-restore.*"))
