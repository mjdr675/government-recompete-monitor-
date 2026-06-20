# MASTER ROADMAP — 06: Tasks 201–250
# Epics: E14 (CRM & Billing), E15 (Analytics & Reporting),
#         E16 (Security & Compliance), E17 (Performance & Scalability),
#         E18 (Operations & Monitoring), E19 (Testing & Quality),
#         E20 (Documentation), E22 (AI Agents — Engineering)

---

## EPIC E14 — CRM & Billing

---

### Task 201 — Add Stripe billing portal (upgrade/downgrade/cancel)
**Epic:** E14 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 2
**Objective:** Let subscribers manage their own subscription from a Stripe-hosted billing
portal without contacting support.
**Requirements:**
- `POST /billing/portal` — create Stripe Billing Portal session and redirect
- Stripe product/price setup: Starter ($99), Professional ($199), Team ($299)
- Portal allows: change plan, update payment method, download invoices, cancel
- After cancel: set `org.plan = 'cancelled'`, preserve access until period end
- After upgrade/downgrade: Stripe webhook updates `org.plan`
**Acceptance Criteria:**
- Billing portal accessible from account settings
- Plan changes reflected in org.plan within 60 seconds of webhook
- Cancel does not immediately revoke access
**Dependencies:** Tasks 069, existing Stripe integration
**DB Changes:** `organizations`: add `plan TEXT DEFAULT 'trial'`, `plan_period_end TEXT`, `stripe_subscription_id TEXT`
**API Changes:** `POST /billing/portal`
**Frontend Changes:** "Manage Billing" link in account settings
**Testing:** 4 new tests (mock Stripe)
**Commit:** `feat: add Stripe billing portal for self-service subscription management`
**Follow-up:** Task 202 (plan enforcement)

---

### Task 202 — Enforce plan tier limits
**Epic:** E14 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 2
**Objective:** Gate features and usage by plan tier. Starter = 1–3 users, no API.
Professional = 10 users, no API. Team = unlimited users, API access.
**Requirements:**
- `plan_limits.py` — defines max_users, api_access, export_access per plan
- Check on team invite: enforce max_users limit
- Check on API key generation: only Team plan
- Check on bulk export: only Professional+
- Grace period: 7 days after downgrade before enforcement
- Upgrade prompt shown when limit hit
**Acceptance Criteria:**
- Starter org blocked from inviting 4th user with clear upgrade prompt
- Team plan users can generate API keys
- Downgrades don't immediately remove access (7-day grace)
**Dependencies:** Task 201
**DB Changes:** None (reads org.plan)
**API Changes:** 403 with `{error: "plan_limit", upgrade_url: ...}` on exceeded limits
**Frontend Changes:** Upgrade modal on limit hit
**Testing:** 6 new tests
**Commit:** `feat: enforce plan tier limits with grace period and upgrade prompts`
**Follow-up:** Task 203 (trial management)

---

### Task 203 — Add 14-day trial with no card required
**Epic:** E14 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** New organizations get 14-day full Professional-tier trial. No credit card required.
After trial, downgrade to read-only unless payment added.
**Requirements:**
- On org creation: set `plan='trial'`, `trial_ends_at = now + 14 days`
- Trial users get Professional tier limits
- Dashboard banner: "X days left in your trial — Add Payment Method"
- On `trial_ends_at` passing: Celery task sets `plan='free'` (read-only)
- Free tier: can view contracts, cannot create captures, notes, or alerts
- Email sequence: Day 7 ("7 days left"), Day 12 ("2 days left"), Day 14 ("trial expired")
**Acceptance Criteria:**
- New org has 14-day trial automatically
- Banner shows accurate days remaining
- Trial expiry email sent on correct days
- Expired trial reverts to read-only gracefully
**Dependencies:** Tasks 069, 201, 127
**DB Changes:** `organizations`: columns already set in Task 201
**API Changes:** None
**Frontend Changes:** Trial banner in base.html
**Testing:** 5 new tests
**Commit:** `feat: add 14-day free trial with email sequence and graceful expiry`
**Follow-up:** Task 204 (HubSpot lifecycle sync)

---

### Task 204 — Sync subscription lifecycle to HubSpot
**Epic:** E14 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Keep HubSpot deal stage synchronized with actual subscription state.
**Requirements:**
- Extend `hubspot_service.py` with `sync_subscription_state(email, plan, event_type)`:
  - `trial_started` → move deal to "Trial" stage
  - `payment_added` → move to "Paying Customer"
  - `plan_upgraded` → add note with new plan details
  - `churned` → move deal to "Churned"
- Call from Stripe webhook handler
**Acceptance Criteria:**
- HubSpot deal stage matches subscription state within 5 minutes of event
- Plan name and amount in deal notes on upgrade
**Dependencies:** Task 201, existing hubspot_service.py
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests (mock HubSpot)
**Commit:** `feat: sync subscription lifecycle events to HubSpot deal stages`
**Follow-up:** None

---

### Task 205 — Add usage tracking and metering
**Epic:** E14 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Track feature usage per org for plan enforcement and product analytics.
**Requirements:**
- `usage_events` table: `org_id, user_id, event_type, metadata_json, created_at`
- Track: contract_viewed, capture_created, proposal_created, ai_analysis_requested,
  export_downloaded, api_call_made
- Celery task: aggregate daily usage into `usage_daily_summary` table
- Usage visible to org admin: `GET /settings/usage`
- Usage alerts: email when approaching plan limits (80% of quota)
**Acceptance Criteria:**
- Events recorded without impacting page load time (async log)
- Usage summary page shows events per category, past 30 days
- 80% quota alert sent once per billing period
**Dependencies:** Tasks 064, 069
**DB Changes:** New tables: `usage_events`, `usage_daily_summary`
**API Changes:** `GET /settings/usage`
**Frontend Changes:** Usage dashboard on settings
**Testing:** 4 new tests
**Commit:** `feat: add usage tracking and metering with org usage dashboard`
**Follow-up:** Task 202 (limits use these counts)

---

## EPIC E15 — Analytics & Reporting

---

### Task 206 — Build executive analytics dashboard
**Epic:** E15 | **Milestone:** M4 | **Complexity:** XL | **Sessions:** 3
**Objective:** A dedicated analytics page with org-level pipeline intelligence:
total opportunity value, win rate over time, agency concentration, capture stage funnel.
**Requirements:**
- `GET /analytics` — requires auth (admin+ only)
- Charts (Chart.js):
  1. Pipeline by status: bar chart of opportunity value at each capture stage
  2. Agency concentration: pie chart of opportunities by agency
  3. NAICS distribution: bar chart of opportunities by NAICS sector
  4. Time-to-capture: average days from tracking to proposal submission
  5. Win rate trend: quarterly win rate (WON / (WON + LOST)) past 2 years
- Date range filter: 30d / 90d / 180d / 1y / all time
**Acceptance Criteria:**
- Dashboard loads in < 2 seconds for up to 500 capture opportunities
- Charts render correctly with empty data states
- Date range filter updates all charts without page reload
**Dependencies:** Tasks 062, 151 (capture_opportunities data)
**DB Changes:** None (derived queries)
**API Changes:** `GET /analytics/data?range=90d` returns JSON for all charts
**Frontend Changes:** `templates/analytics.html`
**Testing:** 4 new tests
**Commit:** `feat: add executive analytics dashboard with 5 pipeline intelligence charts`
**Follow-up:** Task 207 (revenue forecasting)

---

### Task 207 — Add revenue forecasting
**Epic:** E15 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Project the org's expected contract revenue over the next 12 months
based on active capture pipeline with pWin estimates.
**Requirements:**
- Revenue forecast = sum(opportunity.value × pwin_estimate) for all PURSUING+ opportunities
- Broken down by quarter
- Confidence bands: optimistic (pWin × 1.2), pessimistic (pWin × 0.8)
- Chart: stacked bar by quarter with confidence band overlay
- Updated in real-time as pWin estimates change on capture opportunities
**Acceptance Criteria:**
- Forecast shown when org has at least 1 capture with pWin set
- "No forecast data — set pWin estimates on your captures" shown otherwise
- Updates within 1 second of pWin change (no Celery needed — live calc)
**Dependencies:** Task 206
**DB Changes:** None
**API Changes:** `GET /analytics/forecast` returns JSON
**Frontend Changes:** Forecast chart on analytics page
**Testing:** 3 new tests
**Commit:** `feat: add revenue forecasting from capture pipeline pWin estimates`
**Follow-up:** None

---

### Task 208 — Add competitor analytics report
**Epic:** E15 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** A dedicated competitor analytics page showing which vendors the org
most frequently competes against and their relative strength.
**Requirements:**
- `GET /analytics/competitors` — aggregate `capture_competitors` data
- Show: top 10 recurring competitors by appearance in org's capture pipeline
- Per competitor: appearance count, win rate against them (WIN if capture = WON, LOSS if LOST)
- Link to vendor profile and AI research for each
**Acceptance Criteria:**
- Shows competitors across all closed captures (WON/LOST)
- Win/loss against each competitor displayed as ratio
- Empty state: "Add competitors to your captures to see this report"
**Dependencies:** Tasks 158, 206
**DB Changes:** None
**API Changes:** `GET /analytics/competitors`
**Frontend Changes:** Competitors tab on analytics page
**Testing:** 3 new tests
**Commit:** `feat: add competitor analytics report with win/loss ratios`
**Follow-up:** None

---

### Task 209 — Add PDF report export (capture opportunity brief)
**Epic:** E15 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Export a formatted PDF capture brief for any capture opportunity.
Useful for presenting to leadership or BD review boards.
**Requirements:**
- `GET /capture/<opp_id>/export.pdf` — generates PDF via WeasyPrint or similar
- PDF content: opportunity summary, agency intel, competitive set, teaming partners,
  go/no-go decision, capture plan (if AI generated), milestones
- Branded with org name and export date
- Limited to Team plan
**Acceptance Criteria:**
- PDF downloads correctly in all browsers
- Content mirrors the capture workspace data
- Org name and date on cover page
**Dependencies:** Tasks 151–158, 202 (plan check)
**DB Changes:** None
**API Changes:** `GET /capture/<opp_id>/export.pdf`
**Frontend Changes:** "Export PDF" button on capture workspace
**Testing:** 2 new tests (content assertions, plan check)
**Commit:** `feat: add PDF export for capture opportunity brief (Team plan)`
**Follow-up:** None

---

## EPIC E16 — Security & Compliance

---

### Task 210 — Add CSRF protection to all state-modifying forms
**Epic:** E16 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Protect all POST/PATCH/DELETE routes against cross-site request forgery.
**Requirements:**
- Add `Flask-WTF` or implement custom CSRF token middleware
- Generate CSRF token per session, store in session, validate on all state-modifying requests
- HTMX requests: include CSRF token in meta tag, read via `X-CSRFToken` header
- Exempt: Stripe webhook (`/stripe/webhook`), SAM.gov callback paths (no session)
- Return 403 with JSON error on CSRF failure
**Acceptance Criteria:**
- POST to any form without valid CSRF token returns 403
- HTMX requests include token automatically via meta tag pattern
- Stripe webhook exempt and functional
- All 84+ existing tests still pass
**Dependencies:** None
**DB Changes:** None
**API Changes:** 403 responses on CSRF failures
**Frontend Changes:** CSRF token in `base.html` `<meta>` tag and all form `<input>` tags
**Testing:** 5 new tests
**Commit:** `feat: add CSRF protection to all state-modifying routes`
**Follow-up:** Task 211 (rate limiting)

---

### Task 211 — Add rate limiting on auth and API endpoints
**Epic:** E16 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Protect against brute-force login attacks and API abuse.
**Requirements:**
- Add `Flask-Limiter` with Redis as storage backend
- Rate limits:
  - `/login` POST: 10 requests / 10 minutes per IP
  - `/register` POST: 5 requests / hour per IP
  - `/forgot-password` POST: 3 requests / hour per IP
  - `/api/*`: 100 requests / minute per API key (Task 234)
  - `/contract/<id>/analyze` (AI): 10 requests / hour per org
- Return 429 with `Retry-After` header
**Acceptance Criteria:**
- 11th login attempt in 10 minutes returns 429
- Legitimate users unaffected in normal use
- Rate limit counters stored in Redis (reset on Redis restart is acceptable)
**Dependencies:** Task 063 (Redis)
**DB Changes:** None
**API Changes:** 429 responses on rate limit
**Frontend Changes:** Friendly message on 429 for auth routes
**Testing:** 5 new tests
**Commit:** `feat: add rate limiting on auth and AI endpoints via Flask-Limiter`
**Follow-up:** None

---

### Task 212 — Add comprehensive audit logging
**Epic:** E16 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Record a tamper-evident audit log of all security-relevant actions
for SOC 2 readiness and customer trust.
**Requirements:**
- `audit_log` table: `id, org_id, user_id, action, resource_type, resource_id, ip_address, user_agent, metadata_json, created_at`
- Log: login (success/fail), logout, register, password change, invite sent/accepted,
  member removed, plan changed, API key created/revoked, capture created/deleted,
  proposal created, export downloaded
- Async logging (do not block requests)
- `GET /settings/audit-log` — org admin can view last 500 entries (paginated)
**Acceptance Criteria:**
- All listed actions recorded within 1 second
- Audit log accessible to org admin only
- Log entries immutable (no UPDATE/DELETE on audit_log)
- IP address and user-agent captured on every entry
**Dependencies:** Tasks 069, 071, 064
**DB Changes:** New table: `audit_log`
**API Changes:** `GET /settings/audit-log`
**Frontend Changes:** Audit log page in settings
**Testing:** 6 new tests
**Commit:** `feat: add comprehensive audit logging for security and SOC 2 readiness`
**Follow-up:** Task 213 (data encryption at rest)

---

### Task 213 — Encrypt sensitive data at rest
**Epic:** E16 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Encrypt sensitive stored values: Slack tokens, integration secrets,
API keys, and webhook signing secrets using application-level encryption.
**Requirements:**
- Create `crypto.py` with `encrypt(plaintext)` / `decrypt(ciphertext)` using
  Fernet (symmetric) with key from `ENCRYPTION_KEY` env var
- Apply to: `org_integrations.access_token_enc`, `org_webhooks.secret`,
  API key values in `api_keys.key_hash` (hash, not encrypt), Stripe customer IDs
- Migration: re-encrypt existing values on startup if unencrypted
- Key rotation support: `ENCRYPTION_KEY_OLD` for decrypting old values
**Acceptance Criteria:**
- Secrets in DB are not readable as plaintext
- Key rotation works without downtime
- Existing integrations continue working after encryption
**Dependencies:** Task 062
**DB Changes:** Column name changes (rename to `_enc` suffix for encrypted columns)
**API Changes:** None
**Frontend Changes:** None
**Testing:** 4 new tests
**Commit:** `feat: add application-level encryption for sensitive stored values`
**Follow-up:** Task 214 (API key management)

---

### Task 214 — Add API key management (Team plan)
**Epic:** E16 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Team plan orgs can generate API keys for programmatic access.
**Requirements:**
- `api_keys` table: `id, org_id, name, key_prefix (first 8 chars), key_hash, created_by, last_used_at, expires_at, is_active`
- Key format: `rcp_live_<random_32_chars>` (shown once on generation)
- `GET/POST/DELETE /settings/api-keys`
- API key authentication: `Authorization: Bearer rcp_live_...` header
- Keys checked against hash, never stored in plaintext
- Rate limit per key (Task 211)
**Acceptance Criteria:**
- Key shown exactly once on creation (cannot retrieve plaintext again)
- Revoke immediately invalidates all requests using that key
- Last used timestamp updated on each API request
**Dependencies:** Tasks 071, 202, 213
**DB Changes:** New table: `api_keys`
**API Changes:** API key auth middleware for `/api/*` routes
**Frontend Changes:** `templates/settings/api_keys.html`
**Testing:** 5 new tests
**Commit:** `feat: add API key management with secure storage and Team plan gate`
**Follow-up:** Task 235 (public API routes)

---

## EPIC E17 — Performance & Scalability

---

### Task 215 — Add Redis query result caching for analytics endpoints
**Epic:** E17 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Cache expensive analytics queries in Redis to achieve < 200ms p95 response.
**Requirements:**
- Create `cache.py` with `get_cached(key, ttl, fn)` wrapper
- Cache: `dashboard_analytics()` (5 min TTL), `opportunity_recommendations()` (10 min),
  `vendor_profile_analytics()` (30 min), `agency_profile()` (30 min)
- Cache key includes org_id for per-tenant isolation
- Invalidate cache on: new ingest, note added, watchlist change
- Log cache hit rate to structured logs
**Acceptance Criteria:**
- Dashboard loads in < 200ms on cache hit
- Cache miss ≤ 1 second for typical dataset
- Cache invalidated correctly on data change
**Dependencies:** Task 063 (Redis), Task 062 (PostgreSQL)
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** 4 new tests (mock Redis)
**Commit:** `feat: add Redis caching for analytics queries with per-tenant isolation`
**Follow-up:** Task 216 (query optimization)

---

### Task 216 — Optimize contract search query performance
**Epic:** E17 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Ensure contract search returns in < 100ms for up to 100K contracts.
**Requirements:**
- Add composite indexes: `(org_id, priority, recompete_score)`, `(org_id, days_remaining)`,
  `(naics_code, agency, days_remaining)`
- Add PostgreSQL GIN index for FTS tsvector column
- Use `EXPLAIN ANALYZE` to identify slow queries
- Add pagination using keyset pagination for large result sets
**Acceptance Criteria:**
- `EXPLAIN ANALYZE` shows Index Scan (not Seq Scan) for all common search paths
- 10,000 contract dataset: search < 50ms, pagination < 20ms
- Existing tests still pass
**Dependencies:** Task 062 (PostgreSQL)
**DB Changes:** New composite indexes (no schema changes)
**API Changes:** None
**Frontend Changes:** None
**Testing:** Add performance benchmark test (skip in CI, mark with `@pytest.mark.benchmark`)
**Commit:** `perf: add composite indexes and GIN FTS for sub-100ms contract search`
**Follow-up:** Task 217 (connection pooling)

---

### Task 217 — Add database connection pooling
**Epic:** E17 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Replace per-request database connections with a connection pool to
handle concurrent gunicorn workers without exhausting PostgreSQL connections.
**Requirements:**
- Use SQLAlchemy `create_engine` with `pool_size=5, max_overflow=10`
- Configure `pool_pre_ping=True` for connection health checks
- Set PostgreSQL `statement_timeout = 5000ms` to prevent runaway queries
- `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` from environment
**Acceptance Criteria:**
- 4 gunicorn workers share a pool of ≤ 20 connections total
- `pg_stat_activity` shows no connection leak after load test
- Slow query timeout prevents page hangs
**Dependencies:** Task 062
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** 2 new tests (pool configuration assertions)
**Commit:** `perf: add SQLAlchemy connection pooling with health checks and query timeout`
**Follow-up:** None

---

## EPIC E18 — Operations & Monitoring

---

### Task 218 — Add structured JSON logging
**Epic:** E18 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Replace Flask's default log format with structured JSON logging for
all request logs, application events, and errors.
**Requirements:**
- Use `python-json-logger` or `structlog`
- Every log entry: `{timestamp, level, request_id, user_id, org_id, path, method, status, duration_ms, message}`
- Request ID generated per request (via `before_request`) and included in all logs for that request
- Log to stdout (Railway captures it)
- Log level configurable via `LOG_LEVEL` env var
**Acceptance Criteria:**
- Railway logs show JSON-formatted entries
- Request ID correlates all log lines within a single request
- Error logs include stack trace in `exception` field
**Dependencies:** None (no PostgreSQL dependency)
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests (assert log output format)
**Commit:** `feat: add structured JSON logging with request ID correlation`
**Follow-up:** Task 219 (Sentry error tracking)

---

### Task 219 — Add Sentry error tracking
**Epic:** E18 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Capture unhandled exceptions and performance traces in Sentry.
**Requirements:**
- Add `sentry-sdk[flask]` to requirements.txt
- Initialize Sentry in `app.py` from `SENTRY_DSN` env var
- Configure: `traces_sample_rate=0.1` (10% of requests traced)
- Tag every event with `org_id` and `user_id` from `g.org` / `g.user`
- Filter out 404 errors (not actionable)
- `SENTRY_DSN` optional — app starts without it
**Acceptance Criteria:**
- Unhandled exceptions appear in Sentry within 30 seconds
- `org_id` and `user_id` visible on every Sentry issue
- 404 errors not in Sentry
**Dependencies:** None
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** 1 new test (Sentry init without DSN does not crash)
**Commit:** `feat: add Sentry error tracking with org and user context`
**Follow-up:** Task 220 (uptime monitoring)

---

### Task 220 — Add /health extended endpoint and uptime monitoring
**Epic:** E18 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Extend `/health` to include dependency checks (DB, Redis, Celery).
Configure external uptime monitoring (Better Uptime or similar).
**Requirements:**
- `GET /health` — unchanged (returns `{status: ok}` without auth)
- `GET /health/deep` — requires internal auth (HEALTH_TOKEN env var), returns:
  `{db: ok/error, redis: ok/error, celery: ok/error, version: <git sha>}`
- `HEALTH_TOKEN` checked via `Authorization: Bearer <token>` header
- Document how to configure uptime check in Railway
**Acceptance Criteria:**
- `/health` still returns 200 (Railway probe unchanged)
- `/health/deep` returns correct component status within 2 seconds
- Returns 500 if any dependency is DOWN
**Dependencies:** Task 063 (Redis check), Task 062 (DB check)
**DB Changes:** None
**API Changes:** `GET /health/deep`
**Frontend Changes:** None
**Testing:** 3 new tests
**Commit:** `feat: add /health/deep endpoint with dependency status checks`
**Follow-up:** Task 221 (CI/CD)

---

### Task 221 — Add GitHub Actions CI pipeline
**Epic:** E18 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Run tests automatically on every push and pull request to main.
**Requirements:**
- `.github/workflows/ci.yml`
- Trigger: push to main, pull_request to main
- Jobs:
  1. `lint`: `ruff check .` (or flake8)
  2. `test`: `pytest -q --tb=short` against SQLite (no PostgreSQL needed in CI)
  3. `security`: `bandit -r .` (basic security scan)
- Cache pip dependencies
- Fail fast: stop on first job failure
- Badge in README
**Acceptance Criteria:**
- CI runs in < 3 minutes
- PR cannot be merged with failing tests
- Badge visible in README showing current status
**Dependencies:** None (can work with SQLite)
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None
**Testing:** No new app tests; CI verifies existing tests pass
**Commit:** `ci: add GitHub Actions pipeline for lint, test, and security scan`
**Follow-up:** Task 222 (staging environment)

---

### Task 222 — Add staging environment on Railway
**Epic:** E18 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** A separate Railway environment with production-identical config, separate
database, and deploy-from-main-branch flow for final verification before production.
**Requirements:**
- New Railway project: `government-recompete-staging`
- Deploy from `staging` branch
- Separate PostgreSQL, Redis, and all env vars (with `_STAGING` suffix convention)
- Staging URL: configurable, access restricted to team IP or basic auth
- Deployment pipeline: main PR → staging → approve → production
**Acceptance Criteria:**
- Staging deploys from `staging` branch independently
- Staging DB is separate from production (no shared data)
- Staging accessible to team for manual testing
**Dependencies:** Task 221 (CI/CD)
**DB Changes:** None (separate DB)
**Deployment:** New Railway project setup (manual one-time step)
**Testing:** None (process/infrastructure)
**Commit:** `docs: add staging environment setup guide in DEPLOYMENT.md`
**Follow-up:** None

---

## EPIC E19 — Testing & Quality

---

### Task 223 — Add integration test suite with test database
**Epic:** E19 | **Milestone:** M3 | **Complexity:** L | **Sessions:** 2–3
**Objective:** Add a full integration test suite that tests request → database → response
flows using a real PostgreSQL test database (not SQLite).
**Requirements:**
- Add `pytest-postgresql` fixture for auto-provisioned test DB
- Create `tests/integration/` directory
- Integration tests: ingest → change detection → recommendation pipeline
- Integration tests: register → login → create capture → add task → export PDF
- Run separately from unit tests (`pytest tests/integration -m integration`)
- CI job: unit tests (SQLite, fast) + integration tests (PostgreSQL, slower)
**Acceptance Criteria:**
- Integration tests run against real PostgreSQL
- Cover all major user flows end to end
- Run in < 5 minutes in CI
**Dependencies:** Task 062, Task 221
**DB Changes:** None
**Testing:** 20+ new integration tests
**Commit:** `test: add integration test suite with real PostgreSQL test database`
**Follow-up:** Task 224 (coverage enforcement)

---

### Task 224 — Enforce 80% test coverage in CI
**Epic:** E19 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Add coverage reporting and fail CI if coverage drops below 80%.
**Requirements:**
- Add `pytest-cov` to requirements
- CI test job: `pytest --cov=. --cov-report=xml --cov-fail-under=80`
- Upload coverage report to Codecov or similar
- Coverage badge in README
- Exclude: `migrations/`, `tests/`, `ai_agent/` from coverage calculation
**Acceptance Criteria:**
- CI fails if coverage < 80%
- Coverage badge shows current % in README
- Coverage report uploaded on every CI run
**Dependencies:** Task 221
**DB Changes:** None
**Testing:** No new tests; enforces existing coverage
**Commit:** `ci: add 80% coverage enforcement with Codecov reporting`
**Follow-up:** None

---

## EPIC E20 — Documentation

---

### Task 225 — Document all routes in README
**Epic:** E20 | **Milestone:** M1 | **Complexity:** XS | **Sessions:** 0.5
**Objective:** Add a route table to README.md covering every current Flask route.
(This is an existing open backlog item from backlog/medium.md.)
**Requirements:**
- Table: Method | Path | Auth Required | Description
- Include all routes from app.py and auth.py
- Keep to one line per route
**Acceptance Criteria:** README table accurate to current route list
**Dependencies:** None
**DB Changes:** None | **API Changes:** None | **Frontend Changes:** None
**Testing:** None
**Commit:** `docs: add complete route table to README`
**Follow-up:** Task 226 (OpenAPI spec)

---

### Task 226 — Generate OpenAPI 3.0 spec for all routes
**Epic:** E20 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Produce a machine-readable API spec used for documentation and future SDK generation.
**Requirements:**
- Use `flask-openapi3` or hand-write `openapi.yaml`
- Document all routes, query parameters, request bodies, response schemas
- Serve at `GET /api/openapi.json` (unauthenticated)
- Swagger UI at `GET /api/docs` (requires Team plan or internal auth)
**Acceptance Criteria:**
- Spec validates with OpenAPI 3.0 validator
- Swagger UI renders all endpoints with example responses
**Dependencies:** Task 214 (API routes)
**DB Changes:** None
**API Changes:** `GET /api/openapi.json`, `GET /api/docs`
**Frontend Changes:** None
**Testing:** 2 new tests (spec validates, Swagger UI accessible)
**Commit:** `docs: add OpenAPI 3.0 spec with Swagger UI at /api/docs`
**Follow-up:** Task 227 (developer guide)

---

### Task 227 — Write developer guide (CONTRIBUTING.md)
**Epic:** E20 | **Milestone:** M4 | **Complexity:** S | **Sessions:** 1
**Objective:** Document the development environment setup, testing, and contribution workflow.
**Requirements:**
- Local setup: prerequisites, env vars, `make dev` command
- Running tests: unit vs. integration
- Adding routes, templates, migrations
- AI agent system: how to add tasks to the queue
- Deployment: branch → staging → production flow
**Acceptance Criteria:**
- New developer can set up local environment in < 20 minutes following the guide
- All commands in guide tested and accurate
**Dependencies:** Task 222
**DB Changes:** None | **API Changes:** None | **Frontend Changes:** None
**Testing:** None
**Commit:** `docs: add CONTRIBUTING.md developer guide`
**Follow-up:** Task 228 (user guide)

---

### Task 228 — Write user guide and in-app help
**Epic:** E20 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Help users discover features without requiring a demo call.
**Requirements:**
- `GET /help` — help center landing page (static, Jinja2)
- Articles: Getting Started, Finding Opportunities, Setting Up Alerts, Capture Workspace,
  Interpreting the Recompete Score
- In-app tooltips on: recompete score (hover), priority labels, score breakdown
- Link to help center from footer and nav
**Acceptance Criteria:**
- Help articles answer top 10 user questions
- Tooltip shows on recompete score hover throughout the app
**Dependencies:** None
**DB Changes:** None
**API Changes:** `GET /help`, `GET /help/<article-slug>`
**Frontend Changes:** Help page, tooltips in base.html
**Testing:** 2 new tests (routes accessible, correct template)
**Commit:** `docs: add user help center and in-app tooltips for key concepts`
**Follow-up:** None

---

## EPIC E22 — AI Agents (Engineering Automation)

---

### Task 229 — Integrate AI agent system with PostgreSQL repo memory
**Epic:** E22 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Upgrade `ai_agent/memory.py` (RepoMemory) to store the codebase index in
PostgreSQL instead of a local SQLite `.ai_agent_memory.db` file. Enables team-shared
agent memory and cloud-hosted agent runs.
**Requirements:**
- Add `AGENT_MEMORY_DB_URL` env var (can point to same PostgreSQL or separate)
- `ai_agent/memory.py`: replace SQLite schema with PostgreSQL-compatible schema
- All existing `RepoMemory` API preserved (`find_function`, `find_route`, etc.)
- Local SQLite fallback when `AGENT_MEMORY_DB_URL` unset
**Acceptance Criteria:**
- All 32 memory tests pass against PostgreSQL backend
- Local dev still works with SQLite fallback
**Dependencies:** Task 062
**DB Changes:** Agent memory schema tables in PostgreSQL
**API Changes:** None (internal to agent system)
**Testing:** All existing `test_memory.py` tests + 2 new PostgreSQL-specific tests
**Commit:** `feat(agent): migrate RepoMemory to PostgreSQL with SQLite fallback`
**Follow-up:** Task 230 (cloud agent run support)

---

### Task 230 — Add cloud-hosted agent execution mode
**Epic:** E22 | **Milestone:** M3 | **Complexity:** XL | **Sessions:** 3
**Objective:** Allow the AI agent to run on Railway (as a one-off job or scheduled task)
instead of requiring a local machine. The agent picks up tasks from the queue/, executes,
commits to a branch, and opens a PR.
**Requirements:**
- New Railway service: `agent` (runs on schedule or webhook trigger)
- `Procfile` entry: `agent: python ai_agent/agent.py` (one-off job mode)
- Agent mode: `AGENT_MODE=cloud` — commits to `ai-agent` branch, opens GitHub PR via gh CLI
- GitHub token (`GITHUB_TOKEN`) in Railway env for PR creation
- Safety: cloud mode adds extra reviewer check before commit
**Acceptance Criteria:**
- Agent triggered via Railway job runs one task and exits
- PR created automatically with task description and test results
- Agent never pushes to main
**Dependencies:** Task 229, Tasks 048 (AI Reviewer), 049 (PR Builder)
**DB Changes:** None
**API Changes:** None
**Testing:** 4 new tests (mock git, mock gh CLI)
**Commit:** `feat(agent): add cloud execution mode with automatic PR creation`
**Follow-up:** Task 231 (autonomous task prioritization)

---

### Task 231 — AI-driven task prioritization for engineering backlog
**Epic:** E22 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** The AI CTO agent (Task 055) analyzes the backlog, current milestone status,
and technical debt, and reorders the queue to maximize customer value.
**Requirements:**
- Extend Task 055 (AI CTO) to write a ranked task list to `ai_agent/PRIORITY_QUEUE.md`
- Input: MASTER_ROADMAP files, milestone progress, test count, open bugs
- Output: ordered list of next 10 tasks with rationale for each
- Human reviews and approves before queue is updated
- Run weekly via Celery beat on the agent service
**Acceptance Criteria:**
- `PRIORITY_QUEUE.md` updated weekly with 10 prioritized tasks
- Rationale for each task cites milestone alignment and technical dependencies
- Queue update requires human approval (file is a proposal, not auto-executed)
**Dependencies:** Task 055, Task 230
**DB Changes:** None
**API Changes:** None
**Testing:** 2 new tests
**Commit:** `feat(agent): add AI-driven task prioritization producing PRIORITY_QUEUE.md`
**Follow-up:** None
