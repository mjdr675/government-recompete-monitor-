#!/usr/bin/env bash
# Thin wrapper around `ae notify` for Recompete.us work.
#
# Activates the AE venv, changes to the repo root so that `ae notify`
# auto-detects the correct commit hash, and injects branch + repo label.
# All other arguments are passed through unchanged.
#
# Usage (same as `ae notify`, with --branch auto-filled):
#   scripts/notify.sh session-started --task P-02 --title "Add search"
#   scripts/notify.sh task-done --task P-02 --tests "87/87 passing"
#   scripts/notify.sh task-failed --task P-02 --stage Testing --error "pytest exit 1"
#   scripts/notify.sh test
#
# Requires: AE_DISCORD_WEBHOOK_URL set in environment (never printed here).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AE_VENV="/home/michael/autonomous-engineering/.venv"

if [[ ! -x "$AE_VENV/bin/ae" ]]; then
    echo "ERROR: ae not found at $AE_VENV/bin/ae" >&2
    echo "       Make sure the autonomous-engineering venv is installed." >&2
    exit 1
fi

BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")

# shellcheck source=/dev/null
source "$AE_VENV/bin/activate"

cd "$REPO_ROOT"

# --branch comes first so callers can override it with their own --branch flag.
# --summary is multiple=True in ae notify so this appends rather than replaces.
exec ae notify --branch "$BRANCH" --summary "Repo: Recompete.us" "$@"
