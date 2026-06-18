# HANDOFF.md — Agent Run Log

The agent appends a summary here after each run.
Most recent run is at the bottom.

---

<!-- Agent writes entries below this line -->

## 2026-06-18 20:12 UTC — Add min_value filter to get_contracts()
**Status:** dry-run / plan only

**Plan:**
[PLAN STUB] Connect an AI API to generate a real plan.

**Git status after run:**
```
M .gitignore
 M janitorial_recompete_report.csv
?? HANDOFF.md
?? TASK.md
?? ai_agent/
```

## 2026-06-18 20:17 UTC — [QA] Auth bypass on /health exposes info to unauthenticated users
**Source:** critical.md  
**Assigned to:** qa  
**Status:** plan generated (dry-run)

**Plan:**
[QA STUB] Plan for: Auth bypass on /health exposes info to unauthenticated users
Steps would be generated here by the AI API.
Files likely involved: tests/

---

## 2026-06-18 — Implement Saved Searches
**Status:** COMPLETE  
**Commit:** dcf7e6e

**Changes:**
- `db.py` — new `saved_searches` table + CRUD: `create_saved_search`, `get_saved_searches`, `get_saved_search`, `rename_saved_search`, `delete_saved_search`
- `app.py` — 5 new routes: `GET /saved-searches`, `POST /saved-searches/save`, `GET /saved-searches/<id>/load`, `POST /saved-searches/<id>/rename`, `POST /saved-searches/<id>/delete`; dashboard route now passes `saved_searches` context
- `templates/saved_searches.html` — new page listing all searches with inline rename + delete forms
- `templates/contracts.html` — "Save Search" form above results; link to saved searches management
- `templates/dashboard.html` — quick-load links for saved searches at top of page
- `templates/base.html` — "Saved Searches" added to global nav
- `tests/test_saved_searches.py` — 20 tests (8 db-layer, 12 HTTP routes), all passing

**Test results:** 77/77 passed

---

## 2026-06-18 — Add min_value filter to get_contracts()
**Status:** COMPLETE

**Changes:**
- `db.py` — `get_contracts()` now accepts `min_value=None`; appends `AND c.value >= ?` when set
- `app.py` — `/contracts` reads `request.args.get('min_value')`, converts to float, passes to `get_contracts()`, and echoes back as `min_value` template context
- `tests/test_min_value_filter.py` — 11 new tests: boundary conditions, combined filters, pagination, and HTTP route behaviour

**Test results:** 88/88 passed

---

## 2026-06-18 — Planning reorganization: sprint vs. maintenance separation

**Status:** COMPLETE (no application changes)

**What changed:**
- `MAINTENANCE.md` created — holds all maintenance work (test coverage, logging, UI polish, etc.). Tasks migrated from old TASK.md with their original statuses preserved.
- `TASK.md` rewritten — now contains only active customer-facing sprint tasks (Watchlists, Email Alerts, Export CSV, Dashboard Improvements). No maintenance tasks.
- `company/SPRINT.md` updated — new sprint goal ("useful enough that a real contractor uses it daily"), priority-ordered task list, completed history section.
- `company/CEO.md` created — records the engineering principle: customer-facing value before maintenance; maintenance only when blocking a feature, fixing a production bug, or the sprint queue is empty.

**Workflow going forward:**
1. Work TASK.md top to bottom — these are sprint tasks only.
2. When TASK.md is empty, consult MAINTENANCE.md for the next maintenance item.
3. Never do maintenance while sprint tasks remain unless it directly blocks progress.

---

## 2026-06-18 — Sprint: Watchlists / Email Alerts / Export CSV / Dashboard
**Status:** ALL FOUR TASKS COMPLETE

| Task | Commit | Tests added | Suite |
|------|--------|-------------|-------|
| Opportunity Watchlists | 6186270 | 18 | 106/106 |
| Email Alerts | a91d32f | 15 | 121/121 |
| Export Filtered Results | af04f96 | 11 | 132/132 |
| Dashboard Improvements | f9da58f | 10 | 142/142 |

**Key files changed:**
- `db.py` — `watchlist` table + CRUD; `get_contracts(all_rows=True)` flag
- `app.py` — `/watchlist`, `/watch/<id>`, `/unwatch/<id>`, `/alerts`, `/contracts.csv` routes; dashboard passes `total_contracts` + `alert_configured`
- `alerts.py` — new module; SMTP email builder + sender
- `templates/` — `watchlist.html`, `alerts.html`; updated `base.html`, `contract_detail.html`, `contracts.html`, `dashboard.html`
- `tests/` — `test_watchlist.py`, `test_alerts.py`, `test_export_csv.py`, `test_dashboard.py`

**TASK.md is now empty.** Maintenance work available in MAINTENANCE.md.

---

## 2026-06-18 — Sprint 4: Vendor Intelligence Dashboard
**Status:** COMPLETE

**New files:**
- `charts.py` — reusable Chart.js data formatters: `bar_chart`, `pie_chart`, `priority_pie`, `agency_bar`, `monthly_bar`
- `templates/vendor.html` — full rewrite; 7 summary cards, risk banner, 3 charts, agency breakdown, upcoming recompetes table, CSS timeline, related vendors
- `tests/test_vendor_intelligence.py` — 54 tests across 7 test classes

**Modified files:**
- `analytics.py` — `vendor_profile_analytics` completely replaced: 7-card extended summary, agency breakdown with pipeline_value + avg_score, full upcoming list (no 10-row cap), chart data via charts.py, risk indicators, related vendors; single connection, no duplicate SQL
- `templates/base.html` — added `{% block scripts %}` hook for page-specific JS

**Test results:** 196/196 passed
