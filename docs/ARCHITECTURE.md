# ARCHITECTURE.md — System Architecture

A complete technical reference for the government recompete intelligence platform.
For the product vision and roadmap see `company/VISION.md` and `company/ROADMAP.md`.
For coding standards see `docs/STYLE.md`. For feature-level architecture see `docs/PRODUCT.md`.

---

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser                             │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│                  Railway (cloud)                        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │          Flask (app.py + auth.py blueprint)      │   │
│  │  require_login · CSRFProtect · Flask-Limiter     │   │
│  │  Jinja2 templates · session cookie (SECRET_KEY)  │   │
│  └──────────────┬──────────────────┬────────────────┘   │
│                 │                  │                     │
│  ┌──────────────▼────┐  ┌──────────▼─────────────────┐  │
│  │  db.py / users.py │  │  analytics.py              │  │
│  │  SQLAlchemy Core  │  │  report_builder.py         │  │
│  │  PostgreSQL (prod)│  │  change_detector.py        │  │
│  │  SQLite (dev/test)│  │  email_service.py (Sprint D│  │
│  └───────────────────┘  └────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Celery Worker + Beat (tasks.py)                 │   │
│  │  Broker: Redis · Backend: Redis                  │   │
│  │  Schedules: nightly ingest 02:00 UTC             │   │
│  │             heartbeat every 5 min                │   │
│  │             beat health check every 10 min       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PostgreSQL (Railway plugin)                     │   │
│  │  Schema: migrations/001_initial_pg.sql           │   │
│  │  Applied via Procfile release step               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Redis (Railway plugin)                          │   │
│  │  Celery broker + result backend                  │   │
│  │  beat:health key (TTL 15 min)                    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Flask Application

**Entry point:** `app.py`  
**Pattern:** route handler only — no business logic in routes  
**Auth:** `auth.py` Blueprint, session cookie, `require_login` before_request  
**CSRF:** Flask-WTF `CSRFProtect` — all POST forms require `csrf_token`; JSON API routes are `@csrf.exempt`  
**Rate limiting:** Flask-Limiter — `POST /login` limited to 5/min per IP  

### Request lifecycle

```
Request arrives
  → require_login (app before_request)
      → path in _PUBLIC_PATHS frozenset? → pass through
      → method==DELETE and path starts /searches/? → pass through (JSON auth)
      → method==POST and path ends /note? → pass through (JSON auth)
      → session has user_id? → pass through
      → else → redirect /login?next=<path>
  → load_logged_in_user (auth blueprint before_app_request)
      → sets g.user from DB
      → sets g.watchlist_count (COUNT from user_watchlist, 0 if not logged in)
  → route handler
      → queries db.py / analytics.py
      → renders Jinja2 template
  → response
```

### Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | None | Railway uptime probe |
| GET/POST | `/login` | None | Sign-in — POST rate-limited 5/min/IP |
| GET/POST | `/register` | None | Account creation |
| GET | `/logout` | None | Clear session |
| GET | `/` | Required | Dashboard with freshness indicator |
| GET | `/contracts` | Required | Searchable/filterable contract list |
| GET | `/contracts/export.csv` | Required | CSV export of current filter |
| GET | `/contract/<id>` | Required | Contract detail + notes |
| POST | `/contract/<id>/note` | JSON self-auth | Add private note |
| GET | `/compare` | Required | Side-by-side comparison |
| GET | `/vendor/<name>` | Required | Vendor intelligence |
| GET | `/agency/<name>` | Required | Agency intelligence |
| GET | `/views` | Required | Saved view list |
| GET | `/views/<id>` | Required | Saved view (redirect) |
| GET/POST | `/ingest` | Required | CSV upload / API pull |
| GET | `/ingest/status` | Required | Ingest status (task_id or log tail) |
| GET | `/watchlist` | Required | Bookmarked contracts page |
| POST | `/watchlist/add` | JSON self-auth | Bookmark a contract |
| POST | `/watchlist/remove` | JSON self-auth | Remove bookmark |
| GET | `/searches` | Required | Saved searches page |
| POST | `/searches/save` | JSON self-auth | Save current filter as named search |
| DELETE | `/searches/<id>` | JSON self-auth | Delete saved search |
| GET | `/api/data-freshness` | None | Last ingest timestamp + record count |
| GET/POST | `/demo` | None | Demo request form |
| GET/POST | `/early-access` | None | Early access sign-up |
| POST | `/create-checkout-session` | None | Stripe checkout |
| POST | `/stripe/webhook` | None (sig-verified) | Stripe event handler |
| GET | `/success` | None | Post-checkout success |
| GET | `/cancel` | None | Post-checkout cancel |

### `_PUBLIC_PATHS` frozenset

Routes in this set bypass `require_login`. JSON API routes with dynamic path segments
(`/searches/<id>` DELETE, `/contract/<id>/note` POST) are not in the frozenset — they
use method+prefix checks in `require_login` and handle their own auth (return 401 JSON).

---

## Database

**Engine:** SQLAlchemy Core ≥ 2.0 (`get_engine()` in `db.py`)  
**Production:** PostgreSQL via `DATABASE_URL` env var  
**Development/test:** SQLite (`contracts.db`, or `tmp_path` fixture override)  
**Initialization:** `db.init_db()` — SQLite only; PostgreSQL uses `migrations/001_initial_pg.sql`  
**Dialect branching:** `is_pg = engine.dialect.name == "postgresql"` — used for `RETURNING id` vs `lastrowid`  
**Engine caching:** `_cached_engine(url)` is LRU-cached by URL string for connection reuse  

### Schema tables

| Table | Purpose |
|---|---|
| `contracts` | Core contract records. FTS via FTS5 (SQLite) or `tsvector` generated column (PostgreSQL) |
| `contract_snapshots` | Point-in-time copies for change detection. Unique on `(run_date, internal_id)` |
| `changes` | Detected contract changes between snapshot runs |
| `users` | Registered accounts. `email UNIQUE`, scrypt password hash, `is_active` flag |
| `celery_task_log` | Celery task execution records (`RUNNING` → `SUCCESS`/`FAILURE`) |
| `user_watchlist` | Per-user bookmarked contracts. `UNIQUE(user_id, internal_id)` |
| `user_saved_searches` | Per-user named filter presets. Stores `query_params_json` |
| `contract_notes` | Per-user private notes on contracts |
| `ingest_log` | Ingest run metadata: `run_date`, `source`, `record_count`, `duration_seconds`, `status`, `error_message` |
| `demo_requests` | Demo form submissions with optional HubSpot IDs |
| `early_access` | Early access sign-ups. `email UNIQUE` |

### Indexes (`contracts`)

| Index | Columns | Serves |
|---|---|---|
| `idx_contracts_vendor` | `vendor` | Vendor profile lookups, `agency LIKE` is separate |
| `idx_contracts_agency` | `agency` | Agency profile lookups |
| `idx_contracts_priority` | `priority` | Priority filter, dashboard critical list |
| `idx_contracts_score` | `recompete_score DESC` | Default sort, top-opportunity lists |
| `idx_contracts_days_remaining` | `days_remaining` | Dashboard "upcoming" range scan, open/expired status filter, watchlist expiry alerts, vendor/agency `ORDER BY days_remaining` |

SQLite indexes are created in `db.init_db()`; PostgreSQL mirrors them in `migrations/`
(`001_initial_pg.sql` plus per-feature migrations such as
`004_contracts_days_remaining_index.sql`). Keep the two in sync when adding an index.

### SQLAlchemy Core patterns

All queries use named parameters (`:param`), `text()`, and `.mappings().fetchone()/fetchall()`.
No ORM models. Results are converted to `dict` before use in templates.

```python
# Standard read pattern
with get_engine().connect() as conn:
    row = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": uid}).mappings().fetchone()

# Standard write pattern
with get_engine().begin() as conn:  # auto-commit on exit
    conn.execute(text("INSERT INTO ... VALUES (:a, :b)"), {"a": ..., "b": ...})
```

---

## Authentication

**Module:** `auth.py` (Flask Blueprint) + `users.py` (model)  
**Session store:** Flask signed cookie — requires `SECRET_KEY` env var  
**Password hashing:** Werkzeug `generate_password_hash` with scrypt  

### Security controls

| Control | Implementation |
|---|---|
| CSRF | Flask-WTF `CSRFProtect` — `csrf_token` hidden field on all POST forms; `@csrf.exempt` on JSON API routes and Stripe webhook |
| Rate limiting | Flask-Limiter 4.x — `POST /login` 5/min/IP; `app.view_functions["auth.login"]` reassigned to wrapper so limit is enforced |
| Stripe webhook | `STRIPE_WEBHOOK_SECRET` env var required — unsigned requests return 400; no fallback |
| Session | Signed cookie; `g.user` populated from DB on every request (not trusted from session) |
| Email normalization | Lowercased and stripped on creation and lookup |

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing |
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string |
| `REDIS_URL` | Yes (prod) | Celery broker + backend |
| `STRIPE_SECRET_KEY` | Yes (prod) | Stripe API |
| `STRIPE_WEBHOOK_SECRET` | Yes (prod) | Webhook signature verification |
| `HUBSPOT_ACCESS_TOKEN` | No | CRM integration |
| `APP_URL` | No | Base URL for email links (default `https://govrecompete.com`) |
| `EMAIL_API_KEY` | No | Resend API key — email silently skipped if absent |
| `SMTP_FROM` | No | Sender address (default `noreply@govrecompete.com`) |
| `SENTRY_DSN` | No | Sentry error tracking — disabled if absent |

---

## Background Tasks (Celery)

**Module:** `tasks.py`  
**Broker/backend:** Redis (`REDIS_URL`)  
**Serializer:** JSON  

| Task | Schedule | Purpose |
|---|---|---|
| `tasks.run_ingest` | Daily 02:00 UTC | Runs `janitorial_recompete_report.main()`: fetches from USAspending, writes the CSV, then **persists to the DB** via `save_snapshot()` (contracts upsert + `contract_snapshots`) and `detect_changes()`. Writes to `ingest_log`; logs ERROR if `record_count < 10`. Idempotent — safe to rerun. |
| `tasks.heartbeat` | Every 5 min | Writes timestamp to `beat:health` Redis key (TTL 15 min) |
| `tasks.check_beat_health` | Every 10 min | Logs ERROR if `beat:health` key is missing or stale |
| `tasks.send_email_task` | On-demand | Wraps `email_service.send_email()`; retries up to 3× on failure |

### Ingest quality alert

After each successful `run_ingest`, `record_count = COUNT(*) FROM contracts` is checked.
If `record_count < _QUALITY_THRESHOLD` (10), an ERROR is logged. The `ingest_log` row
is still written as `status="success"` — the alert signals a data quality concern, not a task failure.

---

## Email Infrastructure (Sprint D)

**Module:** `email_service.py`  
**Provider:** Resend (REST API at `https://api.resend.com/emails`)  
**Auth:** `EMAIL_API_KEY` env var (Bearer token)  
**Sender:** `SMTP_FROM` env var  

If `EMAIL_API_KEY` is not set, `send_email()` logs a WARNING and returns `None`.
All callers must handle a `None` return gracefully.

Email templates live in `templates/email/`. Child templates extend `email/base.html`
(HTML, inline CSS only — no `<style>` blocks for Gmail compatibility) and `email/base.txt`.

---

## Testing

**Runner:** pytest  
**Location:** `tests/`  
**Count:** 941 tests (as of Sprint C completion)  
**Isolation:** `tmp_path` fixtures, `monkeypatch` for `DB_PATH` + `_cached_engine.cache_clear()`

### Test files

| File | What it tests |
|---|---|
| `test_app.py` | Flask routes — contracts, compare, vendor, agency, CSV export, webhook, dashboard freshness |
| `test_auth.py` | Auth — registration, login, logout, CSRF, rate limiting |
| `test_analytics.py` | Dashboard analytics, vendor/agency profiles, opportunity recommendations |
| `test_db.py` | Schema init, upsert, FTS, watchlist constraints, saved searches, contract_notes |
| `test_watchlist.py` | Watchlist add/remove routes + /watchlist page |
| `test_saved_searches.py` | /searches/save, DELETE /searches/:id, /searches page |
| `test_notes.py` | POST /contract/:id/note |
| `test_data_freshness.py` | GET /api/data-freshness |
| `test_celery_ingest.py` | run_ingest task, ingest_log, quality alert, beat schedule |
| `test_memory.py` | AI agent repository memory index |
| `test_patcher.py` | AI agent patch pipeline |

### Test fixture pattern

```python
@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()

@pytest.fixture()
def client(test_db):
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    ...
```

---

## Deployment

### Procfile

```
release: python -c "import os; url=os.environ.get('DATABASE_URL',''); exec(open('migrations/001_initial_pg.sql').read()) if url else None"
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
worker: celery -A tasks worker --loglevel=info
beat: celery -A tasks beat --loglevel=info
```

### Railway environment variables (minimum required)

`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

### Deploy protocol

1. `pytest -q` — full suite must pass (zero failures)
2. `git push origin main`
3. Railway runs release command (PostgreSQL migration)
4. Railway starts web + worker + beat processes
5. `GET /health` → `{"status": "ok"}` — verify within 60s

---

## Directory Structure

```
/
├── app.py                   # Flask app — routes only
├── auth.py                  # Auth Blueprint (/login /register /logout)
├── users.py                 # User model (SQLAlchemy Core)
├── db.py                    # Database — schema, get_engine(), init_db(), queries
├── analytics.py             # Aggregation queries (SQLAlchemy Core)
├── email_service.py         # send_email() via Resend API
├── report_builder.py        # Dashboard summary builder
├── change_detector.py       # Contract change detection
├── views.py                 # Saved view presets
├── tasks.py                 # Celery tasks (ingest, heartbeat, send_email_task)
├── Procfile                 # Railway startup
├── requirements.txt         # Pinned Python dependencies
├── migrations/
│   └── 001_initial_pg.sql   # Idempotent PostgreSQL schema
│
├── templates/
│   ├── base.html            # Layout, nav (Dashboard/Contracts/Watchlist/Saved Searches/Views/Ingest)
│   ├── dashboard.html       # Analytics + freshness indicator
│   ├── contracts.html       # List with watch toggles, compare, save search, CSV export
│   ├── contract_detail.html # Detail + bookmark toggle + notes
│   ├── watchlist.html       # Bookmarked contracts
│   ├── searches.html        # Saved searches
│   ├── compare.html
│   ├── vendor.html
│   ├── agency.html
│   ├── views.html
│   ├── ingest.html
│   ├── login.html
│   ├── register.html
│   ├── demo.html
│   ├── early_access.html
│   └── email/
│       ├── base.html        # Branded email layout (inline CSS)
│       ├── base.txt         # Plain-text email layout
│       ├── welcome.html     # Welcome email (sent on registration)
│       └── welcome.txt
│
├── tests/                   # pytest suite (941 tests)
│   ├── test_app.py
│   ├── test_auth.py
│   ├── test_analytics.py
│   ├── test_db.py
│   ├── test_watchlist.py
│   ├── test_saved_searches.py
│   ├── test_notes.py
│   ├── test_data_freshness.py
│   ├── test_celery_ingest.py
│   ├── test_memory.py
│   └── test_patcher.py
│
├── ai_agent/                # AI engineering system
│   ├── queue/               # Pending tasks (dependency-ordered)
│   ├── done/                # Completed task records
│   └── CURRENT_STATE.md     # Point-in-time system snapshot
│
├── company/                 # Business and product documents
│   ├── SPRINT.md            # Active sprint (M3)
│   └── ...
│
├── docs/
│   ├── ARCHITECTURE.md      # This file
│   ├── PRODUCT.md
│   └── STYLE.md
│
└── TASK_LOG.md              # One-line-per-task history
```

---

## Sprint Status (as of Task 093)

| Sprint | Status | Tasks |
|---|---|---|
| A — Platform Stability | **Complete** | PostgreSQL compat, CSRF, rate limiting, webhook sig, pinned deps |
| B — Retention Core | **Complete** | Watchlist, saved searches, contract notes, CSV export |
| C — Data Trust | **Complete** | ingest_log, /api/data-freshness, dashboard freshness, quality alert |
| D — Email Infrastructure | **In progress** | email_service.py, Celery task, templates, welcome email on register |
| E — Expiration Alerts | Not started | Depends on B (done) + D |
| F — Monetization | Not started | Depends on A (done) + D |
| G — Operational Excellence | **In progress** | Sentry (Task 101) |
