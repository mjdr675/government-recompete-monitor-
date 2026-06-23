#!/usr/bin/env bash
# Thin wrapper around `ae notify` for Recompete.us work.
#
# Changes to the repo root so that `ae notify` auto-detects the correct commit
# hash, and injects branch + repo label. All other arguments are passed through
# unchanged.
#
# `ae` is detected through the central tool registry (tools/registry.py) — no
# hardcoded paths, no venv activation. Behaviour is identical in CI, locally,
# and in production; the only difference is whether `ae` is available. When it
# is not, the wrapper degrades gracefully rather than crashing the caller.
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

# --help must always succeed, even when `ae` is missing (so it works as a smoke
# check in CI). Print usage and exit 0 without resolving any tool.
case "${1:-}" in
    -h|--help)
        cat <<'USAGE'
Usage: notify.sh <event> [ae notify options]

Thin wrapper around `ae notify` for Recompete.us. Auto-fills --branch and
injects "Repo: Recompete.us". All arguments pass through to `ae notify`.

Events: session-started | task-done | task-failed | test

Requires AE_DISCORD_WEBHOOK_URL in the environment.
USAGE
        exit 0
        ;;
esac

# An event argument is required — usage error exits non-zero, mirroring ae notify.
if [[ $# -eq 0 ]]; then
    echo "ERROR: missing event argument. Try: notify.sh --help" >&2
    exit 2
fi

cd "$REPO_ROOT"

BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")

# Detect `ae` via the central tool registry. Printing the path (empty when
# missing) gives us both availability and the executable to exec — one source
# of truth.
PYTHON="$(command -v python3 || command -v python || echo python3)"
AE_PATH="$("$PYTHON" -c \
    'from tools import registry; print(registry.get("ae").path or "")' \
    2>/dev/null || true)"

# Degrade gracefully when `ae` is unavailable: warn but don't crash the task.
if [[ -z "$AE_PATH" ]]; then
    echo "WARNING: 'ae' not found on PATH; skipping Discord notification." >&2
    exit 0
fi

# --branch comes first so callers can override it with their own --branch flag.
# --summary is multiple=True in ae notify so this appends rather than replaces.
exec "$AE_PATH" notify --branch "$BRANCH" --summary "Repo: Recompete.us" "$@"
