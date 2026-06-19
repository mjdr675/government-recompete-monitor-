# Task Log

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
