#!/usr/bin/env bash
# Rollback for scripts/phase6-setup.sh.
#
# Removes ONLY the Phase 6 systemd drop-in that adds the Discord reboot
# notification, then reloads systemd. It deliberately does NOT uninstall uv —
# uv is a generally useful tool with no side effects on the workstation, and
# removing it is not reversible in the "undo Phase 6" sense. If you really want
# uv gone, delete ~/.local/bin/uv ~/.local/bin/uvx manually.
#
# Run this ON THE VPS as user `michael`.
#
# Usage:
#   scripts/phase6-rollback.sh            # remove drop-in + daemon-reload
#   scripts/phase6-rollback.sh --dry-run  # show what would be removed
set -euo pipefail

SERVICE="workstation-start.service"
DROPIN_DIR="$HOME/.config/systemd/user/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/discord-notify.conf"

DRY_RUN=0
case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    "") ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
esac

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓ %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }

say "Phase 6 rollback (dry-run: $([[ $DRY_RUN == 1 ]] && echo yes || echo no))"

if [[ ! -f "$DROPIN_FILE" ]]; then
    ok "no Phase 6 drop-in found at ${DROPIN_FILE} — nothing to undo"
    exit 0
fi

if [[ "$DRY_RUN" == 1 ]]; then
    info "[dry-run] would remove: ${DROPIN_FILE}"
    info "[dry-run] would remove dir if empty: ${DROPIN_DIR}"
    info "[dry-run] would run: systemctl --user daemon-reload"
    exit 0
fi

rm -f "$DROPIN_FILE"
ok "removed ${DROPIN_FILE}"
rmdir "$DROPIN_DIR" 2>/dev/null && ok "removed empty ${DROPIN_DIR}" || true
systemctl --user daemon-reload
ok "reloaded systemd --user"

say "Verify"
if systemctl --user cat "$SERVICE" 2>/dev/null | grep -q 'discord-notify\|ae notify'; then
    info "WARNING: an ae-notify ExecStartPost is still present — check for other drop-ins"
else
    ok "no Phase 6 notification remains in ${SERVICE}"
fi

say "Rollback complete"
info "Note: uv was intentionally left installed (see header)."
