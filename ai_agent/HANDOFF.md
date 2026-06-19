# Current Status

Repository is running on a Hetzner VPS.

Claude Code is authenticated.

Python environment works.

All tests currently pass (87 passed as of 2026-06-19).

The objective is to safely improve this repository through small, production-quality commits.

## Last completed task

Fixed the negative days filter bug on `/contracts`. Commit: `f4b8959`.

## Next candidates

- **FTS rebuild after save_snapshot()** (`backlog/bugs.md`) — `save_snapshot()` bypasses FTS triggers; needs a manual rebuild call after ingest.
- **SQLite data-loss warning on Railway** (`backlog/critical.md`) — add a startup log warning when no persistent volume is detected.
