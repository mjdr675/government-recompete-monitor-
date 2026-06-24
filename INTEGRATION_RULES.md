# Integration Gate Rules

Integration is the merge authority for Recompete.us. These rules are non-negotiable.

---

## What Integration Does

- Accepts explicit handoff commits from lane agents
- Cherry-picks them one at a time onto `lane/integration`
- Validates the result with `scripts/integration_gate.sh`
- Pushes to `origin/main` only on Michael's explicit approval

## What Integration Does NOT Do

- Build features
- Repair lane code
- Patch test failures unrelated to the cherry-pick
- Force push
- Merge without a passing gate run
- Push without approval

---

## Step-by-Step Process

### 1. Preflight

```bash
cd /home/michael/recompete-worktrees/integration
git fetch origin
git status --short          # must be clean except known governance untracked files
git branch --show-current   # must be lane/integration
bash scripts/check_lanes.sh # must pass
```

If `ai_agent/REVIEW.md` is dirty, restore it:
```bash
git checkout -- ai_agent/REVIEW.md
```

If any other tracked file is dirty: **STOP and report**.

### 2. Inspect each commit before applying

```bash
git show --stat --oneline <hash>
```

Verify:
- The commit hash exists locally
- Files changed are within the lane's ownership
- `LANE.md` is NOT in the diff (governance file must not travel in product commits)
- No migration number collision with files already in `migrations/`

### 3. Cherry-pick one commit at a time

```bash
git cherry-pick <hash>
```

If conflict: `git cherry-pick --abort`, then stop and report which files conflict and which lane owns them.

After each cherry-pick:
```bash
git status --short
git show --stat --oneline HEAD
```

### 4. Run lane checks

```bash
bash scripts/check_lanes.sh
```

### 5. Run full Integration Gate

```bash
bash scripts/integration_gate.sh [lane-branch]
```

Gate must print `INTEGRATION GATE PASSED` before any push is considered.

If the gate fails with a `disk I/O error` or `Killed` (resource exhaustion), run cleanup once and retry once:

```bash
bash scripts/clean_test_tmp.sh
bash scripts/integration_gate.sh [lane-branch]
```

If the gate fails with a test failure:
1. Run the failing test on `lane/bugfix` (at `origin/main`) to determine if pre-existing
2. If pre-existing: classify and route to owning lane. Do not patch in Integration.
3. If new: abort the cherry-pick and return to source lane.

### 6. Push — only on explicit approval

Push only when Michael types an explicit approval in chat. Use:

```bash
git push origin lane/integration:main
```

Never use `--force` or `--force-with-lease`.

After push, verify:
```bash
git fetch origin
git status -sb   # should show no ahead/behind
git log -1 --oneline --decorate origin/main
```

---

## Source of Truth

- `origin/main` is the production source of truth.
- Lane branches are experimental until integrated.
- `lane/integration` is a staging compiler, not a feature branch.

---

## Commit Classification Guide

| Symptom | Classification | Action |
|---|---|---|
| `LANE.md` in cherry-pick diff | Lane hygiene error | Reject; ask lane to split `LANE.md` out |
| Migration number collision | Lane hygiene error | Reject; ask lane to renumber |
| `git cherry-pick` conflict | Base mismatch | Abort; ask lane to rebase onto `origin/main` |
| Test failure — pre-existing | Infrastructure debt | Route to `lane/bugfix`; don't block merge |
| Test failure — new in this commit | Regression | Abort cherry-pick; return to source lane |
| `Killed` / `disk I/O error` | Transient infra | Run `clean_test_tmp.sh`, retry once |

---

## App Ownership

`app.py` structure belongs to `lane/platform`. Other lanes may add route behavior but must
not add a new `Flask()` initialization or restructure the app factory.

## Data Ownership

| Lane | Role |
|---|---|
| `lane/data-pipeline` | Writes and prepares contract data |
| `lane/search` | Reads and ranks at query time |
| `lane/contract-intel` | Scores and interprets |

---

## Handoff Format

Every lane must end its session with:

```
Integration handoff:
<Lane Name>:
- <commit_hash> <commit_message>
```

Integration will not accept vague descriptions — only explicit commit hashes.
