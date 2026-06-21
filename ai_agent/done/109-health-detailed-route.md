# Task 109 — Add GET /api/health/detailed route

**Epic:** E05
**Milestone:** M3
**Sprint:** G-4
**Complexity:** S
**Status:** QUEUED

## Objective

Add an authenticated health endpoint that reports the live status of the database,
Redis, and data freshness. Operators and monitoring tools call this to detect partial
failures that the basic `/health` route does not surface.

## Requirements

- New route in `app.py`:
  ```python
  @app.route("/api/health/detailed")
  def health_detailed():
  ```
  - Auth-required: if `not g.user`, return `jsonify({"error": "unauthorized"})`, 401.
  - DB check: execute `text("SELECT 1")` via `get_engine().connect()`; if it raises,
    set `db_status = "error"`, else `"ok"`.
  - Redis check: call `redis.from_url(REDIS_URL).ping()`; if it raises (including
    `ConnectionError`), set `redis_status = "error"`, else `"ok"`.
  - Last ingest: query `ingest_log` for the most recent row with `status="success"`;
    include `last_ingest_at` (ISO string or null) and `last_ingest_records` (int or null).
  - Return JSON:
    ```json
    {
      "db": "ok",
      "redis": "ok",
      "last_ingest_at": "2026-06-20T02:05:00",
      "last_ingest_records": 1842,
      "ok": true
    }
    ```
    where `ok` is `true` only when both `db` and `redis` are `"ok"`.
  - HTTP status: 200 when `ok=true`, 503 when `ok=false`.
- Do NOT add to `_PUBLIC_PATHS` — auth gate is intentional.

## Acceptance Criteria

- [ ] Unauthenticated request returns 401
- [ ] Authenticated request with healthy DB and Redis returns `{"ok": true}` and 200
- [ ] Authenticated request when Redis unavailable returns `{"ok": false}` and 503
- [ ] `last_ingest_at` is null when no ingest_log rows exist
- [ ] Route does not appear in public navigation

## Hard Dependencies

- Task 083: ingest_log table — must be DONE
- Task 091: data-freshness API (established DB query pattern to reuse) — must be DONE

## DB Changes

None (reads from `ingest_log`).

## API Changes

New route: `GET /api/health/detailed`.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_app.py`:
- `test_health_detailed_requires_auth`: GET without session → 401.
- `test_health_detailed_returns_ok_when_healthy`: logged-in user, no Redis mock needed
  (use monkeypatch to stub Redis ping to return True); assert `{"ok": true}` and 200.
- `test_health_detailed_returns_503_when_redis_down`: monkeypatch Redis ping to raise
  `ConnectionError`; assert `ok=false` and 503.
- `test_health_detailed_last_ingest_null_when_no_rows`: no ingest_log rows; assert
  `last_ingest_at` is null.

## Suggested Commit Message

`feat: add GET /api/health/detailed route with DB and Redis status (Task 109)`
