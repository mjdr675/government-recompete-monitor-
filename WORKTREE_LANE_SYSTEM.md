# Recompete Worktree Lane System

## Why This System Exists

Multiple Claude agents work on Recompete.us simultaneously. Without isolation, agents
overwrite each other's changes, corrupt test state, and create untraceable merge conflicts.
The lane system gives each agent a dedicated git worktree and branch so work is parallel
but never colliding. Integration Gate is the single chokepoint that validates all work
before it reaches `origin/main`.

---

## Canonical Worktrees

| Lane                  | Branch                    | Worktree                                               | Owns                                                   |
| --------------------- | ------------------------- | ------------------------------------------------------ | ------------------------------------------------------ |
| Integration Gate      | `lane/integration`        | `/home/michael/recompete-worktrees/integration`        | merges, validation, gate, push authority               |
| Data Pipeline         | `lane/data-pipeline`      | `/home/michael/recompete-worktrees/data-pipeline`      | ingestion, enrichment, cron, Celery, `tasks.py`        |
| Search                | `lane/search`             | `/home/michael/recompete-worktrees/search`             | fuzzy search, filters, NL query parsing, discovery     |
| Customer Workspace    | `lane/customer-workspace` | `/home/michael/recompete-worktrees/customer-workspace` | company profile, onboarding, dashboard personalization |
| Platform              | `lane/platform`           | `/home/michael/recompete-worktrees/platform`           | Flask skeleton, DB, migrations, auth, deployment       |
| Contract Intelligence | `lane/contract-intel`     | `/home/michael/recompete-worktrees/contract-intel`     | scoring, comparison, summaries, `contract_summary.py`  |
| UI/Product            | `lane/ui-polish`          | `/home/michael/recompete-worktrees/ui-polish`          | branding, templates, pricing, visual polish            |
| Bugfix                | `lane/bugfix`             | `/home/michael/recompete-worktrees/bugfix`             | isolated regressions, pre-existing test failures       |

---

## Rules Every Agent Must Follow

### 1. One chat/agent per worktree
Never work in two worktrees from the same chat. Each chat owns exactly one worktree.
Read your `LANE.md` first. If you are not in the right directory, stop.

### 2. Integration Gate is the only merge and push authority
No lane branch may be pushed to `origin/main` directly. All work must:
1. Be committed locally on the lane branch
2. Be handed off to Integration with the exact commit hash
3. Be cherry-picked by the Integration Gate agent
4. Pass `bash scripts/integration_gate.sh`
5. Be pushed only with Michael's explicit approval

### 3. No force push — ever
`git push --force`, `git push --force-with-lease`, and `git reset --hard` against remote
refs are forbidden without Michael typing the exact command in chat.

### 4. Integration is the only push authority
Lane agents must not push their branch to `origin/main`. They push only their lane
branch (`git push origin lane/<name>`) if needed for backup — never to `main`.

### 5. Do not work in legacy worktrees
These are legacy or experimental and must not be used unless explicitly assigned:

```
/home/michael/recompete-*   (any path not under /home/michael/recompete-worktrees/)
/home/michael/government-recompete-monitor-
/home/michael/integration-clean-wt
/home/michael/prune-wt
```

### 6. Read governance docs before starting any work
Every agent in every reset chat must run this before touching any file:

```bash
cd /home/michael/recompete-worktrees/<assigned-lane>
cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
cat LANE.md
git status -sb
```

### 7. Do not commit `ai_agent/REVIEW.md`
`ai_agent/REVIEW.md` is written by test infrastructure and contains only a timestamp.
It appears as ` M ai_agent/REVIEW.md` after any `pytest` run. Never stage or commit it.
Restore it with:

```bash
git checkout -- ai_agent/REVIEW.md
```

### 8. `LANE.md` is governance-only
`LANE.md` describes the lane's identity and must not travel inside product commits.
When producing a handoff commit, always check that `LANE.md` is not staged:

```bash
git reset HEAD LANE.md 2>/dev/null || true
```

### 9. Migration numbering
Migrations must not reuse a number already in `origin/main`. Check before committing:

```bash
ls migrations/
```

If `015_foo.sql` already exists on `origin/main`, your new migration must be `016_`.

### 10. If `/tmp` fills, run the cleanup script
The pytest suite creates thousands of temp files. After a long gate run, SQLite can fail
with `disk I/O error`. Clear it with:

```bash
bash /home/michael/recompete-worktrees/integration/scripts/clean_test_tmp.sh
```

Then re-run the gate. Do not route a disk I/O error to a lane for fixing.

### 11. Classify gate failures by owning lane — never patch in Integration
When the gate's test suite fails:

1. Run the failing test in isolation on `lane/bugfix` (at `origin/main`) to confirm it is pre-existing.
2. If pre-existing: route to the owning lane. Do not touch Integration.
3. If introduced by the cherry-pick: abort (`git cherry-pick --abort`) and return the commit to its source lane for repair.

### 12. Batch Integration model
Integration consumes handoff commits one lane at a time. The workflow is:

```
Lane agent → git commit (local) → handoff hash → Integration cherry-pick → gate → push
```

Use `ai_agent/prompts/INTEGRATION_BATCH_AUTOPILOT.md` for batch runs.

---

## Verifying the System

```bash
bash /home/michael/recompete-worktrees/integration/scripts/check_lanes.sh
```

## Running the Full Integration Gate

```bash
cd /home/michael/recompete-worktrees/integration
bash scripts/integration_gate.sh [lane-branch]
```

## First Command Every Reset Chat Must Run

```bash
cd /home/michael/recompete-worktrees/<assigned-lane>
cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
cat LANE.md
git status -sb
```
