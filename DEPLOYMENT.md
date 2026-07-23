# Deployment

**Canonical path: Railway.** This is the only path that serves live customer traffic.

## Production

- **Platform:** Railway, project `joyful-luck` / environment `production`.
- **Front door:** Cloudflare, `https://recompete.us` (confirm via response headers:
  `server: cloudflare`, `x-railway-edge`).
- **Build:** `railway.toml`, `builder = "nixpacks"`.
- **Web service:** `gunicorn app:app --bind 0.0.0.0:$PORT`.
- **Deploy trigger:** Railway's own auto-deploy on push to `main` (configured in the
  Railway dashboard, not in this repo). This is the *only* thing that redeploys prod.

## Data ingest

- **Schedule:** Railway cron service `daily-ingest`, `railway.toml`, `cronSchedule = "0 6 * * *"` (06:00 UTC daily).
- **Mechanism:** cron POSTs `https://recompete.us/ingest/run` with
  `Authorization: Bearer $CRON_SECRET`. Idempotent — a second call the same day
  returns `{"status":"already_ran"}` without re-running (pass `{"force":1}` to override).
- **Health check:** `GET /api/data-freshness` — `hours_ago` should stay under ~24h
  given the daily schedule.

## Backups

- **Nightly, on-host:** `~/recompete-backups/railway_nightly_backup.sh` (workstation
  cron, `CRON_TZ=UTC; 0 7 * * *`, after the 06:00 UTC ingest). Verifies integrity and
  sha256 before accepting a backup as successful. Retains 14 days under `nightly/`.
- **Off-site copy (Cloudflare R2):** ✅ **LIVE** as of 2026-07-08 (Railway deploy
  `03f648b6`, SUCCESS/Online). The web service's fail-closed pre-deploy backup
  (`scripts/backup_db.sh predeploy`, chained before `gunicorn` via `&&`) uploads
  each snapshot to R2 and re-downloads it to prove a byte-identical, integrity-
  checked copy before the deploy proceeds. Last verified snapshot:
  `backup_2026-07-08_002043_nogit_predeploy.db.gz` (4.0M), `PRAGMA
  integrity_check=ok` (run via the python3 fallback — no `sqlite3` CLI in the
  image), R2 upload verified byte-identical. Scripted restore/rehearsal:
  `scripts/restore_db.sh --from-r2` (`--verify-only` for a no-touch rehearsal).
- **Restore rehearsal:** performed and verified at Gate 1 completion (on-host
  snapshot -> `recompete-backups/restore-rehearsal/`, `integrity_check ok`, sane
  row counts, queryable).

## GitHub Actions (`.github/workflows/deploy.yml`) — DISABLED, kept as a manual escape hatch

This workflow used to auto-deploy on every push to `main` by SSHing into a
**separate, non-production VPS** (the Contabo box used as this project's CI/deploy
workstation) and running `git reset --hard origin/main` + `systemctl restart recompete`
there. It was never the path that served `recompete.us` — Railway was, the whole
time — but it silently redeployed a second, unused service on every push, carrying
live SSH credentials (`secrets.VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY`) as
unnecessary attack surface for a target nothing actually depends on.

As of 2026-07-03 (Gate 2 O4.2) its trigger is `workflow_dispatch` only — it no
longer fires automatically. The file is kept, not deleted, as a manual-only
option in case that VPS path is ever needed again; run it explicitly via the
GitHub Actions UI or `gh workflow run deploy.yml` if so.

## Known gaps (tracked, not yet resolved)

(Resolved 2026-07-08 — **Stripe webhook processing (was Gate 2 O2)**:
`STRIPE_WEBHOOK_SECRET` is now set on Railway prod, and the live deploy accepted a
resent Stripe delivery — `POST /stripe/webhook -> 200` at `2026-07-08T00:47:03Z`,
with no missing-secret warning, no signature-verification error, and no traceback.
`/stripe/webhook` verifies signatures via `stripe.Webhook.construct_event` and is
covered by `tests/test_stripe_webhook*.py`. Subscription lifecycle events
(checkout/update/cancel) are being verified and processed.)

(Resolved 2026-07-22 — **worker/beat are LIVE on Railway.** `Procfile` defines
`worker` (`celery -A tasks worker`) and `beat` (`celery -A tasks beat`), and
`railway.toml` defines four services — `web`, `daily-ingest`, `worker`, and `beat`.
As of the **2026-07-22 deploy** (commit `1c64b83`, status SUCCESS, project
`joyful-luck` / `production`) the live Railway `worker` and `beat` services are
**created and running**, deployed from the **same `1c64b83`** as `web`. Verified by
Michael via read-only Railway inspection on 2026-07-22: the worker log reached
`celery@… ready`, Beat loaded its schedule and at least one scheduled task fired,
`/health` returned HTTP 200, and web is live on **PostgreSQL 18.4**. The worker and
Beat that drive watchlist alerts, trial emails, and other async/scheduled email are
therefore live and processing in production. (The recorded evidence covers worker
readiness, Beat schedule loading, and at least one scheduled task firing; end-to-end
delivery of each individual email path was not separately verified here.)

  **Historical (superseded, dated):** from the 2026-07-10 Postgres cutover until the
  2026-07-22 deploy, the `worker`/`beat` blocks were config-as-code only — the live
  Railway services had **not** been created and Celery worker/beat were dead in prod.
  That state **no longer holds** as of the 2026-07-22 deploy above; it is retained
  here only as history and must not be read as current.

  The shared-Postgres prerequisite was satisfied at the 2026-07-10 cutover: web is
  live on PostgreSQL 18.4 (`DATABASE_URL=${{Postgres.DATABASE_URL}}`).

  **Future production changes remain human-only and gated.** Any further deploy,
  restart, scaling, or migration of `worker`/`beat` — or any service — still requires
  explicit Product Manager authorization. This documentation records the already-live
  state; it does **not** by itself authorize any future production action. Runbook and
  plan of record: [`docs/DEPLOYMENT.md` §8b](docs/DEPLOYMENT.md) (now the reference
  runbook for re-provisioning) and
  [`docs/O5_POSTGRES_MIGRATION_PLAN.md`](docs/O5_POSTGRES_MIGRATION_PLAN.md). The
  runbook's hard constraint still applies: **exactly one `beat` replica** — more than
  one fires every crontab job multiple times (duplicate emails/alerts).)

(Resolved: **off-site backup durability** — off-site Cloudflare R2 upload + fail-closed
restore/verify is now **live** as of 2026-07-08; see Backups above.)

## Rollback

If a deploy causes 5xx errors or ingest failures within 24h, roll back via `git push
origin <previous-good-commit>:main` (Railway redeploys the prior build automatically),
or use the Railway dashboard to redeploy the previous deployment directly. **Both are
production deploys and — like any forward deploy, restart, scaling, or migration —
require explicit Product Manager authorization; the only exception is an incident
response already authorized as an emergency rollback path.** If prod data was affected,
restore the most recent verified snapshot from `~/recompete-backups/` via `railway ssh`
— this is a prod write and needs approval.
