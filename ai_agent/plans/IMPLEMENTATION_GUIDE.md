# IMPLEMENTATION GUIDE
# How autonomous Claude sessions execute the Master Engineering Roadmap

---

## 1. Before Starting Any Session

Read these files in order:
1. `ai_agent/plans/MASTER_ROADMAP_00_RECOVERY_SUMMARY.md` — epic map and milestone context
2. `ai_agent/plans/MASTER_ROADMAP_02_MILESTONES_AND_EPICS.md` — milestone gates
3. `ai_agent/plans/MASTER_ROADMAP_08_DEPENDENCIES.md` — dependency table
4. `TASK_LOG.md` — what has already been completed
5. `HANDOFF.md` (last entry) — current state from the prior session

Then check the queue: `ls ai_agent/queue/ | sort`

---

## 2. Selecting the Next Task

### Step 1 — Identify the current milestone
Check `MASTER_ROADMAP_02_MILESTONES_AND_EPICS.md` milestone gate checklists.
Find the lowest milestone (M1 → M2 → ...) whose gate is NOT complete.

### Step 2 — Find eligible tasks
From the lowest incomplete milestone, find tasks that:
- Are listed in the corresponding task file (03–07)
- Have ALL hard dependencies marked DONE in `TASK_LOG.md`
- Are NOT already in `ai_agent/queue/` or `ai_agent/done/`

### Step 3 — Apply priority order
Within eligible tasks, prioritize:
1. Tasks in `backlog/critical.md` or `backlog/bugs.md` with `[OPEN]` status
2. The blocking dependency tasks (see Section 4 of DEPENDENCIES.md)
3. Lowest task number first (earlier tasks have lower dependencies)

### Step 4 — Pick exactly one task
Select one task. Write it to `ai_agent/queue/<number>-<slug>.md`. Do not queue more than one.

---

## 3. Implementing One Task

### Before writing any code
- Read every file the task touches (routes, templates, db.py, tests)
- Check that the task's hard dependencies are actually complete (not just listed as DONE)
- If a dependency is missing, stop and implement it first

### Implementation rules
- Implement only what the task's Requirements section specifies
- Do not fix unrelated bugs discovered during implementation (add them to `backlog/bugs.md`)
- Do not refactor code outside the task's scope
- Do not add features not listed in the task's Requirements
- If the task requires a new table, use `CREATE TABLE IF NOT EXISTS`
- If the task requires a new route, follow the existing pattern in `app.py`

### Scope creep test
Before committing, ask: "Does every changed line directly implement a stated requirement?"
If no → revert that line.

---

## 4. Stopping After Each Task

**One task = one commit = one session.**

After the commit:
1. Update `TASK_LOG.md` (append one row)
2. Update `HANDOFF.md` (append one entry)
3. Move the task file from `ai_agent/queue/` to `ai_agent/done/`
4. Stop. Do not start the next task in the same session.

The next session will pick up from TASK_LOG.md and HANDOFF.md.

---

## 5. When to Stop Without Completing

Stop and report (do not attempt to work around) if:
- A hard dependency is missing and cannot be verified as complete
- Tests fail and the fix would require changing code outside the task scope
- The task requirements are ambiguous or contradictory
- An external service (SAM.gov, Stripe, Anthropic) is unavailable and the task requires it

In all cases: write what was attempted to `HANDOFF.md`, leave the queue file in place, and stop.

---

## 6. File Ownership Rules

| File | Who can edit |
|---|---|
| `db.py` | Only tasks that explicitly list DB Changes |
| `app.py` | Only tasks that list new API routes |
| `analytics.py` | Only tasks that explicitly modify analytics queries |
| `auth.py`, `users.py` | Only auth/user management tasks |
| `requirements.txt` | Only tasks that list a new dependency |
| `TASK_LOG.md` | Append-only — never modify existing rows |
| `HANDOFF.md` | Append-only — never modify existing entries |
| `ai_agent/plans/*` | Never modify during app feature implementation |
| `backlog/*.md` | Only to mark tasks `[DONE]` or add new `[OPEN]` bugs |

---

## 7. Commit Message Format

```
<type>: <short description> (Task <number>)

Types: feat, fix, test, docs, perf, ci, refactor, chore
```

Examples:
```
feat: add min_value filter to get_contracts and /contracts route (Task 056)
test: add /health endpoint unit tests (Task 057)
feat: add PostgreSQL support with DATABASE_URL env var (Task 061)
```

The suggested commit message in each task file is the default. Use it verbatim unless
the implementation differs from what was planned.

---

## 8. Emergency Rollback

If `pytest` fails after applying changes:
1. `git stash` — preserve your work
2. Verify the test failure is caused by your changes (`git stash pop` → rerun tests to confirm)
3. Fix only the failing tests within the task scope
4. If the fix requires changes outside the task scope, roll back and report in HANDOFF.md

Never skip or delete tests to make CI pass.
