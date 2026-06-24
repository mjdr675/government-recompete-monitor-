#!/usr/bin/env bash
# check_lanes.sh — Verify all 8 canonical worktrees are present and on correct branches.
# Exit 0 if all checks pass. Exit 1 on any required failure.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

pass()    { echo -e "${GREEN}[PASS]${NC} $1"; }
fail()    { echo -e "${RED}[FAIL]${NC} $1"; FAILURES=$((FAILURES+1)); }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
section() { echo ""; echo -e "${BOLD}═══ $1 ═══${NC}"; }

FAILURES=0

declare -A LANE_BRANCHES=(
  ["/home/michael/recompete-worktrees/integration"]="lane/integration"
  ["/home/michael/recompete-worktrees/data-pipeline"]="lane/data-pipeline"
  ["/home/michael/recompete-worktrees/search"]="lane/search"
  ["/home/michael/recompete-worktrees/customer-workspace"]="lane/customer-workspace"
  ["/home/michael/recompete-worktrees/platform"]="lane/platform"
  ["/home/michael/recompete-worktrees/contract-intel"]="lane/contract-intel"
  ["/home/michael/recompete-worktrees/ui-polish"]="lane/ui-polish"
  ["/home/michael/recompete-worktrees/bugfix"]="lane/bugfix"
)

section "Recompete Lane System Check"
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ── CHECK 1: Worktree presence, branch, cleanliness, LANE.md ─────────────────
section "1. Canonical Worktrees"

for wt in \
  "/home/michael/recompete-worktrees/integration" \
  "/home/michael/recompete-worktrees/data-pipeline" \
  "/home/michael/recompete-worktrees/search" \
  "/home/michael/recompete-worktrees/customer-workspace" \
  "/home/michael/recompete-worktrees/platform" \
  "/home/michael/recompete-worktrees/contract-intel" \
  "/home/michael/recompete-worktrees/ui-polish" \
  "/home/michael/recompete-worktrees/bugfix"
do
  expected_branch="${LANE_BRANCHES[$wt]}"
  echo ""
  echo -e "${BOLD}  $wt${NC}"

  if [ ! -d "$wt" ]; then
    fail "  Worktree directory missing: $wt"
    continue
  fi

  actual_branch="$(git -C "$wt" branch --show-current 2>/dev/null || echo 'DETACHED')"
  if [ "$actual_branch" = "$expected_branch" ]; then
    pass "  Branch: $actual_branch"
  else
    fail "  Branch: got '$actual_branch', expected '$expected_branch'"
  fi

  dirty_tracked="$(git -C "$wt" diff --name-only; git -C "$wt" diff --cached --name-only)"
  if [ -n "$dirty_tracked" ]; then
    warn "  Dirty tracked files:"
    echo "$dirty_tracked" | sed 's/^/    /'
  else
    pass "  No dirty tracked files"
  fi

  if [ -f "$wt/LANE.md" ]; then
    pass "  LANE.md present"
  else
    fail "  LANE.md missing"
  fi

  status_short="$(git -C "$wt" status -sb 2>/dev/null | head -1)"
  echo "  Status: $status_short"
done

# ── CHECK 2: Integration governance files ─────────────────────────────────────
section "2. Integration Governance Files"
INTEGRATION="/home/michael/recompete-worktrees/integration"

for f in \
  "scripts/integration_gate.sh" \
  "scripts/check_lanes.sh" \
  "scripts/clean_test_tmp.sh" \
  "INTEGRATION_RULES.md" \
  "LEGACY_WORKTREES_REPORT.md" \
  "WORKTREE_LANE_SYSTEM.md" \
  "LANE.md"
do
  if [ -f "$INTEGRATION/$f" ]; then
    if [ -x "$INTEGRATION/$f" ] 2>/dev/null; then
      pass "$f (executable)"
    else
      pass "$f"
    fi
  else
    fail "$f MISSING from integration worktree"
  fi
done

if [ -x "$INTEGRATION/scripts/integration_gate.sh" ]; then
  pass "integration_gate.sh is executable"
else
  fail "integration_gate.sh is NOT executable"
fi

# ── RESULT ────────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  ALL LANE CHECKS PASSED                   ${NC}"
  echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}═══════════════════════════════════════════${NC}"
  echo -e "${RED}${BOLD}  $FAILURES CHECK(S) FAILED                 ${NC}"
  echo -e "${RED}${BOLD}═══════════════════════════════════════════${NC}"
  exit 1
fi
