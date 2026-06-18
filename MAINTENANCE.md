# MAINTENANCE.md — Maintenance Work Queue

Maintenance tasks: test coverage, logging, documentation, cleanup, UI polish,
labels, refactors, developer tooling, and internal improvements.

**Rule:** Complete all TASK.md sprint work before selecting from this list.
Maintenance is performed only when it blocks a feature, fixes a production bug,
or there are no remaining sprint tasks.

## Format

```
### [STATUS] Short title
Description of what to do.
```

STATUS values: OPEN | IN_PROGRESS | DONE | SKIPPED

---

### [DONE] Add min_value filter to get_contracts()
`get_contracts()` in `db.py` had no `min_value` param so the High Value Contracts
view silently returned all contracts. Added `min_value=None` param, filter with
`AND c.value >= ?` when set, and pass `request.args.get('min_value')` through
the `/contracts` route in `app.py`.

### [OPEN] Add /health unit test
Create `tests/test_health.py` that imports the Flask app and asserts `GET /health`
returns 200 with `{"status": "ok"}`.

### [OPEN] Human-readable labels in views.html
`views.html` displays raw dict keys like `days: 90`. Replace with friendly labels
like `Expiring within: 90 days`.

### [OPEN] Ingest logging
Write subprocess stdout and stderr to `ingest.log` instead of `DEVNULL`.
Add a `GET /ingest/status` route returning the last 50 lines as plain text.
