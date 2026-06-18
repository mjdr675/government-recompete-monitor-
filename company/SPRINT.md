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
| 1 | Opportunity Watchlists | DONE |
| 2 | Email Alerts | DONE |
| 3 | Export Filtered Results | DONE |
| 4 | Dashboard Improvements | DONE |

**Sprint status: COMPLETE** (2026-06-18)

---

## Completed Work

### Opportunity Watchlists — DONE (2026-06-18, commit 6186270)
- [x] watch/unwatch from contract detail page
- [x] `/watchlist` page with remove buttons
- [x] Dashboard shows up to 5 watched contracts with empty state
- [x] 18 tests; 106/106

### Email Alerts — DONE (2026-06-18, commit a91d32f)
- [x] `alerts.py` builds + sends via SMTP (ALERT_TO / SMTP_* env vars)
- [x] Covers watched contracts, priority upgrades, new opportunities
- [x] `/alerts` page for config + manual send trigger
- [x] 15 tests (SMTP mocked); 121/121

### Export Filtered Results — DONE (2026-06-18, commit af04f96)
- [x] `/contracts.csv` respects all filters, no pagination cap
- [x] Export CSV link on contracts page preserves current filters
- [x] 11 tests; 132/132

### Dashboard Improvements — DONE (2026-06-18, commit f9da58f)
- [x] Watchlist, Saved Searches, Alerts always visible after login
- [x] Empty-state prompts guide new users to each feature
- [x] Total contract count + alerts-configured badge on dashboard
- [x] 10 tests; 142/142

### Saved Searches — DONE (2026-06-18, commit dcf7e6e)
- [x] Save, load, rename, delete named contract searches
- [x] Persisted in `saved_searches` SQLite table
- [x] Dashboard quick-load links; global nav entry
- [x] 20 tests — full suite 77/77

### Min-value Filter — DONE (2026-06-18, commit 56f3a32)
- [x] `get_contracts()` accepts `min_value=None`; filters `c.value >= ?` when set
- [x] "High Value Contracts" view now correctly filters to contracts ≥ $1M
- [x] 11 tests — full suite 88/88
