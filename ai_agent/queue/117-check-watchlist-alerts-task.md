# Task 117 — Write check_watchlist_alerts() Celery task

**Epic:** E03
**Milestone:** M3
**Sprint:** E-3
**Complexity:** S
**Status:** QUEUED

## Objective

Implement the core alert dispatch Celery task that queries watched contracts approaching
expiration thresholds, filters by user preferences, deduplicates via `alert_log`, and
returns a list of (user_id, contract_id, days_threshold, email) tuples ready for email
enqueueing (Task 118).

## Requirements

- In `tasks.py`, add:
  ```python
  @celery.task(name="tasks.check_watchlist_alerts")
  def check_watchlist_alerts():
  ```
  - Query `user_watchlist` JOIN `contracts` JOIN `alert_preferences` WHERE
    `alert_preferences.enabled = 1`.
  - For each user's `alert_days` JSON array, compute how many days until
    `contract.end_date`; if `days_remaining` matches any threshold (±1 day window),
    and `contract.value >= alert_preferences.min_value`, and no row in `alert_log`
    matches `(user_id, contract_id, days_threshold)` — add to the pending list.
  - Return the pending list. (Actual email enqueueing is in Task 118; this task
    returns data so it can be tested without mocking `send_email_task`.)
  - Log `INFO` at start and end with counts: "Alert check: N candidates, M pending".

## Acceptance Criteria

- [ ] Returns empty list when no watched contracts match any threshold
- [ ] Excludes contracts already in `alert_log` for the same `(user_id, contract_id, days_threshold)`
- [ ] Respects `alert_preferences.min_value` filter
- [ ] Respects `alert_preferences.enabled = 0` (disabled users get no alerts)
- [ ] Uses ±1 day window around each threshold (e.g., threshold 30 matches 29, 30, or 31 days remaining)
- [ ] All existing tests still pass

## Hard Dependencies

- Task 112: alert_preferences table — must be DONE
- Task 113: alert_log table — must be DONE

## DB Changes

Reads `user_watchlist`, `contracts`, `alert_preferences`, `alert_log`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

`import json` (stdlib — already available).

## Testing

Add tests to `tests/test_celery_alerts.py` (new file):
- `test_check_alerts_empty_when_no_watchlist`: empty DB → returns [].
- `test_check_alerts_matches_threshold`: insert user, contract (30 days from now),
  watchlist row, alert_prefs with `[30]`; assert task returns one result.
- `test_check_alerts_deduplicates_via_alert_log`: insert existing `alert_log` row for
  same (user, contract, threshold); assert task returns [].
- `test_check_alerts_respects_min_value`: contract value below `min_value` → not returned.
- `test_check_alerts_respects_disabled_pref`: `enabled=0` → returns [].

## Suggested Commit Message

`feat: add check_watchlist_alerts Celery task (Task 117)`
