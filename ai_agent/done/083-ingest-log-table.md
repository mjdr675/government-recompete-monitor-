# Task 083 — Add ingest_log table and write metadata after run_ingest

**Epic:** E07  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

Add an `ingest_log` table to record each ingest run's outcome. Write a log row at the
end of the `run_ingest` Celery task (both success and failure). This enables the
data-freshness indicator (Task 084) and silent-failure detection (Sprint C-5).

## Requirements

- In `db.py` `init_db()`: add `CREATE TABLE IF NOT EXISTS ingest_log`:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `run_date TEXT NOT NULL` (ISO-8601 date, e.g. "2026-06-20")
  - `source TEXT NOT NULL` (e.g. "usaspending" or "csv_upload")
  - `record_count INTEGER NOT NULL DEFAULT 0`
  - `duration_seconds REAL`
  - `status TEXT NOT NULL` (e.g. "success", "failure")
  - `error_message TEXT`
  - `created_at TEXT NOT NULL`
- In `migrations/001_initial_pg.sql`: add equivalent PostgreSQL `CREATE TABLE IF NOT EXISTS ingest_log`
- In `tasks.py` `run_ingest()`: record start time before main work; after completion (or in
  except block on failure), insert a row into `ingest_log` using `get_engine().begin()` + `text()`
  - `source = "usaspending"`
  - `record_count` = number of contracts upserted
  - `duration_seconds` = elapsed wall-clock seconds
  - `status = "success"` on normal completion, `"failure"` on exception
  - `error_message` = str(exception) on failure, NULL on success

## Acceptance Criteria

- [ ] `ingest_log` table is created by `init_db()`
- [ ] After `run_ingest()` completes successfully, a row appears in `ingest_log` with `status="success"`
- [ ] If `run_ingest()` raises an exception, a row appears with `status="failure"` and `error_message` set
- [ ] Migration SQL is valid PostgreSQL
- [ ] New test: mock ingest to return a known record count; assert ingest_log row is written
- [ ] Existing Celery ingest tests still pass

## Hard Dependencies

- Task 065: Celery ingest task — must be DONE

## DB Changes

New table: `ingest_log`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add test to `tests/test_celery_ingest.py`: after calling the ingest function directly,
query ingest_log and assert one row with expected status and record_count.

## Suggested Commit Message

`feat: add ingest_log table and write metadata after run_ingest (Task 083)`
