#!/usr/bin/env bash
# Integration Gate — must pass before any lane merges into main.
#
# If a merge creates broad structural failures, abort/reset the merge.
# Do not manually patch hundreds of failures inside the integration lane.
#
# Usage:
#   bash scripts/integration_gate.sh [lane-branch]
#
# EXIT CODES
#   0 — all checks passed, safe to merge
#   1 — a check failed; DO NOT merge until resolved
set -euo pipefail

LANE_BRANCH="${1:-}"
WORKTREE_ROOT="$(git rev-parse --show-toplevel)"

# Use project venv if available, otherwise fall back to system python3
VENV_PYTHON="/home/michael/autonomous-engineering/.venv/bin/python3"
if [ -x "${VENV_PYTHON}" ]; then
  PYTHON="${VENV_PYTHON}"
else
  PYTHON="python3"
fi
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; echo -e "${RED}${BOLD}GATE FAILED — DO NOT MERGE${NC}"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${BOLD}[CHECK]${NC} $1"; }
section() { echo ""; echo -e "${BOLD}═══ $1 ═══${NC}"; }

section "Recompete Integration Gate"
echo "  Date:      $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Worktree:  ${WORKTREE_ROOT}"
echo "  Branch:    $(git branch --show-current)"
echo "  Commit:    $(git log -1 --oneline)"
[ -n "${LANE_BRANCH}" ] && echo "  Merging:   ${LANE_BRANCH}"
echo ""

# ── CHECK 1: Print path, branch, status ───────────────────────────────────────
section "1. Git State"
info "Working tree cleanliness"
DIRTY_FILES=$(git status --short)
if [ -n "${DIRTY_FILES}" ]; then
  # Untracked governance files (LANE.md, INTEGRATION_RULES.md, etc.) are allowed
  DIRTY_TRACKED=$(git diff --name-only; git diff --cached --name-only)
  if [ -n "${DIRTY_TRACKED}" ]; then
    fail "Tracked files are modified. Commit or stash before merging:\n${DIRTY_TRACKED}"
  else
    warn "Untracked files present (governance docs) — proceeding"
    echo "${DIRTY_FILES}"
  fi
fi
pass "No dirty tracked files"

# ── CHECK 2: Must be on integration branch ────────────────────────────────────
section "2. Branch Verification"
info "Current branch must be lane/integration or main"
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "${CURRENT_BRANCH}" != "lane/integration" && "${CURRENT_BRANCH}" != "main" ]]; then
  fail "Must run from 'lane/integration' or 'main'. Currently on: ${CURRENT_BRANCH}"
fi
pass "On branch: ${CURRENT_BRANCH}"

# ── CHECK 3: app.py exists and is non-trivial ─────────────────────────────────
section "3. app.py Integrity"
info "app.py present and non-trivial"
cd "${WORKTREE_ROOT}"
if [ ! -f "app.py" ]; then
  fail "app.py is missing — platform structure is broken"
fi
LINE_COUNT=$(wc -l < app.py)
if [ "${LINE_COUNT}" -lt 10 ]; then
  fail "app.py appears truncated (${LINE_COUNT} lines) — possible overwrite corruption"
fi
pass "app.py present (${LINE_COUNT} lines)"

# ── CHECK 4: Exactly one Flask() initialization ───────────────────────────────
section "4. Flask Initialization"
info "Verify exactly one Flask() in app.py; app.config not before Flask()"
${PYTHON} - <<'PY'
from pathlib import Path
import sys

text = Path("app.py").read_text()

flask_init_pos = text.find("app = Flask(")
config_pos = text.find("app.config")

if flask_init_pos == -1:
    print("ERROR: 'app = Flask(' not found in app.py", file=sys.stderr)
    sys.exit(1)

if config_pos != -1 and config_pos < flask_init_pos:
    print(
        f"ERROR: app.config appears at char {config_pos} before app = Flask(...) at char {flask_init_pos}",
        file=sys.stderr,
    )
    sys.exit(1)

count = text.count("Flask(")
print(f"  Flask() call count: {count}")
if count != 1:
    print(f"ERROR: expected exactly 1 Flask() initialization, found {count}", file=sys.stderr)
    sys.exit(1)

print("  Flask init position: OK (before any app.config usage)")
PY
pass "Single Flask() initialization verified; ordering correct"

# ── CHECK 5: No rogue Flask() outside app.py ──────────────────────────────────
# Looks for global-level `app = Flask(` assignments (not local `_app = Flask(`
# inside functions, which are legitimate background-task app context patterns).
section "5. Rogue Flask Check"
info "No global app = Flask() outside app.py"
FLASK_HITS=$(grep -rn "^app = Flask(\|^app=Flask(" --include="*.py" . \
  | grep -v "^./app.py:" \
  | grep -v "__pycache__" \
  | grep -v "\.git" || true)
if [ -n "${FLASK_HITS}" ]; then
  fail "Global 'app = Flask()' found outside app.py — double-init corruption risk:\n${FLASK_HITS}"
fi
# Secondary: warn (not fail) on any non-local Flask() calls outside app.py
SECONDARY_HITS=$(grep -rn "Flask(__name__)\| = Flask(" --include="*.py" . \
  | grep -v "^./app.py:" \
  | grep -v "_app = Flask(" \
  | grep -v "__pycache__" \
  | grep -v "/test_" \
  | grep -v "\.git" || true)
if [ -n "${SECONDARY_HITS}" ]; then
  warn "Non-local Flask() calls found outside app.py (verify these are intentional app_context uses):"
  echo "${SECONDARY_HITS}"
fi
pass "No global app = Flask() outside app.py"

# ── CHECK 6: Core imports and critical functions resolve ──────────────────────
section "6. Core Import Check"
info "app, db, analytics import cleanly; required functions present"
${PYTHON} - <<'PY'
import sys, os
sys.path.insert(0, os.getcwd())

errors = []

try:
    import app as _app
except Exception as e:
    errors.append(f"import app: {e}")

try:
    import db
except Exception as e:
    errors.append(f"import db: {e}")

try:
    import analytics
except Exception as e:
    errors.append(f"import analytics: {e}")

if errors:
    for err in errors:
        print(f"  ERROR: {err}", file=sys.stderr)
    sys.exit(1)

required_db = ["get_contracts"]
for name in required_db:
    if not hasattr(db, name):
        errors.append(f"db.{name} is missing")

if errors:
    for err in errors:
        print(f"  ERROR: {err}", file=sys.stderr)
    sys.exit(1)

print("  app, db, analytics: imported OK")
print(f"  db.get_contracts: present")
PY
pass "Core imports and required functions resolve"

# ── CHECK 7: requirements.txt present ────────────────────────────────────────
section "7. Dependency File"
info "requirements.txt exists"
if [ ! -f "requirements.txt" ]; then
  fail "requirements.txt missing — deployment will fail"
fi
pass "requirements.txt present"

# ── CHECK 8: Run full test suite ──────────────────────────────────────────────
section "8. Test Suite"
info "Running full pytest suite (fail on first error)"
echo ""
if ! ${PYTHON} -m pytest tests/ -x --tb=short -q 2>&1; then
  echo ""
  fail "Test suite failed. Identify the owning lane and return the fix there. DO NOT patch blindly in integration."
fi
pass "All tests passed"

# ── CHECK 9: Lane branch divergence ──────────────────────────────────────────
if [ -n "${LANE_BRANCH}" ]; then
  section "9. Lane Divergence"
  info "Checking ${LANE_BRANCH} against origin/main"
  if git rev-parse --verify "${LANE_BRANCH}" &>/dev/null; then
    BEHIND=$(git rev-list --count "${LANE_BRANCH}..origin/main" 2>/dev/null || echo "unknown")
    if [ "${BEHIND}" = "0" ] || [ "${BEHIND}" = "unknown" ]; then
      pass "Lane branch is current with origin/main"
    else
      warn "${LANE_BRANCH} is ${BEHIND} commits behind origin/main — consider rebasing before merge"
    fi
  else
    warn "Branch '${LANE_BRANCH}' not found locally — skipping divergence check"
  fi
fi

# ── ALL CLEAR ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  INTEGRATION GATE PASSED — SAFE TO MERGE  ${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
[ -n "${LANE_BRANCH}" ] && echo "  Merging: ${LANE_BRANCH} → ${CURRENT_BRANCH}"
echo ""
