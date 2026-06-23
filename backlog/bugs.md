# Bug Backlog

Confirmed bugs — triage and fix promptly.

---

### [DONE] FTS rebuild not called after save_snapshot()
`save_snapshot()` in `db.py` inserts rows via raw SQL, bypassing the FTS
triggers. After the loop, open a new connection and run:
  `INSERT INTO contracts_fts(contracts_fts) VALUES ('rebuild')`
then commit. Without this, full-text search returns stale results after
a CSV ingest.
Role: backend

### [DONE] Days-remaining filter accepts negative values
`/contracts?days=-1` passes `-1` to `get_contracts()`, which returns all
contracts with `days_remaining <= -1` — i.e. expired contracts silently.
Add a `max(0, days)` guard or return 400 for negative values.
Role: backend
