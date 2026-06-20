# Task 058 — Add ingest logging and /ingest/status route

**Epic:** E01
**Milestone:** M1
**Complexity:** S
**Status:** QUEUED

## Objective
Capture stdout/stderr from the SAM.gov API pull subprocess into a rotating log file and
expose the last 50 lines through a new authenticated route. Users and operators currently
have no way to verify whether ingest ran or diagnose failures. This is a carry-forward
backlog item.

## Requirements
- Redirect the `recompete_report.py` subprocess stdout and stderr to `ingest.log` in the
  app working directory using `subprocess.PIPE` capture and write to a `RotatingFileHandler`
  (max size 1 MB, 3 backups)
- Create `GET /ingest/status` route in `app.py` (or the ingest blueprint)
- Route reads the last 50 lines from `ingest.log` and returns them as `text/plain; charset=utf-8`
- Route requires authentication (redirect to `/login` if no session)
- Add a "View log" link to `templates/ingest.html` pointing to `/ingest/status`

## Acceptance Criteria
- [ ] After triggering an API pull, `/ingest/status` shows the log output
- [ ] Route returns HTTP 200 with `Content-Type: text/plain`
- [ ] Unauthenticated request to `/ingest/status` redirects to `/login`
- [ ] Log file rotates at 1 MB (existing content not lost — backup kept)
- [ ] "View log" link visible on `ingest.html`
- [ ] All existing tests still pass
- [ ] New tests pass

## Hard Dependencies
- None

## DB Changes
- None

## API Changes
- Route: `GET /ingest/status` — returns last 50 lines of `ingest.log` as `text/plain`

## Frontend Changes
- Template: `templates/ingest.html` — add "View log" link to `/ingest/status`

## New Dependencies (requirements.txt)
- None (`logging.handlers.RotatingFileHandler` is stdlib)

## Suggested Commit Message
`feat: add ingest logging and /ingest/status route (Task 058)`
