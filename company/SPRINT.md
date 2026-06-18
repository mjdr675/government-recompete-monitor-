# Sprint Status

## Current Sprint — Saved Searches

**Goal:** Allow logged-in users to save, load, rename, and delete named contract searches.

**Status:** COMPLETE (2026-06-18, commit dcf7e6e)

### Delivered
- [x] Logged-in users can save searches from the Contracts page
- [x] Saved searches persist in the `saved_searches` SQLite table
- [x] Users can rename searches (inline form on Saved Searches page)
- [x] Users can delete searches (with confirmation dialog)
- [x] Users can load searches (redirects to `/contracts` with filters applied)
- [x] Dashboard shows saved searches quick-load links
- [x] "Saved Searches" added to global navigation
- [x] 20 tests added — all passing; full suite 77/77

---

## Min-value Filter — DONE (2026-06-18)

- [x] `get_contracts()` accepts `min_value=None`; filters `c.value >= ?` when set
- [x] `/contracts` route reads `request.args.get('min_value')` and passes it through
- [x] "High Value Contracts" view now correctly filters to contracts ≥ $1M
- [x] 11 new tests — all passing; full suite 88/88

---

## Next Highest-Value Feature Recommendation

**Add /health unit test** (`TASK.md` — OPEN)  
Trivial one-file addition that closes a test-coverage gap on the health endpoint.

Runner-up: **Human-readable labels in views.html** — polish item, low effort.
