# Task 121 — Trigger status change alert in change_detector.py

**Epic:** E03
**Milestone:** M3
**Sprint:** E-10
**Complexity:** S
**Status:** QUEUED

## Objective

When `change_detector.py` detects that a watched contract's recompete priority or status
has changed, enqueue a status change alert email to the watching user using the template
from Task 116.

## Requirements

- Locate `change_detector.py` (or equivalent module that compares contract snapshots).
- After a change is detected for a contract that appears in `user_watchlist`, for each
  watching user:
  1. Check `alert_preferences.enabled = 1` for that user (skip if disabled).
  2. Look up the user's email from `users`.
  3. Look up `alert_preferences.unsubscribe_token`; if `None`, generate with
     `secrets.token_urlsafe(24)` and write to `alert_preferences`.
  4. Build `contract_url`, `unsubscribe_url`.
  5. Call `send_email_task.delay(...)` with the `status_change.html` / `.txt` templates
     from Task 116, passing `old_status`, `new_status`, `contract_title`, `agency`,
     `expiry_date`, `contract_url`, `unsubscribe_url`.
- Do not write to `alert_log` for status change alerts — these are event-driven, not
  threshold-based, and each status change is a distinct event.

## Acceptance Criteria

- [ ] Status change for a watched contract triggers `send_email_task.delay()` for each watcher
- [ ] Users with `alert_preferences.enabled = 0` are skipped
- [ ] Contracts not in any user's watchlist generate no email
- [ ] Unsubscribe token generated if absent
- [ ] All existing change_detector tests still pass

## Hard Dependencies

- Task 112: alert_preferences table — must be DONE
- Task 116: status change alert email template — must be DONE
- Task 118: enqueue alert emails (establishes unsubscribe_token pattern) — must be DONE

## DB Changes

Reads `user_watchlist`, `alert_preferences`, `users`. Writes `alert_preferences.unsubscribe_token` if null.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add tests to `tests/test_change_detector.py` (new file if absent):
- `test_status_change_triggers_alert`: insert user, contract, watchlist row, alert_prefs
  (enabled=1); simulate a status change event; monkeypatch `send_email_task.delay`;
  assert called once with correct `old_status` and `new_status` in html_body.
- `test_status_change_skips_disabled_user`: `alert_preferences.enabled=0`; assert
  `send_email_task.delay` not called.
- `test_status_change_no_watchers`: no watchlist row for contract; assert no email.

## Suggested Commit Message

`feat: trigger status change alert email in change_detector (Task 121)`
