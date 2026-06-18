# Sprint Status

## Current Sprint

**Goal:** Become useful enough that a real government contractor would use the product every day.

### Priority Order
1. Opportunity Watchlists
2. Email Alerts
3. Export CSV
4. Dashboard Improvements

### Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Opportunity Watchlists | OPEN |
| 2 | Email Alerts | OPEN |
| 3 | Export Filtered Results | OPEN |
| 4 | Dashboard Improvements | OPEN |

---

## Completed Work

### Saved Searches — DONE (2026-06-18, commit dcf7e6e)
- [x] Save, load, rename, delete named contract searches
- [x] Persisted in `saved_searches` SQLite table
- [x] Dashboard quick-load links; global nav entry
- [x] 20 tests — full suite 77/77

### Min-value Filter — DONE (2026-06-18, commit 56f3a32)
- [x] `get_contracts()` accepts `min_value=None`; filters `c.value >= ?` when set
- [x] "High Value Contracts" view now correctly filters to contracts ≥ $1M
- [x] 11 tests — full suite 88/88
