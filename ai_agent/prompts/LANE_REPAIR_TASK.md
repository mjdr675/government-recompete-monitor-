# Lane Repair Task Prompt

Use this prompt when Integration has rejected a lane commit due to a conflict,
migration collision, LANE.md inclusion, or base mismatch. The goal is to produce
a clean replacement commit that Integration can pick without issues.

---

## Prompt Template

```
You are the Recompete <LANE NAME> agent.
Lane: lane/<branch-name>
Worktree: /home/michael/recompete-worktrees/<worktree-name>

## Context

Integration attempted to cherry-pick your commit <ORIGINAL_HASH> and it was rejected.

Rejection reason:
<ONE OF:
  - CONFLICT: cherry-pick conflicted in <file(s)> due to <reason>
  - LANE.md: LANE.md was bundled in the commit and would overwrite integration's governance doc
  - MIGRATION COLLISION: your migrations/<NNN>_foo.sql uses a number already in origin/main
  - OTHER: <describe>
>

## Step 1 — Restore context

cd /home/michael/recompete-worktrees/<worktree-name>
cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
cat LANE.md
git fetch origin
git status --short
git status -sb
git log --oneline -8

## Step 2 — Understand the rejection

Read the conflicting files. Understand what origin/main now contains that your
commit did not account for. The Integration stack that is now on origin/main includes:

<PASTE THE RELEVANT INTEGRATION COMMITS THAT CONFLICT, e.g.:>
  9d66c07 feat(platform): reliable daily ingest scheduling via Railway cron

Your commit <ORIGINAL_HASH> conflicts with the above because both modify <file(s)>.

## Step 3 — Repair

Choose the correct repair strategy:

### If CONFLICT:
Rebase your branch onto current origin/main:
  git fetch origin
  git rebase origin/main

Resolve conflicts, preserving your intended feature while incorporating the
changes from origin/main. Do not drop the other lane's work.

### If LANE.md bundled:
Amend or create a new commit that excludes LANE.md:
  git reset HEAD LANE.md
  git commit --amend --no-edit   # or create a new commit

LANE.md is a governance doc for this worktree only. It must never travel with product commits.

### If MIGRATION COLLISION:
Rename your migration file to the next available number:
  git mv migrations/<OLD>_foo.sql migrations/<NEW>_foo.sql
  # update any references in the file (e.g. comment headers)
  # update any code that references the old filename
  git add migrations/
  git commit --amend --no-edit   # or create a new commit

Check what numbers are taken: ls /home/michael/recompete-worktrees/integration/migrations/

## Step 4 — Validate

Run your lane's relevant tests:
  python -m pytest tests/<your_test_files> -v

Fix any failures you introduced. Pre-existing failures are not your responsibility here.

## Step 5 — Commit

After repair, produce a clean commit. If you rebased, the existing commit may already
be clean. If you amended, confirm with:
  git show --stat --oneline HEAD

Verify:
- ai_agent/REVIEW.md is NOT staged
- LANE.md is NOT staged
- No unintended files are staged

## Step 6 — Report handoff

Report:
1. What the original rejection was
2. How you repaired it
3. What tests passed
4. The new clean handoff:

Integration handoff:
<Lane Name>:
- <NEW_COMMIT_HASH> <commit_message>

Note: the new hash will differ from the rejected one. Integration will use only the new hash.
```

---

## Common Repair Patterns

### Conflict in tasks.py or janitorial_recompete_report.py
These files are co-owned by `lane/data-pipeline` and `lane/platform`. After platform's
ingest scheduling changes land in `origin/main`, data-pipeline must rebase and merge
both sets of changes (Celery task dispatch + scheduling improvements) into a unified version.

### LANE.md in diff
Lane agents sometimes commit their LANE.md by mistake. Always check before committing:
```bash
git status --short   # confirm LANE.md is not staged
```
If it is staged: `git reset HEAD LANE.md`

### Migration collision
After any platform commit lands, run `ls migrations/` in the integration worktree to find
the highest-numbered migration, then number yours one higher.
