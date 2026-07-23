# O5 / Gate 3 — Shared Postgres + Celery worker/beat cutover plan

**Status (2026-07-22): COMPLETE — web, worker, and beat are LIVE in production.**
All three services are deployed from commit `1c64b83` (status SUCCESS, deployed
2026-07-22) in Railway project `joyful-luck` / `production`, sharing a network
Postgres (`DATABASE_URL`) and Redis (`REDIS_URL`). The Postgres data cutover
(steps 2–6) completed on 2026-07-10; worker/beat activation (steps 7–8) is
confirmed live as of 2026-07-22 — see "Current state" below for the human-verified
evidence. _Historical (superseded):_ before 2026-07-22 the worker/beat service defs
were config-as-code only in `railway.toml` and the live services had not been
created.
**Goal:** run Celery `worker` and `beat` in prod so scheduled/async jobs (watchlist
alerts, trial-reminder emails, beat health) actually run. The nightly ingest is
owned solely by the `daily-ingest` cron — it is **not** a beat job.

> **Accepted ops risk:** Railway automated backups / PITR are unavailable on the
> current plan and are accepted as an operational risk for now. The app's
> fail-closed pre-start `scripts/backup_db.sh` snapshot (uploaded to R2) is the
> backup layer. Do not block this cutover on Railway Pro backups.

---

## Why this needs shared Postgres (not just Redis)

- _Historical (pre-2026-07-10 cutover):_ `web` served off **SQLite** at
  `/data/contracts.db`, on a Railway **volume**. Web now runs on network Postgres
  (see "Current state" below); the SQLite topology no longer applies.
- A Railway volume **binds to a single service**. Separate `worker`/`beat` services
  cannot see `web`'s SQLite file — they'd each get an empty per-service volume.
- Redis is already provisioned (`REDIS_URL` present) and is only the Celery
  **broker/result backend**, not the application datastore.
- Therefore all three services must share a **network Postgres** via `DATABASE_URL`.
  The app already supports this: `db.get_engine()` / `db.get_connection()` select
  Postgres when `DATABASE_URL` is set, and `db._apply_migrations()` runs against
  either engine. Worker/beat service defs are **active** in `railway.toml`, and the
  `worker` and `beat` services are now **live in production** as of the 2026-07-22
  deploy (commit `1c64b83`).

## Current state (updated 2026-07-22; post-cutover 2026-07-10; originally 2026-07-08)

> **COMPLETE:** web, worker, and beat are all live in production, deployed from
> commit `1c64b83` (status SUCCESS, 2026-07-22). Steps 1–8 below are done.
> Human-verified read-only evidence (2026-07-22): the worker log reached
> `celery@… ready`; Beat loaded its schedule and at least one scheduled task fired;
> `/health` returned HTTP 200; web is on **PostgreSQL 18.4**. **No** deploy, restart,
> scaling, or migration was performed while writing this documentation — it records
> already-live state only. Future production changes remain human-only and gated.


- Railway services: `government-recompete-monitor-` (web), `ingest-cron`, `Redis`,
  `Postgres`, **and the `worker` + `beat` services — all live as of the 2026-07-22
  deploy (commit `1c64b83`).**
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
7. **Activate worker + beat** — ✅ **DONE (2026-07-22).** The live `worker` and
   `beat` Railway services are created and deployed from commit `1c64b83`, wired to
   the shared `${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}` references
   (per DEPLOYMENT.md §8b). Deployment status SUCCESS.
8. **Verify worker/beat** — ✅ **DONE (2026-07-22, human read-only verification).**
   The worker log reached `celery@… ready`; Beat loaded its schedule and at least one
   scheduled task fired; `/health` returned HTTP 200; web is live on PostgreSQL 18.4.

## Rollback

- **Before data migration:** unset/remove `DATABASE_URL` from `web` → app falls back
  to SQLite on its volume (unchanged). Delete the Postgres service. No data touched.
- **After partial migration / bad data:** keep `web` on SQLite (do not cut over);
  the SQLite volume is untouched during load; discard the Postgres data and retry.
- **After cutover regression:** re-point `web` off `DATABASE_URL` to SQLite (the
  volume snapshot from step-0 backup), remove worker/beat services, restore from the
  R2 snapshot if any SQLite write was affected (prod write — needs approval).
- Removing worker/beat leaves web serving and stored data unaffected, but they hold the
  email-provider credentials and drive external email delivery, so removal **halts
  processing of all queued async jobs** until they are restored.

## Prod risks

- **Data loss / divergence** during the SQLite→Postgres load — mitigated by the
  pre-migration verified backup and the step-5 count/spot checks (hard gate).
- **Type/collation differences** SQLite vs Postgres (e.g. boolean/text affinity) —
  validate app reads after schema build (step 3) before loading data.
- **Premature worker/beat activation** against an empty PG or an empty per-service
  SQLite volume would make jobs act on wrong data. This was prevented by ordering the
  cutover (web → Postgres first, steps 2–6) before creating worker/beat; activation
  happened only after the Postgres cutover, so the risk did not materialize. Retained
  here as guidance for any future re-provisioning.
- **Beat schedule persistence**: `celery.beat.PersistentScheduler` stores its state
  in a local file that resets on each redeploy/restart (Railway ephemeral storage).
  Low-impact — crontab entries re-seed from `tasks.py` — but consider `celery-redbeat`
  (Redis-backed) or a volume on `beat` later if durable schedule state is needed.
- **Downtime** during the maintenance-window cutover; **recurring cost** for Postgres.
- Writes to prod (data migration, restore) are **human-only, gated** actions.

## Repo groundwork (originally branch `ops/celery-postgres-railway-services`) — now merged & live

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
  backup + R2 upload are verified. The `worker` and `beat` Railway services are now
  **LIVE as well**, deployed from commit `1c64b83` on 2026-07-22 (worker
  `celery@… ready`; Beat schedule loaded and at least one scheduled task fired;
  `/health` 200). **Future** deploys, restarts, scaling, or migrations of any service
  remain human-only and require explicit Product Manager authorization — this
  documentation records live state and does not itself authorize any future
  production action.
