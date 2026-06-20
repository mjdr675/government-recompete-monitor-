# Task 091 — Add GET /api/data-freshness route

**Epic:** E07
**Milestone:** M3
**Sprint:** C-3
**Complexity:** S
**Status:** QUEUED

## Objective

Expose last successful ingest metadata via a JSON API endpoint for the dashboard freshness indicator.

## Requirements

- New `GET /api/data-freshness` route in `app.py` (no auth required — public):
  - Add `/api/data-freshness` to `_PUBLIC_PATHS`
  - Queries `ingest_log` for the most recent row where `status = 'success'`, ordered by `created_at DESC LIMIT 1`
  - Also queries `SELECT COUNT(*) FROM contracts`
  - Returns JSON:
    ```json
    {
      "last_ingest": "2026-06-20T02:01:33Z",
      "record_count": 4821,
      "source": "usaspending",
      "hours_ago": 6.2
    }
    ```
  - If no successful ingest row exists, returns `{"last_ingest": null, "record_count": 0, "source": null, "hours_ago": null}`
  - `hours_ago` = difference between `datetime.now(utc)` and `created_at` in hours (float, 1 decimal)

## Acceptance Criteria

- [ ] `GET /api/data-freshness` returns 200 JSON for unauthenticated request
- [ ] Returns `last_ingest: null` when ingest_log is empty
- [ ] Returns correct `hours_ago` after a known ingest row is inserted
- [ ] `record_count` reflects total contracts in DB

## Hard Dependencies

- Task 083: ingest_log table — DONE

## Testing

Add 3 tests to new file `tests/test_data_freshness.py`: no ingest row → null fields, with ingest row → correct fields, hours_ago calculated correctly.

## Suggested Commit Message

`feat: add GET /api/data-freshness route (Task 091)`
