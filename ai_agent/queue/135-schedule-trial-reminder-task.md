# Task 135 — Schedule trial reminder Celery task

**Epic:** E10
**Milestone:** M3
**Sprint:** F-13
**Complexity:** S
**Status:** QUEUED

## Objective

Implement and schedule the Celery task that checks all users in trial each day and sends
the correct reminder email based on days remaining (day 3 → 11 days left, day 10 → 4 days
left, day 14 → expired).

## Requirements

- In `tasks.py`, add:
  ```python
  @celery.task(name="tasks.send_trial_reminders")
  def send_trial_reminders():
  ```
  - Query `users WHERE subscription_status = 'trialing' AND trial_ends_at IS NOT NULL`.
  - For each user, compute `days_remaining = (trial_ends_at - today).days`.
  - Send appropriate email:
    - `days_remaining == 11` → enqueue `trial_day3.html` template (Task 132)
    - `days_remaining == 4` → enqueue `trial_day10.html` template (Task 133)
    - `days_remaining <= 0` → enqueue `trial_expired.html` template (Task 134);
      update `users.subscription_status = 'inactive'`
  - All emails sent via `send_email_task.delay(...)`.
  - Log `INFO` with count of emails enqueued.
- Add to `beat_schedule`:
  ```python
  "send-trial-reminders-daily": {
      "task": "tasks.send_trial_reminders",
      "schedule": crontab(hour=8, minute=0),
  },
  ```

## Acceptance Criteria

- [ ] User with 11 days remaining gets day-3 email
- [ ] User with 4 days remaining gets day-10 email
- [ ] User with 0 days remaining gets expired email and `subscription_status` set to `'inactive'`
- [ ] Users with active subscriptions (`subscription_status='active'`) are not emailed
- [ ] Task appears in beat schedule at 08:00 UTC
- [ ] All existing tests still pass

## Hard Dependencies

- Task 124: trial_ends_at column — must be DONE
- Task 125: wire trial on registration — must be DONE
- Task 132: trial day-3 template — must be DONE
- Task 133: trial day-10 template — must be DONE
- Task 134: trial expiry template — must be DONE

## DB Changes

Updates `users.subscription_status` to `'inactive'` for expired trials.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

`from datetime import datetime, timezone` (stdlib).

## Testing

Add tests to `tests/test_trial_reminders.py` (new file):
- `test_trial_reminder_day3_sends_correct_template`: user with `trial_ends_at` 11 days out;
  run task; monkeypatch `send_email_task.delay`; assert called with day-3 template content.
- `test_trial_reminder_day10_sends_correct_template`: 4 days out; assert day-10 template.
- `test_trial_reminder_expired_sends_expiry_and_sets_inactive`: 0 days; assert expiry email
  enqueued and `subscription_status` set to `'inactive'`.
- `test_trial_reminder_skips_active_subscription`: user with `subscription_status='active'`;
  assert no email sent.
- `test_trial_reminders_in_beat_schedule`: `beat_schedule` contains
  `tasks.send_trial_reminders` at hour=8.

## Suggested Commit Message

`feat: add send_trial_reminders Celery task scheduled daily at 08:00 UTC (Task 135)`
