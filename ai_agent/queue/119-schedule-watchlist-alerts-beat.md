# Task 119 — Schedule check_watchlist_alerts via Celery beat at 07:00 UTC

**Epic:** E03
**Milestone:** M3
**Sprint:** E-6
**Complexity:** XS
**Status:** QUEUED

## Objective

Register `check_watchlist_alerts` in the Celery beat schedule so it runs automatically
every day at 07:00 UTC. Users receive their expiration alerts in the morning before
their workday starts.

## Requirements

- In `tasks.py` (or wherever `beat_schedule` / `CELERYBEAT_SCHEDULE` is defined),
  add an entry:
  ```python
  "check-watchlist-alerts-daily": {
      "task": "tasks.check_watchlist_alerts",
      "schedule": crontab(hour=7, minute=0),
  },
  ```
- If using a `celery.conf.beat_schedule` dict, add the entry there.
- If using `@celery.on_after_configure.connect`, add via `sender.add_periodic_task(...)`.
- Confirm the entry coexists with the existing `run_ingest` schedule (02:00 UTC) without
  conflict.

## Acceptance Criteria

- [ ] `check_watchlist_alerts` appears in the beat schedule at 07:00 UTC
- [ ] Existing `run_ingest` schedule is unchanged
- [ ] All existing beat schedule tests still pass (if any)

## Hard Dependencies

- Task 118: enqueue alert emails — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

`from celery.schedules import crontab` (already available if run_ingest uses it).

## Testing

Add 1 test to `tests/test_celery_ingest.py` (or new `tests/test_beat_schedule.py`):
- `test_watchlist_alerts_in_beat_schedule`: inspect `celery.conf.beat_schedule` (or the
  app's schedule dict); assert `"tasks.check_watchlist_alerts"` is a registered task
  with hour=7 and minute=0.

## Suggested Commit Message

`feat: schedule check_watchlist_alerts daily at 07:00 UTC via Celery beat (Task 119)`
