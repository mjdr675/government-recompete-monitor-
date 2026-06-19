# Current Status

Repository is running on a Hetzner VPS.

Claude Code is authenticated.

Python environment works.

All tests currently pass (133 passed as of 2026-06-19).

The objective is to safely improve this repository through small, production-quality commits.

## Last completed task

Task 043 — Opportunity Recommendations. Added categorized recommendation logic with reasons.

- `analytics.py`: Added `opportunity_recommendations(con)` — returns a deduplicated list of recommended opportunities, each with a `reason` field. Categories (in priority order): Top Recompete Score, Highest Value, Soonest Expiration, Critical Priority, Recently Changed. Each contract appears at most once.
- `app.py`: Dashboard route now calls `opportunity_recommendations(con)` and passes `recommendations` to template.
- `templates/dashboard.html`: Replaced plain "Recommended Opportunities" table with categorized table including a "Why" column showing the reason for each recommendation.
- `tests/test_analytics.py`: New file with 14 unit tests covering all recommendation categories, deduplication, inactive contract exclusion, and missing changes table resilience.
- `tests/test_app.py`: 5 new route/template tests for recommendation rendering.

Test count: 146 → 166 (+20 tests). All pass.

## Previously completed

Task 042 — Customer Dashboard. Rebuilt homepage as a useful customer-facing dashboard.

Sections delivered:
- 5 summary cards: Total Pipeline, Total Contracts, Active, Critical, Avg Score
- Quick nav buttons: All Contracts, Critical Only, Expiring 90 Days, Saved Views, Ingest
- Critical Opportunities section (CRITICAL priority + days_remaining > 0)
- Upcoming Expirations (next 90 days, urgency coloring)
- Recommended Opportunities (top contracts by recompete score, from top_contracts_overall)
- Recent Changes (existing change-log table preserved)
- Side-by-side Top Agencies + Top Vendors (all-time pipeline values, linked)
- `dashboard_analytics(con)` added to analytics.py for platform-wide stats

Test count: 133 → 146 (+13 tests). All pass.

## Previously completed

Fixed FTS rebuild bug in `save_snapshot()`. Commit: `12d722c`.

Built full production Vendor Intelligence page (12 commits, a8531b5→d7c95eb). Test count 90→110.

Added `_warn_if_ephemeral_db()` to `app.py`. Logs a `DATA LOSS RISK` warning
at startup when `RAILWAY_ENVIRONMENT` is set but `RAILWAY_VOLUME_NAME` is not,
indicating contracts.db is on Railway's ephemeral filesystem. Three tests added.
Commit: `1810440`.

Backlog items marked [DONE]: "SQLite DB lost on Railway redeploy" (critical.md),
"Days-remaining filter accepts negative values" (bugs.md).

## Next candidates

- Task 042 — Customer Dashboard
- Task 043 — Opportunity Recommendations
