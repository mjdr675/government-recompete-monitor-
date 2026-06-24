#!/usr/bin/env bash
# clean_test_tmp.sh — Remove known-safe pytest/CI temp artifacts.
# Run this when /tmp fills and causes sqlite3 disk I/O errors during the gate.
#
# Safe to delete:
#   /tmp/pytest-of-michael, /tmp/pw_runner, /tmp/recompete-test, etc.
#   __pycache__, .pytest_cache, .mypy_cache under the worktree
#
# Never deletes:
#   .git, .env, databases, CSV source data, worktrees, source code
#
# Usage:
#   bash scripts/clean_test_tmp.sh          # live run
#   bash scripts/clean_test_tmp.sh --dry-run
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  echo "[DRY-RUN] No files will be deleted."
fi

removed=0

remove() {
  local target="$1"
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "  [dry-run] would remove: $target"
    else
      rm -rf -- "$target"
      echo "  removed: $target"
    fi
    removed=$((removed+1))
  fi
}

echo "=== clean_test_tmp.sh ==="
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ── /tmp artifacts ─────────────────────────────────────────────────────────────
echo "--- /tmp artifacts ---"
remove /tmp/pytest-of-michael
remove /tmp/pw_runner
remove /tmp/recompete-test
remove /tmp/recompete_screenshots
remove /tmp/recompete_sprint2
remove /tmp/sprint3_screenshots
remove /tmp/claude-1000

# ── Per-worktree caches ────────────────────────────────────────────────────────
echo ""
echo "--- worktree caches ---"
WORKTREE_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -n "$WORKTREE_ROOT" ]; then
  # Remove __pycache__ directories
  while IFS= read -r d; do
    remove "$d"
  done < <(find "$WORKTREE_ROOT" -type d -name "__pycache__" \
    ! -path "*/.git/*" ! -path "*/node_modules/*" 2>/dev/null || true)

  for cache_dir in .pytest_cache .mypy_cache .ruff_cache htmlcov; do
    remove "$WORKTREE_ROOT/$cache_dir"
  done

  for coverage_file in .coverage coverage.xml; do
    remove "$WORKTREE_ROOT/$coverage_file"
  done
fi

echo ""
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete. $removed path(s) would be removed."
else
  echo "Done. $removed path(s) removed."
fi
