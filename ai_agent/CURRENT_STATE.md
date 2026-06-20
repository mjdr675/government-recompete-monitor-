# Current State

**Last updated:** 2026-06-20 (CTO audit)

---

## Infrastructure

| Component | Status |
|---|---|
| Railway deployment | Live |
| Database | PostgreSQL (`DATABASE_URL`) with SQLite fallback for dev |
| Redis | Provisioned on Railway |
| Celery Worker | Running on Railway (Procfile) |
| Celery Beat | Running on Railway (Procfile) |
| Nightly ingest | Scheduled 02:00 UTC via `tasks.run_ingest` |
| PostgreSQL migration | `migrations/001_initial_pg.sql` — idempotent, applied via Procfile release step |

---

## Active Features

| Feature | Status |
|---|---|
| Session-based auth (register/login/logout) | Working — SQLite only; **broken on PostgreSQL** (see Blockers) |
| Dashboard with analytics and recommendations | Working — SQLite only; **broken on PostgreSQL** |
| Contract search + FTS | Working — SQLite FTS5 or PostgreSQL tsvector |
| Vendor intelligence page | Working — SQLite only; **broken on PostgreSQL** |
| Agency intelligence page | Working — SQLite only; **broken on PostgreSQL** |
| Contract detail page | Working |
| Contract comparison page | Working |
| Saved views | Working |
| CSV ingest | Working |
| API ingest (Celery) | Working |
| Ingest log endpoint (`/ingest/status`) | Working |
| Min-value filter on contracts | Working |
| Stripe checkout + webhook | Working |
| HubSpot CRM integration | Working |
| Demo request form | Working |
| Early access form | Working |
| `/health` endpoint | Working (minimal, no auth required) |
| pgvector extension | Provisioned, not yet used |

---

## Known Blockers (Must Fix Before Production PostgreSQL)

1. **`users.py` is SQLite-only** — uses `sqlite3.IntegrityError`, `sqlite3.Row`, `?` placeholders. Will fail on PostgreSQL.
2. **`analytics.py` is SQLite-only** — all functions use `con.execute()` with `?` placeholders and SQLite row factory. Will fail on PostgreSQL.

---

## Not Yet Built (Phase 2 Remaining)

- Per-user saved searches
- Watchlist (bookmark contracts)
- Email alerts on contract changes
- CSV export from filtered view
- Subscription billing portal (upgrade/downgrade/cancel)
- Trial management (14-day free trial)
- Contract notes
- Pipeline view
- Mobile layout pass

---

## Test Suite

Run `pytest -q` to get current count. As of 2026-06-20: approximately 726+ tests.

Tests live in `tests/`. All AI agent tests are included.
Test isolation: `tmp_path` fixtures, no live database access.

---

## Completed Tasks

| Task | Description |
|---|---|
| 041 | Agency intelligence page |
| 042 | Customer dashboard |
| 043 | Opportunity recommendations |
| 044 | AI engineering manager (QueueManager) |
| 048 | AI reviewer (two-stage safety review) |
| 049 | GitHub PR builder |
| 050 | GitHub issues sync |
| 051 | Engineering metrics / observability |
| 052 | Daemon mode |
| 053 | Human escalation system |
| 054 | Cost budgeting (BudgetTracker) |
| 055 | AI CTO (strategic planning module) |
| 056 | Min-value filter on contracts |
| 057 | `/health` unit test |
| 058 | Ingest logging |
| 059 | Human-readable labels in views |
| 060 | Pagination controls |
| 061 | PostgreSQL provisioning |
| 062 | SQLAlchemy schema migration |
| 063 | Redis provisioning |
| 064 | Celery worker and beat |
| 065 | SAM.gov ingest as Celery task |

Also completed (human-directed): auth system, documentation structure, company operating documents, Stripe integration, HubSpot integration.

---

## Security Notes

- Live Stripe secret key and HubSpot token were previously committed to git history (commits 971e8d1, d047d16) and were only untracked in d8a45f0. **These credentials should be considered compromised and rotated.**
- CSRF protection is not implemented on any form.
- No rate limiting on `/login`.
- Stripe webhook works without `STRIPE_WEBHOOK_SECRET` set (degrades to unsigned event acceptance).
