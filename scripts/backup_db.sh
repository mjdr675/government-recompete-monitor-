#!/usr/bin/env bash
#
# Database backup for Recompete — HARD SAFETY LAYER (pre-deploy AND daily).
#
# Guarantees a restorable snapshot of the database. In the deploy pipeline it
# runs BEFORE migrations (migrations run at service restart via init_db()):
#
#     1. git reset --hard origin/main   (pull latest code — gives us THIS script)
#     2. bash scripts/backup_db.sh predeploy   (mandatory; deploy STOPS if this fails)
#     3. sudo systemctl restart recompete      (restart → migrations run)
#
# It is equally safe to run on a daily schedule (e.g. Railway cron / systemd
# timer):  bash scripts/backup_db.sh daily
#
# Auto-detects the active database:
#   - PostgreSQL: DATABASE_URL set  → pg_dump | gzip  → *.sql.gz
#   - SQLite:     otherwise         → sqlite3 .backup → *.db.gz
#
# Backup file naming (matches the agreed convention):
#   backup_<YYYY-MM-DD>_<HHMMSS>_<gitshorthash>[_<label>].(db|sql).gz
#   e.g. backup_2026-06-23_120501_d082cdd_predeploy.db.gz
#
# Backups are written to a PERSISTENT directory OUTSIDE the repo working tree
# (default /var/backups/recompete) so neither `git reset --hard` nor
# `git clean -fd` can ever remove them.
#
# OFF-SITE COPY (Cloudflare R2, S3-compatible):
#   When the R2_* environment variables are present, every successful snapshot
#   is ALSO uploaded to Cloudflare R2 and then re-downloaded and integrity-checked
#   (restore verification) before the backup is considered successful. This is
#   fail-closed: if the upload or its verification fails, the script exits 1 and
#   the deploy aborts. Credentials are read from the environment ONLY and are
#   never logged. Requires the `aws` CLI (awscli) on PATH in the backup env.
#
# Exit status:
#   0  snapshot written (and, if R2 configured, uploaded + verified),
#      OR no database exists yet (genuine fresh install)
#   1  any real failure → caller MUST abort the deploy (no skipping allowed)
#
# Env overrides:
#   RECOMPETE_BACKUP_DIR      local destination dir  (default: /var/backups/recompete)
#   RECOMPETE_BACKUP_RETAIN   local copies to keep   (default: 15, count-based)
#   RECOMPETE_R2_RETAIN_DAYS  R2 age retention days   (default: 14)
#   DB_PATH                   SQLite path            (default: contracts.db)
#   DATABASE_URL              Postgres DSN           (presence selects Postgres)
#   R2_ENDPOINT               Cloudflare R2 S3 endpoint URL   } all four required
#   R2_ACCESS_KEY_ID          R2 access key id                } to enable the
#   R2_SECRET_ACCESS_KEY      R2 secret access key            } off-site upload
#   R2_BUCKET                 R2 bucket name                  }
#   R2_REGION                 S3 region label        (default: auto)
#   R2_CLI                    S3 client binary       (default: aws)
#
# Args:
#   [label]                   optional label (e.g. predeploy / daily), sanitized
#                             into the filename

set -euo pipefail

BACKUP_DIR="${RECOMPETE_BACKUP_DIR:-/var/backups/recompete}"
RETAIN="${RECOMPETE_BACKUP_RETAIN:-15}"
R2_RETAIN_DAYS="${RECOMPETE_R2_RETAIN_DAYS:-14}"
LABEL_RAW="${1:-${RECOMPETE_MIGRATION_LABEL:-}}"

log() { printf '[backup_db] %s\n' "$*"; }
fail() { log "ERROR: $*"; exit 1; }

# A backup is "successful" ONLY if it is proven restorable. Args: <archive> <engine>
#   - gzip -t              : archive is not truncated/corrupt at the compression layer
#   - SQLite: PRAGMA integrity_check on the decompressed copy must return exactly "ok"
#   - Postgres: gzip -t + the pg_dump pipe already gated by `set -o pipefail`
# Any failure → exit 1, which the deploy's `set -e` turns into a hard stop.
verify_backup() {
    local archive="$1" engine="$2"
    gzip -t "$archive" || fail "gzip integrity check failed (corrupt/truncated archive): $archive"
    if [ "$engine" = "sqlite" ]; then
        if command -v sqlite3 >/dev/null 2>&1; then
            local tmp ic
            tmp="$(mktemp)"
            if ! gunzip -c "$archive" >"$tmp" 2>/dev/null; then
                rm -f "$tmp"; fail "could not decompress for verification: $archive"
            fi
            ic="$(sqlite3 "$tmp" 'PRAGMA integrity_check;' 2>/dev/null | head -n1 || true)"
            rm -f "$tmp"
            [ "$ic" = "ok" ] || fail "SQLite integrity_check failed (got: '${ic:-<empty>}'): $archive"
            log "Integrity verified: gzip OK + PRAGMA integrity_check=ok"
        else
            log "WARNING: sqlite3 unavailable — verified gzip layer only (no integrity_check)"
        fi
    else
        log "Integrity verified: gzip OK + pg_dump pipe exit (pipefail)"
    fi
}

# ── Cloudflare R2 (S3-compatible) off-site helpers ────────────────────────────
# All credentials are read from the environment and are NEVER printed.

# "In play" if ANY R2_* var is set. Full validation happens in r2_require so a
# partial/typo'd config fails closed rather than silently skipping the off-site copy.
r2_enabled() {
    [ -n "${R2_ENDPOINT:-}" ] || [ -n "${R2_ACCESS_KEY_ID:-}" ] || \
        [ -n "${R2_SECRET_ACCESS_KEY:-}" ] || [ -n "${R2_BUCKET:-}" ]
}

r2_require() {
    local missing=()
    [ -n "${R2_ENDPOINT:-}" ]          || missing+=("R2_ENDPOINT")
    [ -n "${R2_ACCESS_KEY_ID:-}" ]     || missing+=("R2_ACCESS_KEY_ID")
    [ -n "${R2_SECRET_ACCESS_KEY:-}" ] || missing+=("R2_SECRET_ACCESS_KEY")
    [ -n "${R2_BUCKET:-}" ]            || missing+=("R2_BUCKET")
    [ "${#missing[@]}" -eq 0 ] || fail "R2 partially configured; missing: ${missing[*]} (set all four or none)"
    command -v "${R2_CLI:-aws}" >/dev/null 2>&1 || \
        fail "R2 configured but '${R2_CLI:-aws}' CLI not on PATH (install awscli in the backup environment)"
}

# aws wrapper: credentials passed via env only; R2 uses region "auto".
r2() {
    AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    AWS_DEFAULT_REGION="${R2_REGION:-auto}" \
    AWS_EC2_METADATA_DISABLED=true \
    "${R2_CLI:-aws}" --endpoint-url "$R2_ENDPOINT" "$@"
}

# Upload the archive, then re-download it and prove it is restorable before
# treating the off-site copy as successful. Fail-closed on any error.
r2_upload_verified() {
    local archive="$1" engine="$2" key dl
    key="$(basename "$archive")"
    log "R2 upload → s3://$R2_BUCKET/$key"
    r2 s3 cp "$archive" "s3://$R2_BUCKET/$key" --only-show-errors \
        || fail "R2 upload failed for $key"
    # Restore verification: pull the object back and check it end-to-end so a
    # silently corrupted/truncated upload can never count as a good backup.
    dl="$(mktemp)"
    if ! r2 s3 cp "s3://$R2_BUCKET/$key" "$dl" --only-show-errors; then
        rm -f "$dl"; fail "R2 re-download failed for $key (cannot verify upload)"
    fi
    if ! cmp -s "$archive" "$dl"; then
        rm -f "$dl"; fail "R2 object differs from local archive (corrupt upload): $key"
    fi
    verify_backup "$dl" "$engine"   # gzip -t (+ PRAGMA integrity_check when sqlite3 present)
    rm -f "$dl"
    log "R2 upload verified (byte-identical re-download + integrity check): $key"
}

# Age-based retention on R2: delete snapshots older than R2_RETAIN_DAYS.
# Best-effort — a prune failure never aborts a deploy (the backup already succeeded),
# mirroring the local count-based rotation below.
r2_retention() {
    local cutoff keys k
    cutoff="$(date -u -d "-${R2_RETAIN_DAYS} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
    if [ -z "$cutoff" ]; then
        log "WARNING: could not compute R2 retention cutoff — skipping R2 prune"; return 0
    fi
    log "R2 retention: pruning objects older than ${R2_RETAIN_DAYS}d (before $cutoff)"
    keys="$(r2 s3api list-objects-v2 --bucket "$R2_BUCKET" --prefix backup_ \
            --query "Contents[?LastModified<'$cutoff'].Key" --output text 2>/dev/null || true)"
    if [ -z "$keys" ] || [ "$keys" = "None" ]; then
        log "R2 retention: nothing to prune"; return 0
    fi
    for k in $keys; do
        log "R2 retention: removing s3://$R2_BUCKET/$k"
        r2 s3 rm "s3://$R2_BUCKET/$k" --only-show-errors \
            || log "WARNING: failed to remove R2 object $k (continuing)"
    done
}

# Audit marker only (does NOT gate the deploy — set -e gating is unchanged).
write_marker() {
    local sha=""
    command -v sha256sum >/dev/null 2>&1 && sha="$(sha256sum "$1" | awk '{print $1}')"
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${sha:-nohash}" \
        >"$BACKUP_DIR/.last_backup_ok"
    log "Wrote audit marker .last_backup_ok (sha256=${sha:-nohash})"
}

# Timestamp + git hash + optional label → filename stem.
date_part="$(date -u +%Y-%m-%d)"
time_part="$(date -u +%H%M%S)"
git_hash="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
label=""
if [ -n "$LABEL_RAW" ]; then
    # keep only safe characters
    label="_$(printf '%s' "$LABEL_RAW" | tr -c 'A-Za-z0-9._-' '-')"
fi
stem="backup_${date_part}_${time_part}_${git_hash}${label}"

# ---- Fail-closed pre-flight: if R2 vars are present at all, require a complete,
# usable config now (before we spend time snapshotting) so a misconfigured
# off-site target aborts the deploy up front rather than after the backup. ----
if r2_enabled; then
    r2_require
    log "R2 off-site upload ENABLED (bucket=$R2_BUCKET, retain=${R2_RETAIN_DAYS}d)"
else
    log "R2 off-site upload not configured — local backup only."
fi

# Ensure a persistent, writable backup directory (hard requirement).
if ! mkdir -p "$BACKUP_DIR" 2>/dev/null; then
    fail "cannot create backup directory '$BACKUP_DIR' (need write permission / sudo)"
fi
if [ ! -w "$BACKUP_DIR" ]; then
    fail "backup directory '$BACKUP_DIR' is not writable by $(id -un)"
fi

if [ -n "${DATABASE_URL:-}" ]; then
    # ---- PostgreSQL ----
    command -v pg_dump >/dev/null 2>&1 || fail "DATABASE_URL set but pg_dump not on PATH"
    out="$BACKUP_DIR/$stem.sql.gz"
    engine="pg"
    log "Backing up PostgreSQL → $out"
    pg_dump "$DATABASE_URL" | gzip >"$out" || fail "pg_dump failed"
    log "PostgreSQL backup complete ($(du -h "$out" | cut -f1))"
else
    # ---- SQLite ----
    db="${DB_PATH:-contracts.db}"
    if [ ! -f "$db" ]; then
        log "No SQLite database at '$db' — nothing to back up (fresh install)."
        exit 0
    fi
    raw="$BACKUP_DIR/$stem.db"
    log "Backing up SQLite '$db' → $raw.gz"
    if command -v sqlite3 >/dev/null 2>&1; then
        # Online-consistent backup even if the app is mid-write.
        sqlite3 "$db" ".backup '$raw'" || fail "sqlite3 .backup failed"
    else
        cp "$db" "$raw" || fail "cp of SQLite db failed"
    fi
    gzip "$raw" || fail "gzip failed"
    out="$raw.gz"
    engine="sqlite"
    log "SQLite backup complete ($(du -h "$out" | cut -f1))"
fi

# ---- A backup counts as successful ONLY after integrity validation passes ----
verify_backup "$out" "$engine"
write_marker "$out"

# ---- Off-site copy to Cloudflare R2 (fail-closed: upload + restore-verify) ----
if r2_enabled; then
    r2_upload_verified "$out" "$engine"
    r2_retention
fi

# ---- Local rotation: keep newest $RETAIN, prune the rest (best-effort) ----
log "Pruning $BACKUP_DIR (retain $RETAIN)"
mapfile -t backups < <(ls -1t "$BACKUP_DIR"/backup_*.gz 2>/dev/null || true)
if [ "${#backups[@]}" -gt "$RETAIN" ]; then
    for old in "${backups[@]:$RETAIN}"; do
        log "Removing old backup: $old"
        rm -f "$old"
    done
fi

log "Done: $out"
