# Task 075 — Add rate limiting to /login route

**Epic:** E05  
**Milestone:** M3  
**Complexity:** S  
**Status:** QUEUED

## Objective

`POST /login` has no rate limiting. An attacker can attempt unlimited password guesses
without any throttling. Add per-IP rate limiting using Flask-Limiter: maximum 5 POST
attempts per minute on `/login`. On limit exceeded, return 429 with a human-readable
error message.

## Requirements

- Add `Flask-Limiter` to `requirements.txt` (pinned, e.g. `Flask-Limiter==3.9.0`)
- Add `limits` to `requirements.txt` if not already present (Flask-Limiter dependency)
- In `app.py`:
  - Import `from flask_limiter import Limiter` and `from flask_limiter.util import get_remote_address`
  - Initialize: `limiter = Limiter(app, key_func=get_remote_address, default_limits=[])`
    (empty default — apply limits explicitly, not globally)
  - Apply limit to the login route only: `@limiter.limit("5 per minute")` on `auth.login`
    via `limiter.limit("5 per minute", per_method=True, methods=["POST"])`
- When the limit is exceeded, Flask-Limiter returns 429 automatically
- Do NOT rate-limit GET `/login` (showing the form must never be blocked)
- Do NOT apply default limits globally — only `/login` POST is rate limited at this stage

## Acceptance Criteria

- [ ] `Flask-Limiter` appears in `requirements.txt` at a pinned version
- [ ] `POST /login` returns 429 after 5 failed attempts within 60 seconds from the same IP
- [ ] `GET /login` is never rate limited
- [ ] The 429 response body is human-readable (not a raw JSON error)
- [ ] Limit resets after the 60-second window expires
- [ ] All existing `tests/test_auth.py` tests pass (rate limiter disabled in tests — see Testing)
- [ ] New test: 6 consecutive POST requests to `/login` — assert the 6th returns 429

## Hard Dependencies

- Task 071: CSRF infrastructure — must be DONE (rate limiter test setup requires CSRF disabled)

## DB Changes

None.

## API Changes

- `POST /login` — returns 429 after 5 attempts per minute per IP

## Frontend Changes

None — Flask-Limiter's default 429 response is sufficient for now.

## New Dependencies (requirements.txt)

- `Flask-Limiter==3.9.0` (or latest stable — pin the installed version)

## Testing

Flask-Limiter must be disabled or use memory storage in tests to avoid cross-test pollution.
In the test app fixture, set: `app.config["RATELIMIT_ENABLED"] = False`

Add to `tests/test_auth.py`:
- `test_login_rate_limited`: enable limiter in a dedicated fixture, POST `/login` 6 times, assert 6th is 429

## Documentation

Update `docs/ARCHITECTURE.md` — Routes table: note rate limit on `POST /login`.

## Suggested Commit Message

`feat: add rate limiting to /login — 5 POST attempts per minute per IP (Task 075)`
