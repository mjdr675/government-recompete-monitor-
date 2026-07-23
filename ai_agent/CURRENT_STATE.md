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

## Phase 2 Feature Status

Most of the original Phase 2 backlog is now **delivered** (evidence in `app.py`,
`db.py`, `tasks.py`):

- Per-user saved searches — **Built**
- Watchlist (bookmark contracts) — **Built** (`/watchlist*` routes)
- Email alerts on contract changes — **Built** (`tasks.check_watchlist_alerts`)
- CSV export from filtered view — **Built** (`/contracts/export.csv`)
- Subscription billing portal — **Built** (`/billing/portal`, `/settings/billing`)
- Trial management — **Built** (`tasks.send_trial_emails`)
- Contract notes — **Built** (`contract_notes` table in `db.py`)
- Pipeline view — **Built** (`/pipeline*` routes)

Still pending / not conclusively verified:

- Mobile layout pass — **not verified** (no dedicated responsive-layout pass confirmed)

---

## Test Suite

A broad `pytest` suite lives in `tests/`, spanning the application routes, Celery
worker/beat tasks, ingest, billing/Stripe, authentication, database (SQLite and
PostgreSQL paths), and the AI-agent modules, plus integration coverage. Run
`venv/bin/pytest -q` for the current count (the suite grows over time, so no fixed
number is recorded here). CI runs `pytest -q` via `.github/workflows/deploy.yml`.

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

- **CSRF protection is enabled** via `flask_wtf` `CSRFProtect` on the app; a small set
  of endpoints (e.g. the Stripe webhook) are explicitly `@csrf.exempt`.
- **`/login` and `/register` are rate-limited** via `flask_limiter` (`limiter.limit`
  applied to the `auth.login` and `auth.register` view functions).
- **The Stripe webhook fails closed:** when `STRIPE_WEBHOOK_SECRET` is unavailable,
  `POST /stripe/webhook` returns HTTP 400 ("Webhook secret not configured"). Unsigned
  webhook acceptance is **not** the current behavior; signatures are verified via
  `construct_webhook_event`.
- _Historical/operational:_ live Stripe and HubSpot credentials were previously
  committed to git history (commits 971e8d1, d047d16) and untracked in d8a45f0. They
  should be treated as compromised; rotation is an operational action and its status
  is not tracked in this repository.
