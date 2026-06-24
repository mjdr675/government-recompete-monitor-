# Lane: Integration Gate

**Branch:** `lane/integration` → target: `main`
**Worktree:** `/home/michael/recompete-worktrees/integration`

## Role

Merge authority only. This lane compiles completed lane work into `main`. It does not build, fix, or patch features. When it encounters failures, it stops and reports — it does not debug other lanes' code.

## Owns

- Merge sequencing: deciding the order lanes are integrated
- Conflict classification: identifying which lane owns a conflict before resolving it
- Validation: running `scripts/integration_gate.sh` before every merge
- Final merge readiness reports: documenting what passed, what was deferred
- Maintaining `INTEGRATION_RULES.md` and `LEGACY_WORKTREES_REPORT.md`

## Forbidden

- Building features of any kind
- Patching large test failures manually (→ return to owning lane)
- Force pushing without explicit user approval and a written list of overwritten commits
- Accepting a stale remote rewrite without reporting it first
- Merging when the gate fails — STOP and report instead

## Critical Rule: Large Failure Protocol

If a merge creates broad structural failures (missing imports, broken `app.py`, route collapse, 50+ test failures):

1. **STOP** — do not patch blindly
2. Run `git merge --abort` or `git reset --hard HEAD` to restore pre-merge state
3. Report the failure and which lane introduced it
4. Ask for direction before retrying

## Process

```bash
cd /home/michael/recompete-worktrees/integration

# Before merging any lane
bash scripts/integration_gate.sh lane/<target>

# Only if gate passes
git merge --no-ff lane/<target>

# If gate fails broadly
git merge --abort   # or git reset --hard HEAD if already committed
```

## Dependencies

All other lanes. Must not create cross-lane dependencies during conflict resolution.
