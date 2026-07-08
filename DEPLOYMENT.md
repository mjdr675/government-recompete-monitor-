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

- **worker/beat are not running on Railway.** `Procfile` defines `worker`
  (`celery -A tasks worker`) and `beat` (`celery -A tasks beat`), but `railway.toml`
  only defines `web` and `daily-ingest` services — celery worker/beat are dead in
  production. Watchlist alerts, trial emails, and other async/scheduled email are
  not running. Needs a shared Postgres to restore properly; deferred to Gate 3 (O5).
  Branch-only groundwork + human-only cutover steps: see
  [`docs/O5_POSTGRES_MIGRATION_PLAN.md`](docs/O5_POSTGRES_MIGRATION_PLAN.md)
  (worker/beat service defs are drafted, commented/inactive, in `railway.toml`).

(Resolved: **off-site backup durability** — off-site Cloudflare R2 upload + fail-closed
restore/verify is now **live** as of 2026-07-08; see Backups above.)

## Rollback

If a deploy causes 5xx errors or ingest failures within 24h: `git push origin
<previous-good-commit>:main` (Railway redeploys the prior build automatically), or
use the Railway dashboard to redeploy the previous deployment directly. If prod
data was affected, restore the most recent verified snapshot from
`~/recompete-backups/` via `railway ssh` — this is a prod write and needs approval.
