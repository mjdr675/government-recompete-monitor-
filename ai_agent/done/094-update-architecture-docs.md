# Task 094 — Update ARCHITECTURE.md to reflect current state

**Epic:** E07
**Milestone:** M3
**Sprint:** C-7
**Complexity:** XS
**Status:** QUEUED

## Objective

Bring `docs/ARCHITECTURE.md` in sync with the actual current system so new contributors and the AI agent have accurate reference material.

## Requirements

Update `docs/ARCHITECTURE.md` to reflect:
- Test count: 941 (not whatever was there before)
- Sprint A complete: PostgreSQL-compatible auth + analytics, CSRF, rate limiting, webhook sig verification, pinned deps
- Sprint B complete: user_watchlist, user_saved_searches, contract_notes, CSV export, bookmark toggles on list + detail, /watchlist page + nav badge, /searches page, "Save this search" button, notes on detail page
- Sprint C complete (C-1 through C-5): ingest_log table, metadata written after run_ingest, /api/data-freshness route, dashboard freshness indicator, quality alert for low record count
- Tables now in schema: contracts, users, celery_task_log, user_watchlist, user_saved_searches, contract_notes, ingest_log, contract_snapshots, changes, demo_requests, early_access
- New routes: /watchlist, /watchlist/add, /watchlist/remove, /searches, /searches/save, /searches/<id> (DELETE), /contract/<id>/note, /contracts/export.csv, /api/data-freshness
- Sprint D (email infrastructure) is next
- `_PUBLIC_PATHS` frozenset governs auth bypass; dynamic-path JSON routes use before_request method+prefix check

## Acceptance Criteria

- [ ] ARCHITECTURE.md table counts and sprint status are accurate
- [ ] Schema table list is complete
- [ ] No code changes — docs only

## Hard Dependencies

None.

## Testing

No tests. Docs change only.

## Suggested Commit Message

`docs: update ARCHITECTURE.md to reflect Sprint A–C completion (Task 094)`
