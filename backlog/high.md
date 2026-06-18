# High Priority Backlog

Important features and fixes — do after critical items.

---

### [DONE] Contract comparison page
Add a `/compare` route and `templates/compare.html` showing two contracts side by side:
agency, vendor, value, end date, priority, recompete_score. Add checkboxes to the
contracts list so users can select two and click "Compare".
Role: frontend

### [OPEN] Add min_value filter to get_contracts()
`get_contracts()` in `db.py` has no `min_value` param so the High Value
Contracts view silently returns all contracts. Add `min_value=None` param,
filter with `AND c.value >= ?` when set, pass `request.args.get('min_value')`
through the `/contracts` route in `app.py`.
Role: backend

### [OPEN] Add /health unit test
Create `tests/test_health.py` that imports the Flask app and asserts
`GET /health` returns 200 with `{"status": "ok"}`.
Role: qa

### [OPEN] Ingest logging
Write subprocess stdout and stderr to `ingest.log` instead of `DEVNULL`.
Add a `GET /ingest/status` route returning the last 50 lines as plain text.
Role: backend
