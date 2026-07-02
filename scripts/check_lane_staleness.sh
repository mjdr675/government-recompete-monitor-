#!/usr/bin/env bash
# Flags any lane/* branch that has drifted too far behind origin/main.
#
# Why: lanes that sit stale for too long silently re-diverge from fixes that
# land on main via other lanes — the same regression gets "fixed" upstream
# and then reintroduced when the stale lane finally merges. Catching this
# early (via cron/CI) is cheaper than discovering it during a big rebase.
#
# Usage:
#   scripts/check_lane_staleness.sh [threshold]
#   THRESHOLD=20 scripts/check_lane_staleness.sh
#
# threshold defaults to 15 commits behind origin/main.
# Exit code: 0 if all lanes are within threshold, 1 if any lane exceeds it.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

THRESHOLD="${1:-${THRESHOLD:-15}}"

git fetch origin main --quiet

exceeded=0
printf "%-24s %-10s %-8s %-8s\n" "LANE" "HEAD" "BEHIND" "AHEAD"
printf "%-24s %-10s %-8s %-8s\n" "----" "----" "------" "-----"

for branch in $(git for-each-ref --format='%(refname:short)' refs/heads/lane/); do
    behind=$(git rev-list --count "${branch}..origin/main")
    ahead=$(git rev-list --count "origin/main..${branch}")
    head_sha=$(git rev-parse --short "${branch}")
    flag=""
    if [ "${behind}" -gt "${THRESHOLD}" ]; then
        flag=" <-- STALE (>${THRESHOLD} behind)"
        exceeded=1
    fi
    printf "%-24s %-10s %-8s %-8s%s\n" "${branch}" "${head_sha}" "${behind}" "${ahead}" "${flag}"
done

exit "${exceeded}"
