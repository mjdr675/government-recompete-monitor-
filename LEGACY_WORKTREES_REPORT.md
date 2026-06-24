# Legacy Worktrees Report

Generated: 2026-06-24

**Status:** Quarantine list only. Nothing has been moved or deleted.
**Action required:** Review each entry before archiving. Do not bulk-delete.

Canonical worktrees live at `/home/michael/recompete-worktrees/`.
All entries below are outside that path and are candidates for future archival.

---

## Legacy Worktrees

| Path | Branch | Dirty Files | Last Commit | Canonical Lane | Safe to Archive? |
|---|---|---|---|---|---|
| `/home/michael/integration-clean-wt` | `integration-finished-lanes-clean` | 1 | `5a07452` merge(main): resolve conflicts + wire missing workspace db imports | `lane/integration` | ⚠️ Review — has untracked file |
| `/home/michael/prune-wt` | `chore/prune-contract-id-legacy` | 2 | `75ecafe` chore(prune): remove dead legacy contract_id field-change code | None (chore branch) | ⚠️ Review — 2 dirty files |
| `/home/michael/recompete-auto-contract-updates` | `auto-contract-updates` | 0 | `64f935e` feat(updates): dashboard Recent Updates feed (Phase B) | `lane/data-pipeline` | ✅ Clean — safe to archive after confirming branch is merged or superseded |
| `/home/michael/recompete-auto-updates` | `feat/auto-updates-change-detection` | 1 | `1dc16be` feat(auto-updates): dashboard Recent Updates feed | `lane/data-pipeline` | ⚠️ Review — has untracked file |
| `/home/michael/recompete-brand-account-foundation` | `brand-account-foundation` | 0 | `a5ca5a9` feat(account): add company workspace branding | `lane/customer-workspace` | ✅ Clean — safe to archive after confirming branch is merged or superseded |
| `/home/michael/recompete-ci-compare` | `contract-intelligence-compare` | 0 | `7c59ded` feat(contracts): add NAICS and state to multi-contract compare | `lane/contract-intel` | ✅ Clean — safe to archive |
| `/home/michael/recompete-ci-intel` | `contract-intelligence-analytics` | 0 | `621a3b5` refactor(contracts): extract compare ranking into shared domain policy | `lane/contract-intel` | ✅ Clean — safe to archive |
| `/home/michael/recompete-contract-intelligence-tools` | `contract-intelligence-tools-clean` | 0 | `f035349` feat(contracts): improve contract intelligence tools | `lane/contract-intel` | ✅ Clean — safe to archive |
| `/home/michael/recompete-dashboard-personalization` | `dashboard-personalization` | 1 | `b88cd60` feat(dashboard): add personalization engine | `lane/customer-workspace` | ⚠️ Review — has untracked file |
| `/home/michael/recompete-dashboard-personalization-fresh` | `dashboard-personalization-clean` | 1 | `9386792` feat(dashboard): personalize with profile-matched contracts | `lane/customer-workspace` | ⚠️ Review — has untracked file |
| `/home/michael/recompete-data` | `lane/data` | 1 | `85e7ac3` data: index contract description in FTS so search works by work type | `lane/data-pipeline` | ⚠️ **DO NOT ARCHIVE YET** — `lane/data-pipeline` was branched from this; its history contains prior ingestion work |
| `/home/michael/recompete-integration-finished-lanes` | `integration-finished-lanes` | 0 | `51d87ba` wip(recovery): payments capability layer + portable tool registry | None (old integration) | ✅ Clean — likely superseded by new lane system |
| `/home/michael/recompete-main` | `main` | 0 | `5c6de9c` fix: remove debug logging.basicConfig | None (main branch ref) | ⚠️ Keep — useful as a clean main branch checkout. Note: 28 commits behind `origin/main` |
| `/home/michael/recompete-natural-search` | `feat/natural-query-parser` | 1 | `9e42beb` feat(search): natural-language query parsing | `lane/search` | ⚠️ Review — has untracked file; contains NL search work not yet in `lane/search` |
| `/home/michael/recompete-platform-foundations` | `platform-foundations` | 0 | `8165743` docs(platform): promote active_view_id to a documented contract | `lane/platform` | ✅ Clean — safe to archive if work is captured in `lane/platform` |
| `/home/michael/recompete-platform-infra` | `platform-infra-reliability` | 1 | `8aaead9` ci(deploy): serialize deploys with concurrency guard + reliability audit | `lane/platform` | ⚠️ Review — has untracked file; CI reliability work worth reviewing |
| `/home/michael/recompete-platform-infra-2` | `platform-infra-backup` | 1 | `5513d3a` refactor(db): explicit dual-dialect dispatch for contract_field_changes schema | `lane/platform` | ⚠️ Review — has untracked file; DB dialect work may not be merged |
| `/home/michael/recompete-platform-infra-3` | `platform-infra-query-layer` | 12 | `8958a5f` refactor: use SQL applyable filter in /contracts route | `lane/platform` | 🔴 **12 dirty files** — likely active work in progress; DO NOT ARCHIVE |
| `/home/michael/recompete-schema-authority` | `fix/contract-field-changes-schema-authority` | 1 | `634122c` fix(schema): remove Contract A dead code | `lane/platform` | ⚠️ Review — fix branch; check if merged to main |
| `/home/michael/recompete-search-discovery-foundation` | `search-discovery-foundation-clean` | 0 | `41de51a` Update deploy.yml | `lane/search` | ✅ Clean — likely superseded by `lane/search` |
| `/home/michael/recompete-search-discovery-phase1` | `search-discovery-saved-views` | 1 | `a41ca03` feat(search): highlight active saved view in quick-view chips | `lane/search` | ⚠️ Review — saved views work may not be in `lane/search` yet |
| `/home/michael/recompete-sql-safety` | `fix/parameterize-personalized-query` | 1 | `5be8b76` fix(dashboard): parameterize personalized business query | `lane/platform` | ⚠️ Review — security fix; verify it is merged to main |
| `/home/michael/recompete-ui` | `ui/dashboard-redesign` | 1 | `7a98cef` fix: align dashboard with target SaaS UI and persist dark mode | `lane/ui-polish` | ⚠️ Review — has untracked file |
| `/home/michael/recompete-ui-polish-education-clean` | `ui-polish-education-clean` | 79 | `f49209a` feat(ui): branding, 3-tier pricing, contract card polish | `lane/ui-polish` | 🔴 **79 dirty files** — major in-progress work; DO NOT ARCHIVE |
| `/home/michael/recompete-workspace` | `feat/customer-workspace` | 1 | `1212521` feat(dashboard): company branding, incumbent contracts, and /discover page | `lane/customer-workspace` | ⚠️ Review — has untracked file |
| `/tmp/recompete-test` | (detached HEAD) | 1 | `1ea95bd` fix: resolve 502, failing CI | None | ✅ Safe to remove — detached HEAD in /tmp, appears to be a CI artifact |

---

## Summary

| Status | Count |
|---|---|
| 🔴 DO NOT ARCHIVE (active dirty work) | 2 |
| ⚠️ REVIEW before archiving | 15 |
| ✅ Safe to archive (clean, likely superseded) | 6 |
| Keep indefinitely | 1 (`recompete-main`) |
| Remove (CI artifact) | 1 (`/tmp/recompete-test`) |

---

## Highest Priority Reviews

1. **`/home/michael/recompete-platform-infra-3`** — 12 dirty files on `platform-infra-query-layer`. This is the branch that `origin/main` is currently at. If there are 12 local untracked/modified files, that work has NOT been committed or pushed.
2. **`/home/michael/recompete-ui-polish-education-clean`** — 79 dirty files on `ui-polish-education-clean`. Large in-progress UI work. Must be reviewed before any decision.
3. **`/home/michael/recompete-data`** — Contains `lane/data` which is the source of `lane/data-pipeline`. Do not remove until `lane/data-pipeline` has absorbed all useful prior work.
4. **`/home/michael/recompete-sql-safety`** — SQL parameterization security fix. Verify it reached `main` before removing.

---

## Recommended Archive Process (when ready)

```bash
# For each worktree confirmed safe:
# 1. Confirm branch is either merged to main or explicitly abandoned
git log origin/main..<branch> --oneline  # shows unmerged commits

# 2. Remove worktree registration (does NOT delete branch)
git worktree remove /home/michael/recompete-<name>

# 3. Optionally delete branch only after confirming no unmerged work
git branch -d <branch-name>  # -d refuses if unmerged; use -D only with intent
```
