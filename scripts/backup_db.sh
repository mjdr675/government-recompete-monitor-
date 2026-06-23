#!/usr/bin/env bash
#
# Pre-deploy database backup for Recompete — HARD SAFETY LAYER.
#
# Guarantees that every deploy is preceded by a restorable snapshot of the
# database BEFORE migrations run (migrations run at service restart via
# init_db()). Intended call order in the deploy pipeline:
#
#     1. git reset --hard origin/main   (pull latest code — gives us THIS script)
#     2. bash scripts/backup_db.sh      (mandatory; deploy STOPS if this fails)
#     3. sudo systemctl restart recompete   (restart → migrations run)
#
# Auto-detects the active database:
#   - PostgreSQL: DATABASE_URL set  → pg_dump | gzip  → *.sql.gz
#   - SQLite:     otherwise         → sqlite3 .backup → *.db.gz
#
# Backup file naming (matches the agreed convention):
#   backup_<YYYY-MM-DD>_<HHMMSS>_<gitshorthash>[_<label>].(db|sql).gz
#   e.g. backup_2026-06-23_120501_d082cdd.db.gz
#
# Backups are written to a PERSISTENT directory OUTSIDE the repo working tree
# (default /var/backups/recompete) so neither `git reset --hard` nor
# `git clean -fd` can ever remove them.
#
# Exit status:
#   0  snapshot written, OR no database exists yet (genuine fresh install)
#   1  any real failure → caller MUST abort the deploy (no skipping allowed)
#
# Env overrides:
#   RECOMPETE_BACKUP_DIR      destination dir   (default: /var/backups/recompete)
#   RECOMPETE_BACKUP_RETAIN   how many to keep  (default: 15)
#   DB_PATH                   SQLite path       (default: contracts.db)
#   DATABASE_URL              Postgres DSN      (presence selects Postgres)
#
# Args:
#   [label]                   optional migration label, sanitized into the name

set -euo pipefail

BACKUP_DIR="${RECOMPETE_BACKUP_DIR:-/var/backups/recompete}"
RETAIN="${RECOMPETE_BACKUP_RETAIN:-15}"
LABEL_RAW="${1:-${RECOMPETE_MIGRATION_LABEL:-}}"

log() { printf '[backup_db] %s\n' "$*"; }
fail() { log "ERROR: $*"; exit 1; }

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
    log "SQLite backup complete ($(du -h "$out" | cut -f1))"
fi

# ---- Rotation: keep newest $RETAIN, prune the rest ----
log "Pruning $BACKUP_DIR (retain $RETAIN)"
mapfile -t backups < <(ls -1t "$BACKUP_DIR"/backup_*.gz 2>/dev/null || true)
if [ "${#backups[@]}" -gt "$RETAIN" ]; then
    for old in "${backups[@]:$RETAIN}"; do
        log "Removing old backup: $old"
        rm -f "$old"
    done
fi

log "Done: $out"
