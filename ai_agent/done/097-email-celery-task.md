# Task 097 — Add send_email_task Celery task

**Epic:** E08
**Milestone:** M3
**Sprint:** D-5
**Complexity:** S
**Status:** QUEUED

## Objective

Wrap `send_email()` in a Celery task so email sends are non-blocking and automatically retried on transient failure.

## Requirements

- In `tasks.py`, add a new task:
  ```python
  @tasks.task(name="tasks.send_email_task", bind=True, max_retries=3, default_retry_delay=60)
  def send_email_task(self, to: str, subject: str, html_body: str, text_body: str = ""):
      from email_service import send_email
      try:
          result = send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
          if result is None:
              logger.warning("send_email_task: EMAIL_API_KEY not set, skipping send to %s", to)
          return result
      except Exception as exc:
          logger.error("send_email_task failed (to=%s): %s", to, exc)
          raise self.retry(exc=exc)
  ```
- Import is inside the function to avoid circular import at module load time
- Do NOT add to `beat_schedule` — this task is called on-demand, not scheduled

## Acceptance Criteria

- [ ] `send_email_task` is registered in the Celery app
- [ ] Calling `.apply()` with a mocked `send_email` succeeds without error
- [ ] If `send_email` raises, task retries (verify `max_retries=3` is set)
- [ ] If `send_email` returns None (no key), task completes without raising
- [ ] All existing tests still pass

## Hard Dependencies

- Task 095: email_service.py — must be DONE

## Testing

New test class `TestSendEmailTask` in `tests/test_celery_ingest.py` (or new file `tests/test_email_task.py`). Use `monkeypatch` to patch `email_service.send_email`. Min 3 tests:
- `test_send_email_task_calls_send_email`
- `test_send_email_task_returns_none_when_no_key` (mock returns None)
- `test_send_email_task_is_registered`

## Suggested Commit Message

`feat: add send_email_task Celery task (Task 097)`
