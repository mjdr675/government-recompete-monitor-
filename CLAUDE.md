# Government Recompete Monitor (Recompete.us)

## What this project does
Flask web application that monitors government contract recompete opportunities.
Tracks upcoming contract expirations, surfaces competitive leads, and provides
an operator dashboard for managing bids. Auth, billing (Stripe), email (Celery),
and a contracts database backed by SQLite (dev) / PostgreSQL (prod).

## Key files
- `app.py` — Flask application factory and route definitions
- `db.py` — database helpers and schema (SQLite dev / Postgres prod)
- `auth.py` — registration, login, session management
- `tasks.py` — Celery task definitions (email, ingest)
- `views.py` — contract view queries
- `analytics.py` — dashboard aggregations
- `requirements.txt` — Python dependencies

## How to run (dev)
```bash
source /home/michael/autonomous-engineering/.venv/bin/activate
python app.py          # Flask dev server
# Redis + Celery are optional; app degrades gracefully without them
```

## Tests
```bash
cd /home/michael/government-recompete-monitor-
.venv/bin/pytest                      # full suite (~1681 tests, ~2 min)
python3 -m compileall . -q            # compile smoke check
```

## Deployment
Production runs on **Railway** (auto-deploy from `main`). Full details, env vars,
health check commands, deploy checklist, and rollback procedure are in:
→ [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

## Discord Notifications
All Recompete.us product work should report to Discord using the wrapper script.
It delegates to `ae notify` in the autonomous-engineering venv — no secret handling
needed here; reads `AE_DISCORD_WEBHOOK_URL` from the environment.

```bash
# At the start of a task
scripts/notify.sh session-started --task P-02 --title "Add search filters"

# When work is complete (commit hash is auto-detected from git)
scripts/notify.sh task-done --task P-02 --title "Add search filters" \
    --tests "87/87 passing" \
    --summary "Filters added to /contracts" \
    --summary "Includes agency, value range, expiry"

# When tests or a command fails
scripts/notify.sh task-failed --task P-02 --stage Testing \
    --error "pytest exited 1: test_auth.py::test_register_rate_limit"

# Send a one-off test ping
scripts/notify.sh test
```

## Conventions
- Never commit `.env` or secrets
- Always run `pytest tests/ -x -q` before committing
- Send Discord notifications at task start and completion via `scripts/notify.sh`
