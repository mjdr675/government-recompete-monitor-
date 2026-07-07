#!/usr/bin/env bash
#
# Restore a Recompete database backup produced by scripts/backup_db.sh.
#
# Usage (local backups):
#   restore_db.sh --list                 List available LOCAL backups (newest first)
#   restore_db.sh [--yes]                Restore the LATEST local backup
#   restore_db.sh [--yes] <file>         Restore a specific local backup
#                                        (<file> may be a bare name in the
#                                         backup dir or an absolute path)
#
# Usage (off-site Cloudflare R2):
#   restore_db.sh --r2-list                          List R2 backups (newest first)
#   restore_db.sh --from-r2 [--latest|<key>] \
#                 [--verify-only] [--yes]            Download a snapshot from R2 into
#                                                    a scratch dir, VALIDATE it (gzip +
#                                                    PRAGMA integrity_check + table/row
#                                                    sanity vs the live DB), then either
#                                                    restore it (needs --yes) or, with
#                                                    --verify-only, STOP after validation
#                                                    WITHOUT touching the live DB
#                                                    (a restore rehearsal).
#
# Behavior:
#   - SQLite:     decompress the snapshot over ${DB_PATH:-contracts.db}
#   - PostgreSQL: gunzip | psql "$DATABASE_URL"
#   - Before overwriting a live SQLite DB, a *.pre-restore safety copy is made.
#   - Refuses to run non-interactively without --yes (prevents accidents).
#   - R2 mode is FAIL-CLOSED: any download / gzip / integrity failure exits 1.
#   - Credentials are read from the environment ONLY and are never logged.
#
# Env overrides mirror backup_db.sh:
#   RECOMPETE_BACKUP_DIR  (default: /var/backups/recompete)
#   DB_PATH               (default: contracts.db)
#   DATABASE_URL          (presence selects PostgreSQL)
#   R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET   (R2 mode)
#   R2_REGION             (default: auto)
#   R2_CLI                (default: aws)

set -euo pipefail

BACKUP_DIR="${RECOMPETE_BACKUP_DIR:-/var/backups/recompete}"

log() { printf '[restore_db] %s\n' "$*"; }
fail() { log "ERROR: $*"; exit 1; }

# ── Cloudflare R2 (S3-compatible) helpers — credentials via env only ──────────
r2_require() {
    local missing=()
    [ -n "${R2_ENDPOINT:-}" ]          || missing+=("R2_ENDPOINT")
    [ -n "${R2_ACCESS_KEY_ID:-}" ]     || missing+=("R2_ACCESS_KEY_ID")
    [ -n "${R2_SECRET_ACCESS_KEY:-}" ] || missing+=("R2_SECRET_ACCESS_KEY")
    [ -n "${R2_BUCKET:-}" ]            || missing+=("R2_BUCKET")
    [ "${#missing[@]}" -eq 0 ] || fail "R2 not configured; missing: ${missing[*]}"
    command -v "${R2_CLI:-aws}" >/dev/null 2>&1 || \
        fail "R2 configured but '${R2_CLI:-aws}' CLI not on PATH (install awscli)"
}

r2() {
    AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    AWS_DEFAULT_REGION="${R2_REGION:-auto}" \
    AWS_EC2_METADATA_DISABLED=true \
    "${R2_CLI:-aws}" --endpoint-url "$R2_ENDPOINT" "$@"
}

r2_list_keys() {  # newest first
    r2 s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix backup_ \
        --query 'reverse(sort_by(Contents,&LastModified))[].Key' --output text 2>/dev/null \
        | tr '\t' '\n' | sed '/^$/d;/^None$/d'
}

# Validate a gzipped SQLite snapshot end-to-end. Fail-closed on gzip/integrity
# errors. Args: <archive.gz> [<compare_db>]  (compare_db: optional live DB path).
validate_sqlite_snapshot() {
    local archive="$1" compare="${2:-}"
    gzip -t "$archive" || fail "gzip integrity check failed (corrupt/truncated): $archive"
    command -v python3 >/dev/null 2>&1 || fail "python3 not available for snapshot validation"
    local tmp; tmp="$(mktemp --suffix=.db)"
    if ! gunzip -c "$archive" >"$tmp" 2>/dev/null; then
        rm -f "$tmp"; fail "could not decompress snapshot: $archive"
    fi
    # PRAGMA integrity_check is the hard gate; table list + row counts (and an
    # optional comparison against the live DB) are the sanity report.
    if python3 - "$tmp" "$compare" <<'PY'; then
import os, sqlite3, sys
snap, compare = sys.argv[1], (sys.argv[2] or None)

def summary(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tabs = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {}
        for name in tabs:
            counts[name] = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        return tabs, counts
    finally:
        con.close()

con = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
ic = con.execute("PRAGMA integrity_check;").fetchone()[0]
con.close()
print(f"[validate] PRAGMA integrity_check = {ic}")
if ic != "ok":
    print("[validate] FAIL: integrity_check is not 'ok'", file=sys.stderr)
    sys.exit(2)

stabs, scounts = summary(snap)
print(f"[validate] snapshot: {len(stabs)} tables, {sum(scounts.values())} total rows")
for name in stabs:
    print(f"[validate]   {name}: {scounts[name]} rows")

if compare and os.path.exists(compare):
    ctabs, ccounts = summary(compare)
    missing = sorted(set(ctabs) - set(stabs))
    extra = sorted(set(stabs) - set(ctabs))
    print(f"[validate] live DB {compare}: {len(ctabs)} tables")
    if missing:
        print(f"[validate] WARNING: tables in live but NOT in snapshot: {missing}")
    if extra:
        print(f"[validate] NOTE: tables in snapshot but not in live (newer schema?): {extra}")
    for name in sorted(set(stabs) & set(ctabs)):
        print(f"[validate]   {name}: snapshot={scounts[name]} live={ccounts[name]}")
elif compare:
    print(f"[validate] (no live DB at {compare} to compare against)")
print("[validate] OK")
PY
        rm -f "$tmp"
    else
        rm -f "$tmp"; fail "snapshot validation failed: $archive"
    fi
}

# ── Argument parsing ──────────────────────────────────────────────────────────
assume_yes=0
target=""
do_list=0
do_r2_list=0
from_r2=0
verify_only=0
for arg in "$@"; do
    case "$arg" in
        --list) do_list=1 ;;
        --r2-list) do_r2_list=1 ;;
        --from-r2) from_r2=1 ;;
        --latest) target="" ;;   # explicit "use newest R2 key"
        --verify-only) verify_only=1 ;;
        --yes|-y) assume_yes=1 ;;
        -*) fail "unknown option: $arg" ;;
        *) target="$arg" ;;
    esac
done

list_backups() { ls -1t "$BACKUP_DIR"/backup_*.gz 2>/dev/null || true; }

# ── Mode: list R2 objects ─────────────────────────────────────────────────────
if [ "$do_r2_list" -eq 1 ]; then
    r2_require
    log "R2 backups in bucket '$R2_BUCKET' (newest first):"
    found=0
    while IFS= read -r k; do [ -n "$k" ] && { printf '  %s\n' "$k"; found=1; }; done < <(r2_list_keys)
    [ "$found" -eq 1 ] || log "(none found)"
    exit 0
fi

# ── Mode: list local backups ──────────────────────────────────────────────────
if [ "$do_list" -eq 1 ]; then
    log "Backups in $BACKUP_DIR (newest first):"
    found=0
    while IFS= read -r f; do [ -n "$f" ] && { printf '  %s\n' "$f"; found=1; }; done < <(list_backups)
    [ "$found" -eq 1 ] || log "(none found)"
    exit 0
fi

# ── Mode: download + validate (+ optionally restore) from R2 ──────────────────
if [ "$from_r2" -eq 1 ]; then
    r2_require
    key="$target"
    if [ -z "$key" ]; then
        key="$(r2_list_keys | head -1)"
        [ -n "$key" ] || fail "no backups found in R2 bucket '$R2_BUCKET'"
        log "No key given — selecting latest R2 object: $key"
    fi
    scratch="$(mktemp -d "${TMPDIR:-/tmp}/recompete-r2-restore.XXXXXX")"
    dl="$scratch/$(basename "$key")"
    log "Downloading s3://$R2_BUCKET/$key → $dl"
    r2 s3 cp "s3://$R2_BUCKET/$key" "$dl" --only-show-errors || fail "R2 download failed for $key"

    case "$key" in
        *.db.gz)
            log "Validating downloaded SQLite snapshot (integrity + schema/row sanity)"
            validate_sqlite_snapshot "$dl" "${DB_PATH:-contracts.db}"
            ;;
        *.sql.gz)
            log "PostgreSQL dump detected — verifying gzip layer (integrity_check N/A)"
            gzip -t "$dl" || fail "gzip integrity check failed: $dl"
            ;;
        *)
            fail "unrecognized snapshot type for key: $key"
            ;;
    esac

    if [ "$verify_only" -eq 1 ]; then
        log "verify-only: snapshot downloaded + validated; live database NOT modified."
        log "Downloaded copy left at: $dl"
        exit 0
    fi
    chosen="$dl"
    log "Selected R2 backup for restore: $chosen"
else
    # ── Mode: local restore — resolve which file to restore ───────────────────
    if [ -n "$target" ]; then
        if [ -f "$target" ]; then
            chosen="$target"
        elif [ -f "$BACKUP_DIR/$target" ]; then
            chosen="$BACKUP_DIR/$target"
        else
            fail "backup not found: '$target' (looked in CWD and $BACKUP_DIR)"
        fi
    else
        chosen="$(list_backups | head -1)"
        [ -n "$chosen" ] || fail "no backups found in $BACKUP_DIR"
        log "No file given — selecting latest: $chosen"
    fi
    log "Selected backup: $chosen"
fi

# ── Confirmation guard (shared by local + R2 restore) ─────────────────────────
if [ "$assume_yes" -ne 1 ]; then
    if [ -t 0 ]; then
        read -r -p "Restore this backup over the live database? [y/N] " ans
        case "$ans" in y|Y|yes|YES) ;; *) fail "aborted by user" ;; esac
    else
        fail "refusing to restore non-interactively without --yes"
    fi
fi

if [ -n "${DATABASE_URL:-}" ]; then
    # ---- PostgreSQL ----
    command -v psql >/dev/null 2>&1 || fail "DATABASE_URL set but psql not on PATH"
    log "Restoring into PostgreSQL via psql"
    gunzip -c "$chosen" | psql "$DATABASE_URL" || fail "psql restore failed"
    log "PostgreSQL restore complete."
else
    # ---- SQLite ----
    db="${DB_PATH:-contracts.db}"
    if [ -f "$db" ]; then
        safety="$db.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"
        cp "$db" "$safety" || fail "could not write pre-restore safety copy"
        log "Saved pre-restore safety copy: $safety"
    fi
    log "Restoring SQLite snapshot → $db"
    gunzip -c "$chosen" >"$db" || fail "gunzip/restore failed"
    log "SQLite restore complete."
fi

log "Done."
