# Lane: Bugfix

**Branch:** `lane/bugfix`
**Worktree:** `/home/michael/recompete-worktrees/bugfix`

## Role

Emergency hotfix staging. Exists to isolate and patch production regressions without disrupting in-flight lane work. Every fix must be small, targeted, and immediately mergeable through the integration gate.

## Owns

- Isolated regression fixes for production failures
- One bug per branch/commit — no bundling
- Failing test repair when the root cause is a clear, contained defect
- Emergency patches with documented removal or follow-up path

## Forbidden

- Building new features (→ appropriate feature lane)
- Refactoring architecture or restructuring files (→ owning lane)
- Mixing unrelated fixes in a single commit
- Changing lane ownership rules or LANE.md files (→ integration lane)
- Schema changes (→ `lane/platform`)
- Fixes requiring coordination across 2+ lanes — escalate to the owning lane instead

## Rules

- State the owning lane in every commit message: `fix(<lane>): description`
- Every fix must have a test or a written explanation of why one is not feasible
- If a fix requires changes to more than 3 files, it belongs in the owning lane — stop and escalate
- After merge, the owning lane must absorb the fix before continuing feature work

## Related Rules

See `.claude/rules/` in the repo root (imported by root `CLAUDE.md`) for the
full operating rules this lane must follow:
- `.claude/rules/testing.md` — every fix needs a test or a written reason one isn't feasible
- `.claude/rules/git-workflow.md` — lane ownership, no force push, handoff receipt format

## Process

```bash
# Always branch from origin/main, not an in-flight lane
git checkout -b bugfix/<short-description> origin/main

# After fix, merge via integration gate — same process as all lanes
```
