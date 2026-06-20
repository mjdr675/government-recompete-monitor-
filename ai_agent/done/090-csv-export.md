# Task 090 — Add CSV export from /contracts

**Epic:** E06
**Milestone:** M3
**Sprint:** B-13
**Complexity:** S
**Status:** QUEUED

## Objective

Users can download the current filtered contract result set as a CSV file.

## Requirements

- New `GET /contracts/export.csv` route in `app.py` (login required via require_login):
  - Accepts same query params as `/contracts`: `q`, `agency`, `priority`, `days`, `min_value`, `sort`, `dir`
  - Calls `get_contracts()` with `limit=10000` (no pagination — export all matching rows)
  - Streams response as `text/csv` with `Content-Disposition: attachment; filename="contracts.csv"`
  - Columns: `internal_id, award_id, vendor, agency, value, end_date, days_remaining, priority, recompete_score`
  - Use Python `csv.DictWriter` with `io.StringIO`; return `Response(output.getvalue(), mimetype="text/csv", headers={...})`
- In `templates/contracts.html`:
  - Add a "Export CSV" link below the filter form: `<a href="/contracts/export.csv?{{ request.query_string.decode() }}">Export CSV</a>`
  - Only visible to `{% if g.user %}`

## Acceptance Criteria

- [ ] `GET /contracts/export.csv` returns 200 with `text/csv` content type
- [ ] Response has `Content-Disposition: attachment; filename="contracts.csv"`
- [ ] CSV has correct column headers
- [ ] Filter params are respected (e.g. `?priority=Critical` only exports Critical contracts)
- [ ] Unauthenticated request redirects to /login
- [ ] All existing tests still pass

## Hard Dependencies

- None beyond existing contracts route (Task sprint A — DONE)

## Testing

Add tests to `tests/test_app.py`: `test_csv_export_returns_csv`, `test_csv_export_has_correct_headers`, `test_csv_export_redirects_when_not_logged_in`.

## Suggested Commit Message

`feat: add CSV export from /contracts (Task 090)`
