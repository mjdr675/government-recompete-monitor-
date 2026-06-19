# Current Status

Repository is running on a Hetzner VPS.

Claude Code is authenticated.

Python environment works.

All tests currently pass (87 passed as of 2026-06-19).

The objective is to safely improve this repository through small, production-quality commits.

## Last completed task

Fixed FTS rebuild bug in `save_snapshot()`. Commit: `12d722c`.

Sections delivered:
- Executive summary: 7 cards (pipeline, contracts, active, expired, critical, avg score, top score)
- Active contracts table (days_remaining > 0, LIMIT 50)
- Contract timeline bar chart (Chart.js 4.x via CDN, quarterly buckets)
- Agency breakdown enhanced (value, active count, share %, top score)
- Pipeline by priority table + doughnut chart
- Recompete score distribution with platform average comparison
- Win/loss indicators (inferred from days_remaining + changes table)
- Upcoming expirations enhanced (competition_type, urgency colors, LIMIT 25)
- Responsive CSS (@media 700px/480px) + overflow-x:auto table wrappers

Test count: 90 → 110 (+20 tests). All pass.

## Previously completed

Added `_warn_if_ephemeral_db()` to `app.py`. Logs a `DATA LOSS RISK` warning
at startup when `RAILWAY_ENVIRONMENT` is set but `RAILWAY_VOLUME_NAME` is not,
indicating contracts.db is on Railway's ephemeral filesystem. Three tests added.
Commit: `1810440`.

Backlog items marked [DONE]: "SQLite DB lost on Railway redeploy" (critical.md),
"Days-remaining filter accepts negative values" (bugs.md).

## Previously completed (excerpt)

Built full production Vendor Intelligence page (12 commits, a8531b5→d7c95eb). Test count 90→110.

## Next candidates

- No open backlog items remain. All bugs.md and critical.md items are [DONE].
