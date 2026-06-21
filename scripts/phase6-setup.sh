#!/usr/bin/env bash
# Phase 6 workstation setup for gov-recompete-worker (Hetzner VPS).
#
# Run this ON THE VPS as user `michael`. It performs two small, reversible
# changes and verifies each one:
#
#   1. Install uv (Astral's Python package manager), user-local, if missing.
#   2. Wire an `ae notify` Discord reboot notification into the existing
#      workstation-start.service via a systemd *drop-in* override — the
#      original unit file is never edited, so rollback is a single `rm`.
#
# Design goals (per workstation rules):
#   - Small, reversible changes only. Nothing here touches Railway, Cloudflare,
#     DNS, production, databases, or any repository source.
#   - Idempotent: safe to re-run. Existing/correct state is left untouched.
#   - Explain before each change, verify after.
#
# Usage:
#   scripts/phase6-setup.sh              # apply changes, then verify
#   scripts/phase6-setup.sh --dry-run    # print what would happen, change nothing
#   scripts/phase6-setup.sh --test-notify  # also fire one real Discord notification
#
# Rollback:
#   scripts/phase6-rollback.sh
#
# Override paths via env if your layout differs from the documented defaults:
#   AE_VENV   (default: $HOME/autonomous-engineering/.venv)
#   SECRETS_ENV (default: $HOME/.config/secrets/env)
set -euo pipefail

# --- configuration (matches the documented workstation layout) ---------------
AE_VENV="${AE_VENV:-$HOME/autonomous-engineering/.venv}"
SECRETS_ENV="${SECRETS_ENV:-$HOME/.config/secrets/env}"
SERVICE="workstation-start.service"
DROPIN_DIR="$HOME/.config/systemd/user/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/discord-notify.conf"

DRY_RUN=0
TEST_NOTIFY=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --test-notify) TEST_NOTIFY=1 ;;
        -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument: $arg" >&2; exit 2 ;;
    esac
done

# --- helpers -----------------------------------------------------------------
say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    \033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '    \033[33m! %s\033[0m\n' "$*"; }
run()  {
    if [[ "$DRY_RUN" == 1 ]]; then
        printf '    [dry-run] %s\n' "$*"
    else
        eval "$@"
    fi
}

# The ExecStartPost command line, defined once so setup/verify agree.
# Sourced secrets are needed for AE_DISCORD_WEBHOOK_URL; $(hostname) is expanded
# at service-run time, not now.
NOTIFY_CMD="source ${SECRETS_ENV} && ${AE_VENV}/bin/ae notify session-started --task \"REBOOT\" --title \"Workstation recovered — \$(hostname)\""

# --- preflight ---------------------------------------------------------------
say "Phase 6 setup (dry-run: $([[ $DRY_RUN == 1 ]] && echo yes || echo no))"

if [[ ! -x "${AE_VENV}/bin/ae" ]]; then
    warn "ae binary not found at ${AE_VENV}/bin/ae"
    warn "The Discord notification step needs the autonomous-engineering venv."
    warn "Install/activate that venv first, or set AE_VENV to its location."
fi
if [[ ! -f "$SECRETS_ENV" ]]; then
    warn "secrets file not found at ${SECRETS_ENV} (AE_DISCORD_WEBHOOK_URL lives here)"
fi
if ! systemctl --user list-unit-files "$SERVICE" >/dev/null 2>&1; then
    warn "${SERVICE} not registered with systemd --user."
    warn "Phase 3 should have created it. The drop-in will still be written,"
    warn "but it has no effect until that unit exists."
fi

# --- step 1: install uv ------------------------------------------------------
say "Step 1/2: install uv"
if command -v uv >/dev/null 2>&1; then
    ok "uv already installed: $(uv --version 2>/dev/null || echo present) — skipping"
else
    info "uv not found; installing via the official user-local installer."
    info "This writes to ~/.local/bin and ~/.cargo — no system packages, no sudo."
    run "curl -LsSf https://astral.sh/uv/install.sh | sh"
    if [[ "$DRY_RUN" != 1 ]]; then
        if command -v uv >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/uv" ]]; then
            ok "uv installed: $("$HOME/.local/bin/uv" --version 2>/dev/null || uv --version)"
            info "Open a new shell (or 'source ~/.bashrc') to pick up uv on PATH."
        else
            warn "uv install command ran but uv is not on PATH yet — check ~/.local/bin"
        fi
    fi
fi

# --- step 2: systemd drop-in for Discord reboot notification -----------------
say "Step 2/2: wire Discord reboot notification (systemd drop-in)"
info "Target unit : ${SERVICE}"
info "Drop-in file: ${DROPIN_FILE}"
info "Effect      : ExecStartPost fires 'ae notify session-started' on each"
info "              service start (i.e. after a reboot restores your sessions)."

DROPIN_CONTENT="# Phase 6: Discord notification when the workstation recovers after reboot.
# Managed by scripts/phase6-setup.sh — remove with scripts/phase6-rollback.sh.
[Service]
ExecStartPost=/bin/bash -lc '${NOTIFY_CMD}'
"

if [[ -f "$DROPIN_FILE" ]] && [[ "$(cat "$DROPIN_FILE" 2>/dev/null)" == "$DROPIN_CONTENT" ]]; then
    ok "drop-in already present and up to date — skipping"
else
    if [[ -f "$DROPIN_FILE" ]]; then
        info "drop-in exists but differs — updating it"
    fi
    run "mkdir -p '${DROPIN_DIR}'"
    if [[ "$DRY_RUN" == 1 ]]; then
        printf '    [dry-run] write %s:\n' "$DROPIN_FILE"
        printf '%s\n' "$DROPIN_CONTENT" | sed 's/^/        | /'
    else
        printf '%s' "$DROPIN_CONTENT" > "$DROPIN_FILE"
        ok "wrote ${DROPIN_FILE}"
    fi
    run "systemctl --user daemon-reload"
    [[ "$DRY_RUN" == 1 ]] || ok "reloaded systemd --user"
fi

# --- verify ------------------------------------------------------------------
say "Verify"
if [[ "$DRY_RUN" == 1 ]]; then
    info "dry-run: nothing changed, skipping verification"
    exit 0
fi

VERIFY_OK=1
if command -v uv >/dev/null 2>&1 || [[ -x "$HOME/.local/bin/uv" ]]; then
    ok "uv present"
else
    warn "uv not detected on PATH"; VERIFY_OK=0
fi

if systemctl --user cat "$SERVICE" 2>/dev/null | grep -q 'discord-notify\|ExecStartPost.*ae notify'; then
    ok "drop-in is merged into ${SERVICE}:"
    systemctl --user cat "$SERVICE" 2>/dev/null \
        | grep -nE 'ExecStartPost|discord-notify' | sed 's/^/      /' || true
else
    warn "ExecStartPost not visible in 'systemctl --user cat ${SERVICE}'"
    warn "(expected if the unit itself isn't registered yet — see preflight)"
    VERIFY_OK=0
fi

if [[ "$TEST_NOTIFY" == 1 ]]; then
    say "Sending one test Discord notification"
    if [[ -x "${AE_VENV}/bin/ae" && -f "$SECRETS_ENV" ]]; then
        # shellcheck source=/dev/null
        ( source "$SECRETS_ENV" && "${AE_VENV}/bin/ae" notify session-started \
            --task "REBOOT" --title "Phase 6 test — $(hostname)" ) \
            && ok "test notification sent" \
            || warn "test notification failed"
    else
        warn "cannot send test: ae binary or secrets file missing"
    fi
fi

say "Done"
if [[ "$VERIFY_OK" == 1 ]]; then
    ok "Phase 6 applied and verified."
else
    warn "Phase 6 applied with warnings above — review before relying on it."
fi
info "Roll back any time with: scripts/phase6-rollback.sh"
