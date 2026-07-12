# O5 / Gate 3 — Shared Postgres + Celery worker/beat cutover plan

**Status:** Postgres + Redis are provisioned in the Railway project. Worker/beat
service defs and the shared `DATABASE_URL`/`REDIS_URL` references are now **active
in `railway.toml`** on branch `ops/celery-postgres-railway-services` (repo-side
groundwork). **Not deployed.** The human data cutover (steps 2–6 below) is still
outstanding, so this branch must **not** be merged/deployed yet.
**Goal:** run Celery `worker` and `beat` in prod so scheduled/async jobs (watchlist
alerts, trial-reminder emails, beat health) actually run. The nightly ingest is
owned solely by the `daily-ingest` cron — it is **not** a beat job.

> **Accepted ops risk:** Railway automated backups / PITR are unavailable on the
> current plan and are accepted as an operational risk for now. The app's
> fail-closed pre-start `scripts/backup_db.sh` snapshot (uploaded to R2) is the
> backup layer. Do not block this cutover on Railway Pro backups.

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
  either engine. Worker/beat service defs are **active** (config-as-code) in
  `railway.toml`, gated behind the human-only activation runbook.

## Current state (updated post-cutover 2026-07-10; originally 2026-07-08)

> **Cutover complete:** web is live on PostgreSQL 18.4. Steps 1–6 below are done.
> Only worker/beat service creation (step 7) remains, gated on the soak + PM sign-off.


- Railway services: `government-recompete-monitor-` (web), `ingest-cron`, `Redis`,
  **and `Postgres` (now provisioned).**
- `DATABASE_URL`: **now referenced on the live web service** — web runs on
  **PostgreSQL 18.4** as of the 2026-07-10 cutover
  (`DATABASE_URL=${{Postgres.DATABASE_URL}}`). `REDIS_URL`: present on web + Redis.
- `CRON_SECRET`: present on web + ingest-cron.
- `railway.toml`: `web` + `daily-ingest` + **`worker` + `beat` (now active, wired to
  `${{Postgres.DATABASE_URL}}` + `${{Redis.REDIS_URL}}`).**

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
   - Load into Postgres (e.g. `pgloader sqlite://<snapshot> "$DATABASE_URL"`),
     or a scripted per-table dump/insert. Migration must run **after** step 3's schema.
5. **Data-integrity checks (gate — must pass before cutover):**
   - Per-table `COUNT(*)` on Postgres == SQLite for: `users`, `user_watchlist`,
     `user_saved_searches`, `contract_notes`, `workspaces`, `contracts`, billing tables.
   - Spot-check a few known rows (a user + their watchlist; recent contracts).
   - `GET /api/data-freshness` and `/health` return 200 with `DATABASE_URL` set.
6. **Cut `web` over to Postgres**: it already is (step 2/3). Verify prod healthy for a
   soak period (login works, watchlists/notes load, contracts render).
7. **Activate worker + beat**: the two `[[services]]` blocks are already active in
   `railway.toml` on this branch — the remaining action is the live-service work in
   DEPLOYMENT.md §8b: create/deploy the `worker` and `beat` services and set
   `DATABASE_URL` **and** `REDIS_URL` (the `${{Postgres.DATABASE_URL}}` /
   `${{Redis.REDIS_URL}}` references) on both, then deploy.
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
  SQLite volume → jobs act on wrong data. Prevented by the DO-NOT-MERGE/DEPLOY gate
  (the service defs are active in `railway.toml` but the branch is not deployed) and
  by this plan's ordering.
- **Beat schedule persistence**: `celery.beat.PersistentScheduler` stores its state
  in a local file that resets on each redeploy/restart (Railway ephemeral storage).
  Low-impact — crontab entries re-seed from `tasks.py` — but consider `celery-redbeat`
  (Redis-backed) or a volume on `beat` later if durable schedule state is needed.
- **Downtime** during the maintenance-window cutover; **recurring cost** for Postgres.
- Writes to prod (data migration, restore) are **human-only, gated** actions.

## What is already done on branch `ops/celery-postgres-railway-services` (no deploy)

- `railway.toml`: `worker`/`beat` service definitions are **active** and, together
  with `web`, reference the shared `${{Postgres.DATABASE_URL}}` and
  `${{Redis.REDIS_URL}}`. An `ACTIVATION GATE` comment points here (the pre-cutover
  `DO NOT MERGE OR DEPLOY` prohibition was removed once web went live on Postgres).
- `tasks.py`: `run_ingest` **removed from the beat schedule** — single ingest owner
  is the `daily-ingest` cron. The task stays registered for manual/admin triggers.
- `docs/DEPLOYMENT.md` §8b: services, live-vs-config naming, manual Railway steps,
  single ingest owner, accepted backup risk, and worker/beat rollback.
- Tests updated: `test_o5_worker_beat_postgres.py` now asserts worker/beat are
  active and wired to shared Postgres/Redis; `test_celery_ingest.py` asserts
  `run_ingest` is a registered task but **not** on the beat schedule.
- Web is **LIVE on PostgreSQL 18.4** (cutover 2026-07-10); the pre-start pg_dump
  backup + R2 upload are verified. The `worker`/`beat` Railway services are still
  **NOT created** — that remains a human-only step gated on the post-cutover soak
  and explicit Product Manager authorization (see the activation runbook).
