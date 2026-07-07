# Recompete.us — Deployment & Verification Guide

**Last verified:** 2026-06-23
**Platform:** Railway
**Repo HEAD at time of writing:** `6a88602`

---

## 1. Deployment Platform

**Railway** is the production host. Evidence:

- `Procfile` in repo root defines all process types
- `app.py` reads `RAILWAY_ENVIRONMENT` and `RAILWAY_VOLUME_NAME`
- `ai_agent/CURRENT_STATE.md` states "Railway deployment | Live"
- `requirements.txt` includes `gunicorn==26.0.0`

There is **no VPS, no systemd, no nginx, no GitHub Actions CI/CD** defined in this repo.
Deploys happen automatically when commits land on `main` (Railway auto-deploy from GitHub).

---

## 2. Process Model (Procfile)

```
release: python -c "from db import init_db; init_db()"
web:     gunicorn app:app --bind 0.0.0.0:$PORT
worker:  celery -A tasks worker --loglevel=info
beat:    celery -A tasks beat --loglevel=info --scheduler celery.beat.PersistentScheduler
```

| Process | Role |
|---|---|
| `release` | Runs before web starts; initialises DB schema idempotently |
| `web` | Flask app served by Gunicorn; Railway assigns `$PORT` |
| `worker` | Celery task worker (email, ingest, webhooks) |
| `beat` | Celery periodic scheduler (nightly ingest at 02:00 UTC, beat health check every 10 min) |

---

## 3. Required Environment Variables

Set these in the Railway project dashboard under **Variables**.

### Required — app will not work without these

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing key — must be long random string in production |
| `DATABASE_URL` | PostgreSQL connection string (Railway provides this automatically when you provision PostgreSQL) |
| `REDIS_URL` | Redis connection string (Railway provides this automatically when you provision Redis) |

### Required — specific features break without these

| Variable | Description | Default / Fallback |
|---|---|---|
| `STRIPE_SECRET_KEY` | Stripe payments | None — checkout broken |
| `STRIPE_PRICE_ID` | Stripe subscription price ID | None — checkout broken |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification | None — webhook accepts unsigned events |
| `EMAIL_API_KEY` | Resend API key for transactional email | None — emails silently not sent |
| `SMTP_FROM` | From address for emails | `noreply@govrecompete.com` |
| `ADMIN_EMAIL` | Alert destination for beat health failures | None — alerts not sent |
| `APP_URL` | Base URL used in email links | `https://govrecompete.com` |
| `HUBSPOT_ACCESS_TOKEN` | HubSpot CRM integration | None — CRM steps skipped |
| `HUBSPOT_BETA_PIPELINE_ID` | HubSpot pipeline ID | `default` |
| `HUBSPOT_DEMO_STAGE_ID` | HubSpot stage for demo requests | `appointmentscheduled` |
| `HUBSPOT_PAYING_STAGE_ID` | HubSpot stage for paying customers | `closedwon` |
| `HUBSPOT_EARLY_ACCESS_LEAD_SOURCE` | Lead source label | `Early Access` |

### Optional

| Variable | Description |
|---|---|
| `SENTRY_DSN` | Sentry error tracking — app works fine without it |
| `DB_PATH` | SQLite file path when not using `DATABASE_URL` (e.g. `/data/contracts.db` if using Railway volume) |
| `RAILWAY_ENVIRONMENT` | Set automatically by Railway — do not set manually |
| `RAILWAY_VOLUME_NAME` | Set automatically by Railway when a volume is attached |
| `PORT` | Set automatically by Railway — do not set manually |

### Off-site backup — Cloudflare R2 (all four required to enable)

`scripts/backup_db.sh` uploads every successful snapshot to Cloudflare R2 when
these are present. All four must be set together (a partial config fails closed
and aborts the deploy). Credentials are read from the environment only and are
never logged. Requires the `aws` CLI (awscli) in the backup environment.

| Variable | Description |
|---|---|
| `R2_ENDPOINT` | R2 S3-compatible endpoint URL (e.g. `https://<acct>.r2.cloudflarestorage.com`) |
| `R2_ACCESS_KEY_ID` | R2 access key id |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |
| `R2_BUCKET` | R2 bucket name for backups |
| `R2_REGION` | S3 region label (optional; default `auto`) |
| `RECOMPETE_R2_RETAIN_DAYS` | Delete R2 snapshots older than N days (optional; default `14`) |

---

## 4. Local Development

### Setup

```bash
cd /home/michael/government-recompete-monitor-
source venv/bin/activate   # or: venv/bin/python
# no DATABASE_URL set → app uses contracts.db (SQLite) automatically
```

### Run tests

```bash
venv/bin/pytest                    # full suite (~1681 tests, ~2 min)
venv/bin/pytest tests/test_health.py -v   # health endpoint only
venv/bin/pytest tests/test_mobile_first.py -v  # mobile tests only
```

### Compile smoke check

```bash
python3 -m compileall . -q          # should produce no output
```

### Run app locally (dev server)

```bash
python app.py                       # Flask dev server on http://localhost:8000
```

### Run app locally (gunicorn — matches production)

```bash
PORT=8000 venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --workers 1
curl http://127.0.0.1:8000/health   # should return {"status": "ok"}
```

### Local health check result (verified 2026-06-23)

```
{"status":"ok"}   HTTP 200
```

---

## 5. Production Health Verification

### Simple health check (no auth required)

```bash
curl https://recompete.us/health
# Expected: {"status":"ok"}  HTTP 200
```

If this returns anything other than `{"status":"ok"}` and HTTP 200, the web process is down.

### Detailed health check (requires auth cookie — do this in browser)

```
GET https://recompete.us/api/health/detailed
```

Expected response when healthy:

```json
{
  "db": "ok",
  "redis": "ok",
  "last_ingest_at": "<ISO timestamp>",
  "last_ingest_records": <integer>,
  "ok": true
}
```

Returns HTTP 503 if DB or Redis is unreachable.
Returns HTTP 401 if not logged in.

### Railway dashboard checks

After any push to `main`:

1. Open Railway project → **Deployments** tab
2. Confirm the latest deployment shows **Success** (green)
3. Confirm `release` phase completed without error
4. Confirm `web`, `worker`, `beat` processes are all **Running**
5. Check **Logs** for any startup errors

---

## 6. Deployment Flow (What Happens When You Push)

```
git push origin main
    ↓
Railway detects push (auto-deploy enabled)
    ↓
Railway builds (pip install -r requirements.txt)
    ↓
release phase: python -c "from db import init_db; init_db()"
    (creates/migrates DB schema — idempotent, safe to run every deploy)
    ↓
web process: gunicorn app:app --bind 0.0.0.0:$PORT
worker process: celery -A tasks worker
beat process: celery -A tasks beat
    ↓
Railway health-checks GET /health → expects 200
    ↓
Traffic switches to new deployment
```

---

## 7. Safe Manual Deploy Checklist

Before pushing any commit to `main` for production:

- [ ] `1681/1681` tests pass locally: `venv/bin/pytest`
- [ ] Compile clean: `python3 -m compileall . -q`
- [ ] No `.env` files, secrets, or `contracts.db` accidentally staged
- [ ] `git status` shows only intended files
- [ ] The commit message is clear and accurate
- [ ] After push: Railway dashboard shows deployment **Success**
- [ ] After push: `curl https://recompete.us/health` returns `{"status":"ok"}`
- [ ] After push: visit the app and confirm login still works

---

## 8. Rollback Checklist

Railway supports one-click rollback to a previous deployment:

1. Open Railway project → **Deployments** tab
2. Find the last known-good deployment
3. Click **Redeploy** on that deployment
4. Confirm health: `curl https://recompete.us/health`

If the deployment is already failing at the `release` phase (DB init error):
- The previous deployment stays live (Railway does not swap until `release` succeeds)
- Fix the schema/migration issue on a branch, test locally, then push again

For a git-level rollback (use carefully):

```bash
# Identify the last known-good commit
git log --oneline -10

# Create a revert commit (safe — does not rewrite history)
git revert <bad-commit-hash>
git push origin main
```

**Never** use `git push --force` on `main` — it will confuse Railway and may cause a failed deploy.

---

## 8a. Database Backups (local + off-site R2)

`scripts/backup_db.sh` is the hard safety layer. It writes a gzip-compressed,
integrity-verified snapshot to a persistent local directory
(`RECOMPETE_BACKUP_DIR`, default `/var/backups/recompete`) and — when the `R2_*`
env vars are set — also uploads it to Cloudflare R2 and re-downloads it to prove
it is restorable before the run is considered successful.

**Fail-closed:** if the snapshot, its integrity check, the R2 upload, or the R2
restore-verification fails, the script exits non-zero. Because it is chained
ahead of `gunicorn` with `&&` in the start command, a non-zero exit means the web
process never starts, so `init_db()`'s migrations never run without a good backup.

**Retention:** local = newest `RECOMPETE_BACKUP_RETAIN` (default 15) by count;
R2 = delete objects older than `RECOMPETE_R2_RETAIN_DAYS` (default 14) days
(best-effort — a prune failure never aborts a deploy).

### Two schedules

- **Pre-start** (wired on Railway): the `web` service's start command is
  `bash scripts/backup_db.sh predeploy && gunicorn app:app --bind 0.0.0.0:$PORT`
  (`railway.toml`). The backup runs at container start, where the SQLite volume
  **is** mounted, and `&&` makes it fail-closed — gunicorn (and therefore
  `init_db()`'s migrations) never starts without a verified backup. This is
  **not** a `preDeployCommand`: Railway runs pre-deploy commands in a separate
  container with **no volumes mounted**
  ([docs](https://docs.railway.com/guides/pre-deploy-command)), so a pre-deploy
  backup could not read the live DB. Tradeoff: the backup now runs on every web
  container start (deploys, restarts, replica scale-ups), not only per deploy.
  (The disabled `.github/workflows/deploy.yml` VPS path still calls
  `backup_db.sh predeploy` before restart, where a local volume is present.)
- **Daily** (NOT yet wired — follow-up): a standalone Railway cron **service**
  cannot back up the live DB, because a Railway volume binds to a single service
  and the SQLite volume must stay on `web`; a separate service would see no DB and
  no-op permanently. So there is intentionally **no `daily-backup` cron service**
  in `railway.toml`. The daily backup must instead reuse the **ingest-cron
  pattern**: add a `CRON_SECRET`-protected endpoint on `web` (e.g. `POST
  /backup/run`) that shells out to `scripts/backup_db.sh daily` inside the
  container that owns the DB volume, then add a cron service that `curl`s it —
  exactly like the existing `daily-ingest` service. This endpoint work is a
  separate, approved-scope follow-up (not implemented here).
- **`aws` CLI**: installed by `nixpacks.toml`'s build phase — pip-installed into
  an isolated venv (`/opt/awscli`) and symlinked to `/usr/local/bin/aws`, so it
  is on PATH in the deploy image for the start-command backup (and any future
  endpoint-triggered daily run) without polluting the app's pinned deps. (It is
  **not** an apt package: Ubuntu noble has no `awscli` apt candidate.)

### Restore

```bash
# Local backups
scripts/restore_db.sh --list                 # newest first (local dir)
scripts/restore_db.sh --yes <backup_file>    # restore a specific local snapshot

# Off-site (Cloudflare R2) — scripted, fail-closed (needs R2_* env + awscli)
scripts/restore_db.sh --r2-list                        # list R2 snapshots
scripts/restore_db.sh --from-r2 --latest --verify-only # RESTORE REHEARSAL:
#   download latest snapshot to a scratch dir, run gzip + PRAGMA integrity_check
#   + table/row sanity vs the live DB, and STOP without touching the live DB.
scripts/restore_db.sh --from-r2 --latest --yes         # download, validate, then restore
scripts/restore_db.sh --from-r2 <key> --yes            # restore a specific R2 key
```

The `--from-r2` path is fail-closed: any download, gzip, or `integrity_check`
failure exits non-zero. Run `--from-r2 --latest --verify-only` periodically as a
restore rehearsal to prove the off-site backups are recoverable. Credentials are
read from the environment only and are never logged.

Prerequisite for R2 in any environment: **`awscli` on PATH** and the four `R2_*`
variables set. Never commit these values.

---

## 9. Known State as of 2026-06-23

| Item | Status |
|---|---|
| Local tests | 1681/1681 passing |
| Local compile | Clean |
| Local /health (gunicorn) | `{"status":"ok"}` |
| Production /health | **Not verified** — no outbound network access from this machine to production URL |
| Railway dashboard | **Not verified** — no Railway CLI or browser session available from this machine |
| Production deployment | Assumed live; last push was `6a88602` (Mobile-First Phase 2) |

---

## 10. What Information Is Missing

| Missing Item | Impact | How to get it |
|---|---|---|
| Production URL confirmation | Cannot verify `/health` externally | You (the operator) should `curl https://recompete.us/health` from any machine |
| Railway dashboard access | Cannot confirm deployment status | Log into railway.app and check the project |
| Env var completeness | Some vars may not be set in Railway | Check Railway → Variables tab against section 3 above |
| VPS IP `5.78.100.135` | Mentioned in prior session notes but absent from repo | If this was a previous host, confirm it has been decommissioned or document it |
| Production DB state | Unknown if schema migrations ran correctly after each deploy | Run `/api/health/detailed` in-browser when logged in |
| Stripe in live mode | Unknown if `STRIPE_SECRET_KEY` is live key or test key | Check Railway Variables |

---

## 11. Exact Future Claude Prompt — Production Deploy Verification

Use this prompt after any future push to have Claude verify production:

```
You are my engineering agent for Recompete.us.

Repository: /home/michael/government-recompete-monitor-
Branch: main
HEAD: <paste current git rev-parse HEAD>

A push was just made to origin/main. Verify production is healthy.

Steps:
1. Confirm local HEAD matches origin/main:
   git rev-parse HEAD && git rev-parse origin/main

2. Run local tests:
   venv/bin/pytest
   python3 -m compileall . -q

3. Check the production health endpoint:
   curl -sf https://recompete.us/health
   Expected: {"status":"ok"}  HTTP 200

4. If you have Railway CLI access:
   railway status
   railway logs --tail 50

5. Report:
   - local HEAD
   - origin/main
   - test result
   - compile result
   - /health response
   - Railway deployment status (if accessible)
   - any errors or warnings
   - whether it is safe to close

Rules:
- Do not push
- Do not merge branches
- Do not commit product code
- Report failures clearly without hiding them
```

---

## 12. Security Notes (from ai_agent/CURRENT_STATE.md)

> ⚠️ Live Stripe secret key and HubSpot token were previously committed to git history
> (commits `971e8d1`, `d047d16`) and were only untracked in `d8a45f0`.
> **These credentials should be considered compromised and rotated** if not already done.

- CSRF protection is implemented via Flask-WTF `CSRFProtect`
- Rate limiting on `/login` (5 per minute via Flask-Limiter)
- `SESSION_COOKIE_SECURE` is True only when `RAILWAY_ENVIRONMENT == "production"`
- Stripe webhook operates without signature verification if `STRIPE_WEBHOOK_SECRET` is not set
