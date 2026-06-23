#!/usr/bin/env bash
#
# Restore a Recompete database backup produced by scripts/backup_db.sh.
#
# Usage:
#   restore_db.sh --list                 List available backups (newest first)
#   restore_db.sh [--yes]                Restore the LATEST backup
#   restore_db.sh [--yes] <file>         Restore a specific backup
#                                        (<file> may be a bare name in the
#                                         backup dir or an absolute path)
#
# Behavior:
#   - SQLite:     decompress the snapshot over ${DB_PATH:-contracts.db}
#   - PostgreSQL: gunzip | psql "$DATABASE_URL"
#   - Before overwriting a live SQLite DB, a *.pre-restore safety copy is made.
#   - Refuses to run non-interactively without --yes (prevents accidents).
#   - Logs every step.
#
# Env overrides mirror backup_db.sh:
#   RECOMPETE_BACKUP_DIR  (default: /var/backups/recompete)
#   DB_PATH               (default: contracts.db)
#   DATABASE_URL          (presence selects PostgreSQL)

set -euo pipefail

BACKUP_DIR="${RECOMPETE_BACKUP_DIR:-/var/backups/recompete}"

log() { printf '[restore_db] %s\n' "$*"; }
fail() { log "ERROR: $*"; exit 1; }

assume_yes=0
target=""
do_list=0
for arg in "$@"; do
    case "$arg" in
        --list) do_list=1 ;;
        --yes|-y) assume_yes=1 ;;
        -*) fail "unknown option: $arg" ;;
        *) target="$arg" ;;
    esac
done

list_backups() { ls -1t "$BACKUP_DIR"/backup_*.gz 2>/dev/null || true; }

if [ "$do_list" -eq 1 ]; then
    log "Backups in $BACKUP_DIR (newest first):"
    found=0
    while IFS= read -r f; do [ -n "$f" ] && { printf '  %s\n' "$f"; found=1; }; done < <(list_backups)
    [ "$found" -eq 1 ] || log "(none found)"
    exit 0
fi

# Resolve which file to restore.
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

# Confirmation guard.
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
