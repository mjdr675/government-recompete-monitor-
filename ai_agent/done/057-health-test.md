# Task 057 — Add /health unit test

**Epic:** E01
**Milestone:** M1
**Complexity:** XS
**Status:** QUEUED

## Objective
Create `tests/test_health.py` with a basic health check test so that CI catches any
regression that breaks the health endpoint. The `/health` route must remain publicly
accessible (no auth required) and must return a well-formed JSON response.

## Requirements
- Create `tests/test_health.py`
- Import the Flask test client using the same fixture pattern as `tests/test_app.py`
- Assert `GET /health` returns HTTP 200
- Assert the response body is valid JSON with `{"status": "ok"}`
- Assert the route is accessible without a session cookie (unauthenticated request)

## Acceptance Criteria
- [ ] `tests/test_health.py` exists with at least 2 tests
- [ ] Both tests pass with `pytest -q`
- [ ] Test verifies unauthenticated access returns 200 (not redirect to login)
- [ ] Test verifies response body contains `{"status": "ok"}`
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None

## API Changes
- None (existing `/health` route; no changes to application code)

## Frontend Changes
- None

## New Dependencies (requirements.txt)
- None

## Suggested Commit Message
`test: add /health endpoint unit tests (Task 057)`
