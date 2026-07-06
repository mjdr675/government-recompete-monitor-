# Follow-up items — deferred from PR #37

Logged 2026-07-06 after CodeRabbit re-review of `lane/customer-workspace @ 4f063e3`.
Not fixing in this PR — merge decision on #37 is proceeding separately.

## 🟠 Major — UEI backfill runs on every `init_db()` call

**File:** `db.py:396-402` (inside `_ensure_ci_columns`)

`_ensure_ci_columns()`'s backfill loop re-scans every non-empty
`recipient_uei` row and diff-checks it on **every** `init_db()` call.
`save_snapshot()` calls `init_db()` on every save (`db.py:1660`), so on a
hot save path we re-scan every non-empty `recipient_uei` row per save.
Cheap per-row after the first pass (all rows already normalized → 0 UPDATE
statements), but the SELECT still grows O(n) with the contracts table.

CodeRabbit's original approach (deleted in `4f063e3`) used a marker table
so the backfill only ever ran once. The tradeoff we accepted: correctness
via diff-check is simpler and self-healing (a rogue write of a raw value
would get normalized on the next startup), but at O(n) per save.

**Suggested fixes when we address this:**
- Cheapest: module-level `_backfill_ran` bool guarded on first `init_db`
  call; runs once per process. Loses persistence — a fresh worker still
  runs it, but that's already the case.
- Nicer: reintroduce a marker row in a `data_backfills` table (as
  CodeRabbit had). Persists across process restarts.
- Alternative: run the backfill only when `save_snapshot()` observes at
  least one raw value on read, then set the module-level flag.

## 🔵 Trivial nit — Duplicate normalization formula

**File:** `db.py:397`, `db.py:1519`, `db.py:1767`

`"".join((x or "").split()).upper()` is repeated verbatim in
`_ensure_ci_columns`, `upsert_contract`, and `save_snapshot`. Extract a
`_normalize_uei(value)` helper and call it from all three sites so the
rule only exists in one place.

Note: `analytics.py` already has `normalize_uei()` (module-level) but
`db.py` intentionally does not import from `analytics.py` to avoid a
circular import (`analytics.py` imports `db.py`). Either duplicate the
helper in `db.py`, or move the helper into a shared module both can
import.

## 🛠️ Repo hygiene — Worktree creation must propagate `.claude/settings.json`

**Discovered 2026-07-06** while investigating why the `gate_guard.py` PreToolUse
hook did not block `gh pr merge 37 --squash` executed from this worktree.

Root cause: worktrees are their own Claude Code project scope, so
`.claude/settings.json` in a worktree is what loads for sessions run from
that worktree — not the file in the main repo. The gate-guard hook was
installed in `/home/michael/government-recompete-monitor-/.claude/settings.json`
only, so every session run from a worktree bypassed the gate entirely
(0 hooks loaded).

Applied fix (config edits only): patched `.claude/settings.json` in all
8 current worktrees — bugfix, data-pipeline, gate1, gate1-deploy,
integration, search, ui-polish, customer-workspace — to add the
`PreToolUse` hook block, pointing at an absolute path
(`/home/michael/government-recompete-monitor-/.claude/hooks/gate_guard.py`)
so `$CLAUDE_PROJECT_DIR` doesn't misresolve into the worktree.

Follow-up (not done here): the worktree-creation script needs to
propagate `.claude/settings.json` when a new worktree is added, or
symlink `.claude/hooks/` from the main repo into each worktree so the
gate script is picked up automatically. Without this, the next
worktree created will re-open the exact same gap. Candidate locations
for the script fix:
- Whatever wraps `git worktree add` on this box (check
  `scripts/` in the main repo).
- Add a repo-level `just`/`make` target `worktree-new NAME` that runs
  `git worktree add` + copies `.claude/settings.json` + creates a
  matching `.claude/hooks/` symlink.

Also worth considering: publishing the hook via `~/.claude/settings.json`
(Fix B from the investigation report) so it fires globally. Trade-off:
non-recompete projects would also see it. Since the script only gates
`git merge` / `gh pr merge` / force-push / main-push / a specific CSV,
that's likely harmless — but scoping via cwd would be tighter.

## 🔵 Trivial nit — Duplicate days-remaining ternary

**File:** `templates/dashboard.html:794-818` and `templates/dashboard.html:554-556`

The `days-critical`/`days-warning` inline conditional class logic in the
new biz_opps table row duplicates the same inline ternary already used at
lines 554-556. Extract a Jinja macro:

```jinja
{% macro days_cell(days_remaining) %}
  <td class="col-r {% if days_remaining is not none and days_remaining <= 30 %}days-critical{% elif days_remaining is not none and days_remaining <= 90 %}days-warning{% endif %}">
    {{ days_remaining if days_remaining is not none else '&mdash;' }}
  </td>
{% endmacro %}
```

Then use it at both sites so threshold changes only need one edit.
