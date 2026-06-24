# Recompete Integration Rules

These rules govern how lane branches are merged into `main`. The integration gate enforces them mechanically; this document explains the intent.

---

## Source of Truth

- `origin/main` is the production source of truth unless explicitly overridden by the user.
- Lane branches are experimental until integrated — they are not production.
- The integration lane (`lane/integration`) is a staging compiler. It is not a feature branch.
- If `origin/main` diverges from local `main`, always pull and reconcile before merging any lane.

---

## Merge Protocol

Execute in this exact order. Do not skip steps.

1. **Ensure lane branch is clean** — `git status --short` shows no dirty tracked files
2. **Ensure lane has a handoff summary** — a commit message or `HANDOFF.md` describing what was built and what was tested
3. **Merge only one lane at a time** — do not batch multiple lanes into a single integration session
4. **Run the integration gate**: `bash scripts/integration_gate.sh lane/<name>`
5. **If gate passes**: commit the integration merge with `--no-ff`
6. **If gate fails broadly**: abort or reset, do not patch blindly (see Large Failure Rule below)

---

## Force Push Rule

**Never force push without:**
- Explicit user approval (written, in this session)
- A written list of exactly which commits would be overwritten
- Confirmation that no other agents or users are working on the affected branch

Force pushing to `main` is never allowed under any circumstances without user approval.

---

## Large Failure Rule

If a merge causes any of the following:
- Missing imports or `ImportError` on startup
- Broken `app.py` (Flask won't initialize)
- Route collapse (major routes returning 500)
- 50+ test failures (not pre-existing)

Then:

1. **STOP** — do not attempt to patch inline
2. Run `git merge --abort` or `git reset --hard HEAD` to restore pre-merge state
3. Run `git worktree list` and confirm integration is back to baseline
4. Report: which lane introduced the failure, what the first error was, what the pre-merge commit was
5. **Ask for direction** before retrying

Do not treat integration failures as debugging sessions. The owning lane must fix its own lane.

---

## App Ownership Rule

`app.py` structure belongs to `lane/platform`. Other lanes may only modify route *behavior* when their lane requires it, and must document that change in their commit message. No lane other than platform may add a new `Flask()` initialization or restructure the app factory.

---

## Data Ownership Rule

| Lane | Role |
|---|---|
| `lane/data-pipeline` | Writes and prepares contract data |
| `lane/search` | Reads and ranks contract data at query time |
| `lane/contract-intel` | Interprets and scores contract data |

No lane reads from another lane's write path without coordinating on the schema.

---

## Stale Remote Rule

If a remote branch is detected to be ahead of the local branch being merged, or if a push would overwrite work:
- Do not accept the rewrite silently
- Report the divergence and ask which version is authoritative
- Never `git push --force` to resolve without explicit user approval

---

## Pre-existing Test Failures

If the integration gate reports a test failure that exists in `origin/main` (pre-existing, not introduced by the lane being merged):
- Document it in this file or in a comment on the merge commit
- Assign it to the owning lane for repair
- Do not block other lane merges indefinitely on pre-existing failures unless they are structural (app won't start)

### Known Pre-existing Failures (as of 2026-06-24)

| Test | File | Owning Lane | Status |
|---|---|---|---|
| `test_contracts_days_critical_class_for_imminent_expiry` | `tests/test_app.py:151` | `lane/ui-polish` | Failing in `origin/main` baseline — CSS class `days-critical` not rendered |
