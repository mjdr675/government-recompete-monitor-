# Sprint Status

## Sprint 4 — Vendor Intelligence Dashboard — COMPLETE (2026-06-18)

**Goal:** Rich vendor profile page that helps capture managers quickly understand an incumbent contractor.

### Delivered
- [x] 7 summary cards: Active Contracts, Pipeline Value, Avg Score, Critical Contracts, Avg Days Remaining, Earliest/Latest Expiration
- [x] Agency Breakdown table: agency, contracts, pipeline value, avg score — sorted by pipeline value
- [x] Upcoming Recompetes table: full list, soonest first, rows highlighted red when <90 days
- [x] Expiration Timeline: CSS visual, soonest at top, bar width proportional to contract value
- [x] 3 Chart.js charts: Pipeline Value by Agency, Contracts by Priority (doughnut), Expiring per Month
- [x] Risk Indicators banner: <90-day expiries, critical contracts, multi-recompete agencies, largest contract
- [x] Related Vendors section: competitors sharing the same agencies
- [x] `charts.py` reusable helper module (bar_chart, pie_chart, priority_pie, agency_bar, monthly_bar)
- [x] Single-connection analytics, no duplicate SQL
- [x] 54 new tests; full suite 196/196

---

## Previous Sprint — Customer Features

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
