# Task 093 — Add data quality alert: log ERROR if ingest returns < 10 records

**Epic:** E07
**Milestone:** M3
**Sprint:** C-5
**Complexity:** XS
**Status:** QUEUED

## Objective

Detect silent ingest failures where SAM.gov returns an unexpectedly small result set.

## Requirements

- In `tasks.py` `run_ingest()`, after querying `COUNT(*) FROM contracts` on success:
  - If `record_count < 10`: call `logger.error("run_ingest: suspiciously low record count (%d) — possible silent failure or empty API response", record_count)`
  - Still write `status="success"` to `ingest_log` (the ingest itself did not error; the alert is a warning about data quality)
  - Do NOT raise — let the task complete normally
- The `_QUALITY_THRESHOLD = 10` constant should be defined at module level in `tasks.py`

## Acceptance Criteria

- [ ] `run_ingest()` logs an ERROR when record_count < 10 after a successful ingest
- [ ] No ERROR logged when record_count >= 10
- [ ] `ingest_log` row still written with `status="success"` even when alert fires
- [ ] All existing tests still pass

## Hard Dependencies

- Task 083: ingest_log table + run_ingest metadata write — DONE

## Testing

Add 2 tests to `tests/test_celery_ingest.py`:
- `test_low_record_count_logs_error`: mock main() to succeed; pre-insert 2 contracts into DB; assert `caplog` contains ERROR with "suspiciously low"
- `test_normal_record_count_no_error`: pre-insert 15 contracts; assert no ERROR logged

## Suggested Commit Message

`feat: add data quality alert for low ingest record count (Task 093)`
