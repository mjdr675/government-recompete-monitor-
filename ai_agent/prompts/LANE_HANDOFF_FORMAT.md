# Lane Handoff Format

Every lane agent session must end with an Integration handoff in this exact format.
Integration will not accept vague descriptions — only explicit commit hashes.

---

## Required Format

```
Integration handoff:
<Lane Name>:
- <commit_hash> <commit_message>
```

### Single commit example

```
Integration handoff:
Contract Intelligence:
- 4dcd724 feat(contract-intel): per-contract recompete score breakdown on detail page
```

### Multiple commits example

```
Integration handoff:
Platform:
- 380b939 feat(platform): reliable daily ingest scheduling via Railway cron
- 67f2aae feat(platform): company branding, feedback backend, plan catalog, contract lookup
```

### Multiple lanes (batch handoff)

```
Integration handoff:
UI/Product:
- d010d0f feat(ui): polish branding, contract CTAs, pricing, and dark mode

Search:
- c475b55 feat(search): fuzzy NL query parsing, category filter fix, city/zip location columns

Bugfix:
- bb654aa fix(bugfix): seed pagination fixtures inside applyable window
```

---

## Rules

1. **Always include the full 7-character commit hash** — Integration uses `git show <hash>` to inspect before applying.
2. **Commits must be locally committed** before handoff — Integration cherry-picks; it cannot pick uncommitted work.
3. **Do not include staging-only or chore commits** that were used only to shape diff context. Include only the final deliverable commit(s).
4. **One commit per bullet** — do not bundle multiple changes into a description.
5. **Do not include `LANE.md` in the commit** — verify with `git show --stat <hash>` before handing off.
6. **Do not include `ai_agent/REVIEW.md`** — verify with `git show --stat <hash>`.
7. **Migration numbers must not collide** — check `ls /home/michael/recompete-worktrees/integration/migrations/` before handing off.

---

## Pre-handoff Checklist

Before producing the handoff line, run:

```bash
# Confirm commit exists and has the right files
git show --stat --oneline <hash>

# Confirm LANE.md and REVIEW.md are NOT in the commit
git show --name-only <hash> | grep -E "LANE.md|REVIEW.md" && echo "BAD: governance file in commit" || echo "OK"

# Confirm migration number does not collide
git show --name-only <hash> | grep migrations/ | while read f; do
  base=$(basename "$f")
  if ls /home/michael/recompete-worktrees/integration/migrations/"$base" 2>/dev/null; then
    echo "COLLISION: $base already exists in integration"
  fi
done
```

If any check fails, fix the commit before handing off (see `LANE_REPAIR_TASK.md`).

---

## Lane Name Reference

| Worktree                                               | Lane Name             |
| ------------------------------------------------------ | --------------------- |
| `/home/michael/recompete-worktrees/integration`        | Integration Gate      |
| `/home/michael/recompete-worktrees/data-pipeline`      | Data Pipeline         |
| `/home/michael/recompete-worktrees/search`             | Search                |
| `/home/michael/recompete-worktrees/customer-workspace` | Customer Workspace    |
| `/home/michael/recompete-worktrees/platform`           | Platform              |
| `/home/michael/recompete-worktrees/contract-intel`     | Contract Intelligence |
| `/home/michael/recompete-worktrees/ui-polish`          | UI/Product            |
| `/home/michael/recompete-worktrees/bugfix`             | Bugfix                |
