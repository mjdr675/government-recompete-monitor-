# O5 / Gate 3 — Shared Postgres + Celery worker/beat cutover plan

**Status:** groundwork only (this branch). Nothing here is provisioned or deployed.
**Goal:** run Celery `worker` and `beat` in prod so scheduled/async jobs (watchlist
alerts, trial-reminder emails, beat health, nightly ingest fallback) actually run.

---

## Why this needs shared Postgres (not just Redis)

- Today `web` serves off **SQLite** at `/data/contracts.db`, on a Railway **volume**.
- A Railway volume **binds to a single service**. Separate `worker`/`beat` services
  cannot see `web`'s SQLite file — they'd each get an empty per-service volume.
- Redis is already provisioned (`REDIS_URL` present) and is only the Celery
  **broker/result backend**, not the application datastore.
- Therefore all three services must share a **network Postgres** via `DATABASE_URL`.
  The app already supports this: `db.get_engine()` / `db.get_connection()` select
  Postgres when `DATABASE_URL` is set, and `db._apply_migrations()` runs against
  either engine. Worker/beat service defs are drafted (commented) in `railway.toml`.

## Current state (verified)

- Railway services: `web` (Online), `ingest-cron`, `Redis` (Online). **No Postgres.**
- `DATABASE_URL`: **not set** (SQLite). `REDIS_URL`: **present**.
- `railway.toml`: only `web` + `daily-ingest`. Worker/beat are drafted but inactive.

---

## Human-only cutover steps (each needs explicit approval)

> Do NOT start until the SQLite prod DB has a fresh, verified off-site backup
> (the live pre-deploy R2 backup already produces one on every web start; confirm
> the latest `PRAGMA integrity_check=ok` + R2 upload in the web start logs first).

1. **[COST] Provision PostgreSQL on Railway** (`Add Service → Database → PostgreSQL`).
   Railway sets `DATABASE_URL` on the PG service. Recurring cost — approve first.
2. **Reference `DATABASE_URL`** (and existing `REDIS_URL`) on `web` **only** at first,
   pointing at the empty Postgres. Do NOT add worker/beat yet.
3. **Create schema on Postgres**: redeploy `web`; app import runs
   `init_db()` → `_apply_migrations()` against `DATABASE_URL`, building the schema on PG.
   Confirm no migration errors in the deploy logs.
4. **Migrate data SQLite → Postgres** (one-time, maintenance window):
   - Pull the latest verified SQLite snapshot (from R2 or the web volume).
   - Load into Postgres (e.g. `pgloader sqlite://<snapshot> postgresql://<DATABASE_URL>`),
     or a scripted per-table dump/insert. Migration must run **after** step 3's schema.
5. **Data-integrity checks (gate — must pass before cutover):**
   - Per-table `COUNT(*)` on Postgres == SQLite for: `users`, `user_watchlist`,
     `user_saved_searches`, `contract_notes`, `workspaces`, `contracts`, billing tables.
   - Spot-check a few known rows (a user + their watchlist; recent contracts).
   - `GET /api/data-freshness` and `/health` return 200 with `DATABASE_URL` set.
6. **Cut `web` over to Postgres**: it already is (step 2/3). Verify prod healthy for a
   soak period (login works, watchlists/notes load, contracts render).
7. **Activate worker + beat**: uncomment the two `[[services]]` blocks in
   `railway.toml` (this branch's draft), ensure `DATABASE_URL` **and** `REDIS_URL`
   are set on both, deploy.
8. **Verify worker/beat**: worker log shows `celery@… ready`; beat log shows the
   schedule loaded; `tasks.heartbeat` and `tasks.check_beat_health` fire; a watchlist
   alert / trial email sends on schedule (or via a manual trigger).

## Rollback

- **Before data migration:** unset/remove `DATABASE_URL` from `web` → app falls back
  to SQLite on its volume (unchanged). Delete the Postgres service. No data touched.
- **After partial migration / bad data:** keep `web` on SQLite (do not cut over);
  the SQLite volume is untouched during load; discard the Postgres data and retry.
- **After cutover regression:** re-point `web` off `DATABASE_URL` to SQLite (the
  volume snapshot from step-0 backup), remove worker/beat services, restore from the
  R2 snapshot if any SQLite write was affected (prod write — needs approval).
- Worker/beat are safe to remove any time (they only consume the broker + PG).

## Prod risks

- **Data loss / divergence** during the SQLite→Postgres load — mitigated by the
  pre-migration verified backup and the step-5 count/spot checks (hard gate).
- **Type/collation differences** SQLite vs Postgres (e.g. boolean/text affinity) —
  validate app reads after schema build (step 3) before loading data.
- **Premature worker/beat activation** against an empty PG or an empty per-service
  SQLite volume → jobs act on wrong data. Prevented by keeping the services
  commented until step 7 and by this plan's ordering.
- **Downtime** during the maintenance-window cutover; **recurring cost** for Postgres.
- Writes to prod (data migration, restore) are **human-only, gated** actions.

## What is already done on this branch (no infra changes)

- `railway.toml`: drafted (commented, inert) `worker`/`beat` service definitions.
- Tests: Postgres-vs-SQLite engine/connection selection, Celery broker/backend wired
  to `REDIS_URL`, and the beat schedule contains the required jobs
  (`tests/test_o5_worker_beat_postgres.py`).
- This plan. SQLite behavior is unchanged; nothing is provisioned or deployed.
