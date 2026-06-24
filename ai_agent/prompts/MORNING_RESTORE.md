# Morning Restore — Recompete Lane Context

Use this prompt at the start of any lane agent session (new chat, reset, or handoff).
Paste it verbatim or adapt the `<assigned-lane>` placeholder.

---

## Restore Prompt

```
Restore Recompete lane context before doing any work.

Go to your assigned worktree:
  cd /home/michael/recompete-worktrees/<assigned-lane>

Read governance docs:
  cat /home/michael/recompete-worktrees/integration/WORKTREE_LANE_SYSTEM.md
  cat LANE.md

Verify state:
  git status --short
  git status -sb
  git branch --show-current
  pwd

Report:
1. current path
2. current branch
3. whether docs were read
4. whether worktree is clean
5. what this lane owns
6. what this lane must not touch
7. whether safe to begin work

Do not edit any files until you have confirmed all seven points above.
```

---

## Lane → Worktree Reference

| Assigned Lane       | Worktree Path                                              |
| ------------------- | ---------------------------------------------------------- |
| integration         | `/home/michael/recompete-worktrees/integration`            |
| data-pipeline       | `/home/michael/recompete-worktrees/data-pipeline`          |
| search              | `/home/michael/recompete-worktrees/search`                 |
| customer-workspace  | `/home/michael/recompete-worktrees/customer-workspace`     |
| platform            | `/home/michael/recompete-worktrees/platform`               |
| contract-intel      | `/home/michael/recompete-worktrees/contract-intel`         |
| ui-polish           | `/home/michael/recompete-worktrees/ui-polish`              |
| bugfix              | `/home/michael/recompete-worktrees/bugfix`                 |

---

## Known Debris to Ignore

- `M ai_agent/REVIEW.md` — timestamp written by test infra; never commit it
- `?? LANE.md` — untracked governance doc; never commit it inside product commits
- `[ahead N, behind M]` — your lane branch will be behind `origin/main` after other lanes push; this is normal

## If /tmp Fills (sqlite3 disk I/O error during tests)

```bash
bash /home/michael/recompete-worktrees/integration/scripts/clean_test_tmp.sh
```
