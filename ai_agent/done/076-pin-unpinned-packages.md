# Task 076 — Pin unpinned packages in requirements.txt

**Epic:** E05  
**Milestone:** M3  
**Complexity:** XS  
**Status:** QUEUED

## Objective

`requirements.txt` has three unpinned entries: `celery`, `redis`, and `sqlalchemy>=2.0`.
Unpinned packages create non-reproducible builds — a future `pip install` can pull a
breaking version. Pin them to the currently-installed versions.

## Requirements

- Change `celery` → `celery==5.6.3`
- Change `redis` → `redis==8.0.0`
- Change `sqlalchemy>=2.0` → `SQLAlchemy==2.0.51`
- Do not change any other line in requirements.txt

## Acceptance Criteria

- [ ] `requirements.txt` contains no bare/range-pinned entries for celery, redis, or sqlalchemy
- [ ] `pip install -r requirements.txt` completes without error
- [ ] Full test suite passes

## Hard Dependencies

None — standalone housekeeping task.

## DB / API / Frontend Changes

None.

## New Dependencies

None.

## Testing

Run `pip install -r requirements.txt` and `python3 -m pytest tests/test_auth.py tests/test_app.py -q`.

## Documentation

None.

## Suggested Commit Message

`chore: pin celery, redis, and SQLAlchemy versions in requirements.txt (Task 076)`
