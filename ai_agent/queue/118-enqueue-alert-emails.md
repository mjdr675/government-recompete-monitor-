# Task 118 — Enqueue alert emails from check_watchlist_alerts()

**Epic:** E03
**Milestone:** M3
**Sprint:** E-5
**Complexity:** S
**Status:** QUEUED

## Objective

Wire the output of `check_watchlist_alerts()` (Task 117) into the email queue: for each
pending alert, generate unsubscribe token if needed, render the alert email, enqueue via
`send_email_task`, and write to `alert_log` to prevent re-sends.

## Requirements

- Extend `check_watchlist_alerts()` in `tasks.py` after its query phase:
  - For each pending `(user_id, contract_id, days_threshold, user_email)` result:
    1. Look up or generate `unsubscribe_token` for the user in `alert_preferences`:
       if `unsubscribe_token IS NULL`, generate with `secrets.token_urlsafe(24)` and
       write it to `alert_preferences` immediately.
    2. Build `contract_url = f"{APP_URL}/contracts/{contract_id}"`.
    3. Build `unsubscribe_url = f"{APP_URL}/unsubscribe?token={unsubscribe_token}"`.
    4. Call `send_email_task.delay(to=user_email, subject=f"Contract expiring in {days_threshold} days: {contract_title}", html_body=..., text_body=...)` using the templates from Task 115.
    5. Insert into `alert_log (user_id, contract_id, days_threshold)`.
  - Use `INSERT OR IGNORE` (SQLite) / `INSERT … ON CONFLICT DO NOTHING` (PostgreSQL)
    for the `alert_log` insert as a race-condition safety net.
- `APP_URL` should be read from `os.environ.get("APP_URL", "https://localhost:5000")`.

## Acceptance Criteria

- [ ] `send_email_task.delay()` called once per pending alert
- [ ] `alert_log` row written after email enqueued
- [ ] `unsubscribe_token` generated and persisted if not already set
- [ ] Second run of task does not re-send alerts already in `alert_log`
- [ ] All existing tests still pass

## Hard Dependencies

- Task 113: alert_log table — must be DONE
- Task 115: expiration alert email template — must be DONE
- Task 117: check_watchlist_alerts() Celery task — must be DONE
- Task 097: send_email_task Celery task — must be DONE

## DB Changes

Writes `alert_log`. Writes `alert_preferences.unsubscribe_token`.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

`import secrets` (stdlib).

## Testing

Extend `tests/test_celery_alerts.py`:
- `test_enqueue_alert_sends_email`: set up matching contract + prefs; run task;
  monkeypatch `send_email_task.delay`; assert called once with correct `to` address.
- `test_enqueue_alert_writes_alert_log`: after task run, query `alert_log`; assert one row.
- `test_enqueue_alert_generates_unsubscribe_token`: after run, `alert_preferences.unsubscribe_token`
  is non-null.
- `test_enqueue_alert_idempotent`: run task twice; assert `send_email_task.delay` called
  only once (second run blocked by `alert_log`).

## Suggested Commit Message

`feat: enqueue expiration alert emails and write alert_log (Task 118)`
