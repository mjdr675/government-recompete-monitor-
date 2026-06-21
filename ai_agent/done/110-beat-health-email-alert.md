# Task 110 — Add beat health admin email alert on stale beat:health key

**Epic:** E05
**Milestone:** M3
**Sprint:** G-5
**Complexity:** S
**Status:** QUEUED

## Objective

The existing `check_beat_health` task writes a `beat:health` key to Redis every 10 minutes.
Wire an email alert so the operator is notified when the key has not been refreshed in
over 20 minutes, indicating the beat scheduler has crashed or stalled.

## Requirements

- In `tasks.py`, in the existing `check_beat_health()` task, after detecting a stale key
  (current logic logs a warning), additionally enqueue an alert email:
  ```python
  admin_email = os.environ.get("ADMIN_EMAIL", "")
  if admin_email and stale:
      send_email_task.delay(
          to=admin_email,
          subject="[Gov Recompete Monitor] Beat scheduler may be down",
          html_body=f"<p>The Celery beat scheduler has not checked in for over 20 minutes. "
                    f"Last seen: {last_seen_str}. Check Railway logs immediately.</p>",
          text_body=f"Beat scheduler stale. Last seen: {last_seen_str}. Check Railway logs.",
      )
  ```
- Add `ADMIN_EMAIL` env var lookup. If not set, skip the email silently (same pattern
  as `SENTRY_DSN` — no-op when absent).
- Do not send the email every 10 minutes if the beat is continuously stale. Add a
  Redis key `beat:alert_sent` with TTL 3600 (1 hour) to deduplicate: only send if this
  key does not exist; set it immediately after enqueueing.
- The existing `_BEAT_HEALTH_KEY` and `_BEAT_HEALTH_TTL` constants are unchanged.

## Acceptance Criteria

- [ ] When `beat:health` key is stale and `ADMIN_EMAIL` is set, `send_email_task.delay()` is called
- [ ] When `ADMIN_EMAIL` is not set, no email is enqueued
- [ ] Deduplication: second stale detection within 1 hour does not send a second email
- [ ] When beat is healthy (key fresh), no email is sent
- [ ] All existing `check_beat_health` tests still pass

## Hard Dependencies

- Task 097: send_email_task Celery task — must be DONE

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_celery_ingest.py` (or a new `tests/test_beat_health.py`):
- `test_beat_health_alert_sent_when_stale`: monkeypatch Redis to return no value for
  `beat:health`; monkeypatch `send_email_task.delay` to record calls; set `ADMIN_EMAIL`;
  run `check_beat_health.apply()`; assert `delay` called once.
- `test_beat_health_no_alert_without_admin_email`: same stale condition but no
  `ADMIN_EMAIL` set; assert `delay` not called.
- `test_beat_health_dedup_prevents_second_email`: run task twice with stale key;
  monkeypatch Redis `get beat:alert_sent` to return a value on second call; assert
  `delay` called only once total.
- `test_beat_health_no_alert_when_healthy`: monkeypatch Redis to return a fresh timestamp;
  assert `delay` not called.

## Suggested Commit Message

`feat: add beat health email alert with 1-hour dedup (Task 110)`
