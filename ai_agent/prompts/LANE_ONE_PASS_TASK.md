# Lane One-Pass Task Prompt

Use this prompt to give a lane agent a single focused task. The agent restores context,
implements the work, validates it, commits locally, and ends with an Integration handoff.
It does not push to `origin/main`.

---

## Prompt Template

```
You are the Recompete <LANE NAME> agent.
Lane: lane/<branch-name>
Worktree: /home/michael/recompete-worktrees/<worktree-name>

## Step 1 — Restore context

cd /home/michael/recompete-worktrees/<worktree-name>
cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
cat LANE.md
git fetch origin
git status --short
git status -sb
git branch --show-current
git log --oneline -5

Confirm:
- You are in the correct worktree
- You are on the correct branch
- Worktree is clean (or dirty only with known debris)
- You understand what this lane owns

## Step 2 — Inspect current state

Read the relevant files before changing anything.
Report what exists, what is missing, and what the task requires.

## Step 3 — Implement

Work only on files this lane owns (see LANE.md).
Do not touch:
- ai_agent/REVIEW.md
- LANE.md (leave untracked)
- Other lanes' core files unless coordination is documented

## Step 4 — Validate

Run the relevant test suite:
  python -m pytest tests/<relevant_test_file>.py -v

Or full suite if the change is broad:
  python -m pytest tests/ -x -q

Fix any failures you introduced. Do not fix pre-existing unrelated failures here.

## Step 5 — Commit locally

git add <specific files only — never git add -A>
git status --short   # confirm only intended files are staged
git commit -m "<type>(<lane>): <description>"

Do NOT commit:
- ai_agent/REVIEW.md
- LANE.md
- .env or credentials

## Step 6 — End with Integration handoff

Report:
1. What was built
2. What tests were run and passed
3. The exact handoff line below

Integration handoff:
<Lane Name>:
- <commit_hash> <commit_message>
```

---

## Task to assign

Replace the block below with the actual task:

```
TASK:
<Describe what needs to be built, fixed, or changed — be specific about files and behavior>

ACCEPTANCE CRITERIA:
<List what must pass for the task to be complete>
```

---

## Notes for the sending agent

- One task per prompt. Do not bundle unrelated work.
- The lane agent must not push to `origin/main`.
- The handoff hash is the only thing Integration needs.
- If the agent reports a blocker (conflict, missing dependency, schema issue), do not force it to continue — route the blocker appropriately.
