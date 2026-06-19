# Task Log

## 2026-06-19 — Fix negative days filter on /contracts

**Bug:** `GET /contracts?days=-1` silently returned expired contracts instead of rejecting the input.

**Fix:** Added a guard in `app.py` after parsing the `days` query param — returns HTTP 400 if the value is negative.

**Tests added:** `test_contracts_negative_days_returns_400`, `test_contracts_zero_days_returns_200`, `test_contracts_positive_days_returns_200` in `tests/test_app.py`.

**Result:** 87 passed (was 84). Committed as `f4b8959`.
