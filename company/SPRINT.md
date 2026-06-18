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

## Next Highest-Value Feature Recommendation

**Add min_value filter to get_contracts()**  
(`TASK.md` — currently OPEN)

The "High Value Contracts" view in `views.py` passes `min_value: 1000000` as a
filter, but `get_contracts()` in `db.py` ignores it — so the view silently returns
all contracts. This is a correctness bug directly impacting the product's core
value proposition (surfacing high-value recompetes). It is small, well-scoped,
and completely described in `TASK.md`.

Runner-up: **Add /health unit test** — trivial, closes a gap in test coverage.
