# Current State

**Last updated:** 2026-07-23 (O5 runtime reconciliation)

> **Production runtime:** web + Celery `worker` + `beat` are **live on PostgreSQL 18.4**
> (Railway). O5 / Gate 3 (shared Postgres + worker/beat cutover) is **COMPLETE** — web
> cut over to Postgres on 2026-07-10; the `worker` and `beat` services went live on
> 2026-07-22 from commit `1c64b83` (deploy SUCCESS), with human read-only verification
> recorded 2026-07-22. Authoritative sources: `docs/O5_POSTGRES_MIGRATION_PLAN.md` and
> `docs/DEPLOYMENT.md` §8b.
>
> **Repo main vs production runtime:** repository `main` is ahead of the deployed commit
> `1c64b83` only by PRs #75–#78, which are **docs/tooling-only** changes (no product
> code). Production remaining on `1c64b83` therefore does **not** imply a pending product
> deployment.

---

## Infrastructure

| Component | Status |
|---|---|
| Railway deployment | Live |
| Database | PostgreSQL (`DATABASE_URL`) with SQLite fallback for dev |
| Redis | Provisioned on Railway |
| Celery Worker | Live — dedicated Railway service (since 2026-07-22, commit `1c64b83`), on shared network Postgres + Redis |
| Celery Beat | Live — dedicated Railway service (since 2026-07-22); schedules watchlist alerts (07:00 UTC), trial emails (09:00 UTC), heartbeat (5 min), beat-health check (10 min). Does **not** run the nightly ingest |
| Nightly ingest | Owned solely by the dedicated `daily-ingest` cron at `0 6 * * *` (06:00 UTC) — **not** a beat task |
| PostgreSQL migration | Idempotent; applied at app startup via `init_db()` → `_apply_migrations()` against `DATABASE_URL` |

---

## Active Features

| Feature | Status |
|---|---|
| Session-based auth (register/login/logout) | Working (PostgreSQL + SQLite) |
| Dashboard with analytics and recommendations | Working (PostgreSQL + SQLite) |
| Contract search + FTS | Working — SQLite FTS5 or PostgreSQL tsvector |
| Vendor intelligence page | Working (PostgreSQL + SQLite) |
| Agency intelligence page | Working (PostgreSQL + SQLite) |
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

## PostgreSQL Compatibility (RESOLVED)

_Historical: earlier revisions listed `users.py` and `analytics.py` as SQLite-only
blockers to a PostgreSQL cutover._ Both are now **database-driver-agnostic** — the
SQLite-only patterns (`sqlite3.*`, SQLite row factory, `?` placeholders) were removed
in prior compatibility work (associated with PRs #65 and #66). No PostgreSQL blockers
remain; production web/worker/beat run on PostgreSQL 18.4.

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
