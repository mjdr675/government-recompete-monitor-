# Task 095 — Add email_service.py with send_email()

**Epic:** E08
**Milestone:** M3
**Sprint:** D-2
**Complexity:** S
**Status:** QUEUED

## Objective

Create a thin, mockable email sending module that all other email callers import.

## Requirements

- New file `email_service.py` at project root:
  ```python
  import logging
  import os
  import requests

  logger = logging.getLogger(__name__)

  def send_email(to: str, subject: str, html_body: str, text_body: str = "") -> dict | None:
      api_key = os.environ.get("EMAIL_API_KEY", "")
      from_addr = os.environ.get("SMTP_FROM", "noreply@govrecompete.com")
      if not api_key:
          logger.warning("EMAIL_API_KEY not set — email not sent to %s", to)
          return None
      resp = requests.post(
          "https://api.resend.com/emails",
          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
          json={"from": from_addr, "to": [to], "subject": subject,
                "html": html_body, "text": text_body or subject},
          timeout=10,
      )
      resp.raise_for_status()
      return resp.json()
  ```
- Provider: Resend (simple REST API, `EMAIL_API_KEY` is the Resend API key)
- Add `requests` to `requirements.txt` if not already present (check first)
- If `EMAIL_API_KEY` is not set: log WARNING, return `None` — do NOT raise
- If the HTTP call fails: let `requests.HTTPError` propagate to the caller

## Acceptance Criteria

- [ ] `send_email()` returns `None` when `EMAIL_API_KEY` is not set
- [ ] `send_email()` logs a WARNING when `EMAIL_API_KEY` is not set
- [ ] `send_email()` calls `requests.post` with correct URL and headers when key is set
- [ ] `send_email()` raises `HTTPError` on non-2xx response (no swallowing)
- [ ] All existing tests still pass

## Hard Dependencies

None.

## Testing

New file `tests/test_email_service.py`. Use `monkeypatch` to patch `requests.post`. Min 4 tests:
- `test_returns_none_when_no_api_key` (monkeypatch delenv EMAIL_API_KEY)
- `test_logs_warning_when_no_api_key` (caplog)
- `test_calls_resend_api_when_key_set` (mock requests.post, check call args)
- `test_raises_on_http_error` (mock requests.post to raise HTTPError)

## Suggested Commit Message

`feat: add email_service.py with send_email() via Resend API (Task 095)`
