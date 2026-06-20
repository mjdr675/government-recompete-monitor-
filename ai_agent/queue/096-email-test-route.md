# Task 096 — Add /ingest/email-test admin route

**Epic:** E08
**Milestone:** M3
**Sprint:** D-4
**Complexity:** XS
**Status:** QUEUED

## Objective

Give admins a one-click way to verify email delivery is working in production.

## Requirements

- New `GET /ingest/email-test` route in `app.py` (login required via `require_login`):
  - Calls `send_email(to=g.user["email"], subject="Test email — Gov Recompete Monitor", html_body="<p>Email delivery is working.</p>", text_body="Email delivery is working.")`
  - Import `send_email` from `email_service` at the top of `app.py`
  - If `send_email` returns `None` (no API key): return `jsonify({"ok": False, "error": "EMAIL_API_KEY not set"}), 503`
  - If `send_email` raises: catch `Exception`, return `jsonify({"ok": False, "error": str(exc)}), 500`
  - On success: return `jsonify({"ok": True, "to": g.user["email"]})`

## Acceptance Criteria

- [ ] `GET /ingest/email-test` returns 200 JSON `{"ok": true}` when send_email returns a dict
- [ ] Returns 503 when EMAIL_API_KEY is not set (send_email returns None)
- [ ] Returns 500 when send_email raises
- [ ] Unauthenticated request redirects to /login (302)

## Hard Dependencies

- Task 095: email_service.py — must be DONE

## Testing

Add 3 tests to `tests/test_app.py` using `monkeypatch` to patch `email_service.send_email`:
- `test_email_test_returns_ok_when_send_succeeds`
- `test_email_test_returns_503_when_no_api_key` (mock returns None)
- `test_email_test_returns_500_when_send_raises`

## Suggested Commit Message

`feat: add /ingest/email-test admin route (Task 096)`
