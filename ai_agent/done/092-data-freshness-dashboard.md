# Task 092 — Add data freshness indicator to dashboard

**Epic:** E07
**Milestone:** M3
**Sprint:** C-4
**Complexity:** S
**Status:** QUEUED

## Objective

Show users when data was last updated on the dashboard, so they can trust what they're seeing.

## Requirements

- In `app.py` dashboard route (`GET /`):
  - Query `ingest_log` for most recent `status='success'` row (same query as Task 091 but inline — no need to call the API route internally)
  - Compute `hours_ago` (float, 1 decimal) from `created_at` to `datetime.now(utc)`
  - Pass `last_ingest` (ISO string or None) and `hours_ago` (float or None) to template
- In `templates/dashboard.html`:
  - Add a small freshness banner below the `<h1>` heading:
    - If `last_ingest`: `<div class="muted">Data last updated {{ hours_ago }}h ago ({{ last_ingest[:10] }})</div>`
    - If not `last_ingest`: `<div class="muted">Data freshness unknown — no ingest completed yet.</div>`

## Acceptance Criteria

- [ ] Dashboard shows "Data last updated Xh ago" when ingest_log has a success row
- [ ] Dashboard shows "Data freshness unknown" when ingest_log is empty
- [ ] All existing dashboard tests still pass

## Hard Dependencies

- Task 083: ingest_log table — DONE
- Task 091: /api/data-freshness route — not required (shares same query logic, but independent)

## Testing

Add 2 tests to `tests/test_app.py`: `test_dashboard_shows_freshness_banner_when_ingest_exists`, `test_dashboard_shows_unknown_when_no_ingest`. Both use the test client with an ingest_log row inserted directly via SQLAlchemy.

## Suggested Commit Message

`feat: add data freshness indicator to dashboard (Task 092)`
