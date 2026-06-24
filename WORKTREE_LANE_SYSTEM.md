# Recompete Worktree Lane System

## Why This System Exists

Multiple Claude agents work on Recompete.us simultaneously. Without isolation, agents
overwrite each other's changes, corrupt test state, and create untraceable merge conflicts.
The lane system gives each agent a dedicated git worktree and branch so work is parallel
but never colliding. Integration Gate is the single chokepoint that validates all work
before it reaches `origin/main`.

---

## Lane Map

| Lane                  | Branch                    | Worktree                                               | Owns                                                   |
| --------------------- | ------------------------- | ------------------------------------------------------ | ------------------------------------------------------ |
| Integration Gate      | `lane/integration`        | `/home/michael/recompete-worktrees/integration`        | merges, validation, gate                               |
| Data Pipeline         | `lane/data-pipeline`      | `/home/michael/recompete-worktrees/data-pipeline`      | ingestion, enrichment, cron, Celery                    |
| Search                | `lane/search`             | `/home/michael/recompete-worktrees/search`             | fuzzy search, filters, discovery ranking               |
| Customer Workspace    | `lane/customer-workspace` | `/home/michael/recompete-worktrees/customer-workspace` | company profile, onboarding, dashboard personalization |
| Platform              | `lane/platform`           | `/home/michael/recompete-worktrees/platform`           | Flask skeleton, DB, migrations, auth, deployment       |
| Contract Intelligence | `lane/contract-intel`     | `/home/michael/recompete-worktrees/contract-intel`     | scoring, comparison, summaries                         |
| UI/Product            | `lane/ui-polish`          | `/home/michael/recompete-worktrees/ui-polish`          | branding, templates, pricing, visual polish            |
| Bugfix                | `lane/bugfix`             | `/home/michael/recompete-worktrees/bugfix`             | isolated regressions                                   |

---

## Rules Every Agent Must Follow

### 1. One chat/agent per worktree
Never work in two worktrees from the same chat. Each chat owns exactly one worktree.
If you are not sure which worktree you own, read your `LANE.md`.

### 2. Integration Gate is the only merge authority
No lane branch may be merged to `origin/main` directly. All merges go through
`lane/integration` via cherry-pick, followed by:

```bash
bash /home/michael/recompete-worktrees/integration/scripts/integration_gate.sh <lane-branch>
```

The gate must print `INTEGRATION GATE PASSED` before any push to `origin/main`.

### 3. No force push without explicit user approval
Never run `git push --force`, `git push --force-with-lease`, or `git reset --hard`
against a remote ref without the user typing the exact command in the chat.

### 4. Do not work in legacy worktrees
The following are legacy or experimental worktrees and must not be used unless
explicitly assigned in the current chat:

```
/home/michael/recompete-*          (all except the canonical 8 below)
/home/michael/government-recompete-monitor-
/home/michael/integration-clean-wt
/home/michael/prune-wt
```

Canonical worktrees are under `/home/michael/recompete-worktrees/` only.

### 5. Read governance docs before starting any work
Every agent in every reset chat must run this before touching any file:

```bash
cd /home/michael/recompete-worktrees/<assigned-lane>
cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
cat LANE.md
git status -sb
```

### 6. Do not commit `ai_agent/REVIEW.md`
The file `ai_agent/REVIEW.md` is written by test infrastructure and contains only a
timestamp. It appears as `M ai_agent/REVIEW.md` after any `pytest` run.
**Never stage or commit it.** Restore it with:

```bash
git checkout -- ai_agent/REVIEW.md
```

### 7. If /tmp fills, run the cleanup script
The pytest suite creates thousands of temp files under `/tmp/pytest-of-michael`.
After a long gate run, `/tmp` can fill and cause `sqlite3.OperationalError: disk I/O error`
at setup time. This is a transient infrastructure failure, not a code bug. Clear it with:

```bash
bash /home/michael/recompete-worktrees/integration/scripts/clean_test_tmp.sh
```

Then re-run the gate. Do not route a disk I/O error to a lane for fixing.

### 8. If the gate fails, classify and route — do not patch in Integration
When the gate's test suite fails:

1. Run the failing test in isolation on `lane/bugfix` (which tracks `origin/main`) to
   determine if it is pre-existing.
2. If pre-existing: identify the owning lane from the test file name and route a fix
   request there. Do not touch Integration.
3. If introduced by the cherry-pick: revert the cherry-pick (`git cherry-pick --abort`
   or `git revert`) and return the commit to its source lane for repair.

Never patch unrelated test failures inside `lane/integration`.

---

## Integration Gate Checks (summary)

The gate at `scripts/integration_gate.sh` runs 9 checks in order:

1. No dirty tracked files
2. Current branch is `lane/integration` or `main`
3. `app.py` present and non-trivial (≥ 10 lines)
4. Exactly one `Flask()` init in `app.py`; no `app.config` before it
5. No global `app = Flask()` outside `app.py`
6. `app`, `db`, `analytics` import cleanly; `db.get_contracts` present
7. `requirements.txt` present
8. Full pytest suite passes (`pytest tests/ -x --tb=short -q`)
9. Lane branch divergence check against `origin/main`

---

## Verifying the System

To verify all 8 worktrees are healthy:

```bash
bash /home/michael/recompete-worktrees/integration/scripts/check_lanes.sh
```

To run the full integration gate:

```bash
cd /home/michael/recompete-worktrees/integration
bash scripts/integration_gate.sh
```
