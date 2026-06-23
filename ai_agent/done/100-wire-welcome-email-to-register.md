# Task 100 — Wire welcome email into register route

**Epic:** E08
**Milestone:** M3
**Sprint:** D-8
**Complexity:** S
**Status:** QUEUED

## Objective

Send a welcome email to every new user immediately after successful registration, via the Celery email task so the HTTP response is not blocked.

## Requirements

- In `auth.py`, after `session["user_id"] = user["id"]` on successful registration:
  - Import `send_email_task` from `tasks` (lazy import inside the `if` block to avoid circular import)
  - Render HTML and text bodies using `render_template`:
    ```python
    from flask import render_template
    from tasks import send_email_task
    app_url = os.environ.get("APP_URL", "https://govrecompete.com")
    html_body = render_template("email/welcome.html", user_email=email, app_url=app_url)
    text_body = render_template("email/welcome.txt", user_email=email, app_url=app_url)
    send_email_task.delay(to=email, subject="Welcome to Gov Recompete Monitor", html_body=html_body, text_body=text_body)
    ```
  - If `send_email_task.delay()` raises (e.g. Redis unavailable): catch `Exception`, log WARNING, continue — never block registration
- Add `APP_URL` to the list of env vars mentioned in `docs/ARCHITECTURE.md` (or leave for Task 094 docs update — either is fine)
- `os` is already imported in `auth.py`; if not, add it

## Acceptance Criteria

- [ ] Successful registration enqueues a Celery task (verify with mock)
- [ ] If Celery is unavailable (task raises), registration still succeeds (no 500)
- [ ] Existing registration tests still pass (welcome email is mocked/swallowed in test fixtures that don't have Redis)

## Hard Dependencies

- Task 097: send_email_task Celery task — must be DONE
- Task 099: welcome email template — must be DONE

## Testing

Add 2 tests to `tests/test_auth.py`:
- `test_registration_enqueues_welcome_email`: mock `tasks.send_email_task.delay`; assert it was called once with `to=<email>` after POST /register
- `test_registration_succeeds_if_email_task_raises`: mock `tasks.send_email_task.delay` to raise; assert registration still redirects to `/` (302)

## Suggested Commit Message

`feat: wire welcome email into register route (Task 100)`
