# Task Log

## 2026-06-19 — Task 042: Customer Dashboard

**Task:** Build a useful customer-facing dashboard landing page.

**Changes:**
- `analytics.py`: Added `dashboard_analytics(con)` — platform summary (total_pipeline, total_contracts, active_contracts, critical_contracts, avg_score), upcoming expirations (next 90 days), critical active contracts, top 5 agencies and vendors by pipeline.
- `app.py`: Updated `dashboard()` route to call `dashboard_analytics(con)` and pass `analytics` to template alongside existing `report`.
- `templates/dashboard.html`: Full rewrite — 5 platform summary cards, quick-nav action buttons, Critical Opportunities section, Upcoming Expirations, Recommended Opportunities (top score), Recent Changes, side-by-side Top Agencies + Top Vendors.

**Tests added:** 13 tests in `tests/test_app.py` covering all sections and key data checks.

**Result:** 146 passed (was 133). Not pushed.

---

## 2026-06-19 — Task 041: Agency Intelligence

**Task:** Bring agency profile page to full Vendor Intelligence quality parity.

**Changes:**
- `analytics.py`: Expanded `agency_profile()` to return `active`, `timeline`, `win_loss_summary`, `change_events`, `score_distribution`, `pipeline_by_priority` alongside enriched `summary` (active_contracts, expired_contracts, max_score, platform_avg_score) and `vendors` (active_contracts, top_score).
- `templates/agency.html`: Full rewrite matching `vendor.html` — 7 summary cards, active contracts table, timeline bar chart, win/loss indicators, score analysis, priority doughnut + table, vendor leaderboard with share %, enhanced upcoming expirations with urgency coloring, overflow-x:auto wrappers.

**Tests added:** 18 tests in `tests/test_app.py` covering all new sections.

**Result:** 133 passed (was 115). Not pushed.

---

## 2026-06-19 — Fix FTS rebuild not called after save_snapshot()

**Bug:** `save_snapshot()` uses `INSERT ... ON CONFLICT DO UPDATE` which fires `AFTER INSERT` triggers (not `AFTER UPDATE`), so `contracts_au` never runs during ingest. Stale FTS entries accumulate, causing full-text search to return wrong or missing results.

**Fix:** Added `INSERT INTO contracts_fts(contracts_fts) VALUES ('rebuild')` at the end of the ingest loop in `save_snapshot()` (`db.py`), before the final commit.

**Tests added:** 5 tests in `tests/test_db.py` — vendor/agency FTS search, upsert update reflected in FTS, empty id skipped, multi-row all searchable.

**Result:** 115 passed (was 110). Committed as `12d722c`. Backlog item marked [DONE].

---

## 2026-06-19 — Build production Vendor Intelligence page

**Task:** Full vendor intelligence page with all required sections.

**Commits (12):** a8531b5 → d7c95eb

| Commit | Description |
|---|---|
| a8531b5 | Baseline vendor profile route tests |
| f3d5620 | Add `{% block scripts %}` to base.html |
| 8ba578f | Responsive CSS + table scroll wrappers |
| 048ddab | Expand summary cards (active/expired/max_score) |
| 12cb83a | Enhance agency breakdown (value, share, top score) |
| b011b27 | Enhance upcoming recompetes (competition type, urgency) |
| 0a3b569 | Add active contracts section |
| 80290fc | Add pipeline by priority breakdown |
| 865e228 | Add score distribution + platform avg |
| 6bcb9b1 | Add win/loss indicators |
| 6b3c40c | Add contract timeline bar chart |
| d7c95eb | Add priority doughnut chart |

**Result:** 110 passed (was 90). Not pushed.

---

## 2026-06-19 — Warn at startup when Railway volume is missing

**Task:** SQLite DB lost on Railway redeploy (`backlog/critical.md`)

**Fix:** Added `_warn_if_ephemeral_db()` to `app.py`. Checks `RAILWAY_ENVIRONMENT` (set on all Railway deployments) and `RAILWAY_VOLUME_NAME` (only set when a persistent volume is attached). Logs a `DATA LOSS RISK` warning if on Railway with no volume.

**Tests added:** 3 tests in `tests/test_app.py` covering warning emitted, suppressed with volume, suppressed off-Railway.

**Result:** 90 passed (was 87). Committed as `1810440`.

---

## 2026-06-19 — Fix negative days filter on /contracts

**Bug:** `GET /contracts?days=-1` silently returned expired contracts instead of rejecting the input.

**Fix:** Added a guard in `app.py` after parsing the `days` query param — returns HTTP 400 if the value is negative.

**Tests added:** `test_contracts_negative_days_returns_400`, `test_contracts_zero_days_returns_200`, `test_contracts_positive_days_returns_200` in `tests/test_app.py`.

**Result:** 87 passed (was 84). Committed as `f4b8959`.
