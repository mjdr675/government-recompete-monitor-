# TASK.md — Agent Work Queue

Each task should be self-contained and small. The agent picks the first OPEN task,
works on it, marks it DONE, and writes a summary to HANDOFF.md.

## Format

```
### [STATUS] Short title
Description of what to do.
```

STATUS values: OPEN | IN_PROGRESS | DONE | SKIPPED

---

### [OPEN] Add min_value filter to get_contracts()
`get_contracts()` in `db.py` has no `min_value` param so the High Value Contracts
view silently returns all contracts. Add `min_value=None` param, filter with
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
