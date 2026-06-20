# MASTER ROADMAP — 03: Tasks 056–100
# Epics: E01 (Immediate Backlog), E02 (Platform Foundation), E03 (Auth & Users),
#         E04 (Onboarding), E05 (Company Intelligence, partial)

---

## EPIC E01 — Immediate Backlog (Carry-Forward)

---

### Task 056 — Add min_value filter to get_contracts()
**Epic:** E01 | **Milestone:** M1 | **Complexity:** S | **Sessions:** 1
**Objective:** The High Value Contracts saved view returns all contracts because
`get_contracts()` has no min_value parameter. Add it so the view works correctly.
**Business Value:** Customers using the High Value view see incorrect results.
**Requirements:**
- Add `min_value=None` param to `get_contracts()` in `db.py`
- When set, add `AND c.value >= ?` to query
- Pass `request.args.get('min_value')` through `/contracts` route in `app.py`
- Update `SAVED_VIEWS` in `views.py` to include `min_value` for the High Value view
**Acceptance Criteria:**
- `/contracts?min_value=1000000` returns only contracts with value >= $1M
- High Value saved view correctly filters to ≥ $1M contracts
- Negative min_value returns 400
**Dependencies:** None
**DB Changes:** None
**API Changes:** `/contracts` accepts `min_value` query param
**Frontend Changes:** None (param passthrough only)
**Testing:** Add test for min_value filter in `test_db.py` and route test in `test_app.py`
**Docs:** Update route table in README
**Deployment:** None
**Commit:** `feat: add min_value filter to get_contracts and /contracts route`
**Follow-up:** Add max_value filter (Task 097)

---

### Task 057 — Add /health unit test
**Epic:** E01 | **Milestone:** M1 | **Complexity:** XS | **Sessions:** 0.5
**Objective:** Create `tests/test_health.py` with a basic health check test.
**Business Value:** CI pipeline will catch health endpoint regressions.
**Requirements:**
- Import Flask test client
- Assert `GET /health` returns 200 with `{"status": "ok"}`
- Assert unauthenticated access (no session) returns 200
**Acceptance Criteria:** Test passes, no auth required, correct JSON body
**Dependencies:** None
**DB Changes:** None | **API Changes:** None | **Frontend Changes:** None
**Testing:** New file `tests/test_health.py` with 2 tests
**Commit:** `test: add /health endpoint unit tests`
**Follow-up:** Task 222 (rate limiting on all endpoints)

---

### Task 058 — Add ingest logging and /ingest/status route
**Epic:** E01 | **Milestone:** M1 | **Complexity:** S | **Sessions:** 1
**Objective:** Log subprocess stdout/stderr from SAM.gov API pull to `ingest.log`.
Add `GET /ingest/status` returning the last 50 lines.
**Business Value:** Users can verify ingest is running and diagnose failures.
**Requirements:**
- Redirect `recompete_report.py` subprocess stdout/stderr to `ingest.log`
- `GET /ingest/status` reads and returns last 50 lines as `text/plain`
- Route requires auth
- Log file rotates at 1 MB (use `logging.handlers.RotatingFileHandler`)
**Acceptance Criteria:**
- After API pull triggered, `/ingest/status` shows log output
- Route returns 200 with plain text, requires login
**Dependencies:** None
**DB Changes:** None
**API Changes:** New route `GET /ingest/status`
**Frontend Changes:** Add link to `/ingest/status` from ingest.html
**Testing:** Mock subprocess, assert log file written, assert route returns 200
**Commit:** `feat: add ingest logging and /ingest/status route`
**Follow-up:** Task 065 (move to Celery background job)

---

### Task 059 — Fix human-readable labels in views.html
**Epic:** E01 | **Milestone:** M1 | **Complexity:** XS | **Sessions:** 0.5
**Objective:** Replace raw dict keys like `days: 90` with friendly labels.
**Requirements:**
- In `templates/views.html`, replace raw filter key display with label map
- E.g., `days: 90` → `Expiring within: 90 days`, `priority: CRITICAL` → `Priority: Critical`
**Acceptance Criteria:** All saved views display human-readable filter summaries
**Dependencies:** None | **DB Changes:** None | **API Changes:** None
**Frontend Changes:** `templates/views.html` label rendering
**Testing:** Add template render test asserting friendly labels appear
**Commit:** `fix: display human-readable filter labels in saved views`
**Follow-up:** None

---

### Task 060 — Add first/last page buttons and page count to contracts.html
**Epic:** E01 | **Milestone:** M1 | **Complexity:** XS | **Sessions:** 0.5
**Objective:** Contract list pagination is missing first/last buttons and total page count.
**Requirements:**
- Add "First" and "Last" page links to pagination in `templates/contracts.html`
- Display "Page X of Y" based on total count and page size
- Disable First/Prev when on page 1; disable Next/Last when on last page
**Acceptance Criteria:** All four navigation controls render correctly on page 1, middle, and last page
**Dependencies:** None | **DB Changes:** None | **API Changes:** None
**Frontend Changes:** `templates/contracts.html` pagination block
**Testing:** Update `test_app.py` contracts route tests to assert pagination HTML
**Commit:** `fix: add first/last page buttons and page count to contracts list`
**Follow-up:** None

---

## EPIC E02 — Platform Foundation

---

### Task 061 — Provision PostgreSQL on Railway and add DATABASE_URL config
**Epic:** E02 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Add PostgreSQL as a Railway plugin and wire DATABASE_URL into the app.
**Business Value:** Foundation for multi-tenant, concurrent-write capable architecture.
**Requirements:**
- Add Railway PostgreSQL plugin to project
- Add `DATABASE_URL` to environment variables
- Update `db.py` to detect `DATABASE_URL` and prefer it over SQLite `DB_PATH`
- Keep SQLite as fallback for local dev if `DATABASE_URL` is unset
- Add `psycopg2-binary` to `requirements.txt`
**Acceptance Criteria:**
- App starts without error when `DATABASE_URL` is set
- Falls back to SQLite when `DATABASE_URL` is absent
- `/health` returns 200 in both modes
**Dependencies:** None
**DB Changes:** None (schema migration is Task 062)
**API Changes:** None | **Frontend Changes:** None
**Testing:** Test that `connect()` returns correct connection type per env
**Commit:** `feat: add PostgreSQL support with DATABASE_URL env var`
**Follow-up:** Task 062 (schema migration)

---

### Task 062 — Migrate schema from SQLite to PostgreSQL
**Epic:** E02 | **Milestone:** M2 | **Complexity:** XL | **Sessions:** 3–4
**Objective:** Rewrite `db.py` using SQLAlchemy Core with PostgreSQL-compatible SQL.
All existing tables and all existing queries must work on PostgreSQL.
**Business Value:** Enables concurrent multi-user writes, persistent data, multi-tenancy.
**Requirements:**
- Add SQLAlchemy Core to requirements (`sqlalchemy>=2.0`)
- Rewrite `init_db()` to create all tables on PostgreSQL (or SQLite for dev)
- Port all raw SQL in db.py, analytics.py, change_detector.py to SQLAlchemy text()
- Replace FTS5 virtual table with PostgreSQL `tsvector` + `GIN` index
- Rewrite FTS triggers as PostgreSQL triggers or update tsvector on upsert
- All existing tests must pass with the new backend
- Write a one-time migration script `migrations/001_initial_pg.py`
**Acceptance Criteria:**
- All 84+ existing tests pass against PostgreSQL test database
- FTS search returns same results as before
- No data loss in migration script (idempotent)
- SQLite still works for local dev (`DATABASE_URL` unset)
**Dependencies:** Task 061
**DB Changes:** Full schema port; add tsvector column to contracts
**API Changes:** None | **Frontend Changes:** None
**Testing:** Parametrize DB tests to run against both SQLite and PostgreSQL
**Deployment:** Migration runs from `Procfile` before gunicorn starts
**Commit:** `feat: migrate database layer to PostgreSQL with SQLAlchemy Core`
**Follow-up:** Task 063 (Redis), Task 069 (org model)

---

### Task 063 — Add Redis service to Railway
**Epic:** E02 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Add Railway Redis plugin and wire REDIS_URL into the app config.
**Requirements:**
- Add Railway Redis plugin
- Add `redis` and `celery` to requirements.txt
- Create `tasks.py` as the Celery app entry point (`tasks = Celery('recompete', broker=REDIS_URL)`)
- Add `REDIS_URL` to environment config
- Test Redis connection on startup (log warning if unavailable, do not crash)
**Acceptance Criteria:**
- `tasks.py` imports without error
- App starts when Redis is unavailable (degraded mode, not crash)
- `/health` still returns 200
**Dependencies:** Task 061
**DB Changes:** None | **API Changes:** None | **Frontend Changes:** None
**Testing:** Test Celery app instantiation, mock Redis connection
**Commit:** `feat: add Redis service and Celery task app skeleton`
**Follow-up:** Task 064 (background tasks)

---

### Task 064 — Add Celery worker to Procfile and wire first background task
**Epic:** E02 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Add Celery worker service to Railway Procfile and prove the task queue works.
**Requirements:**
- Add `worker: celery -A tasks worker --loglevel=info` to Procfile
- Add `beat: celery -A tasks beat --loglevel=info` to Procfile
- Create `tasks/noop_task.py` as a no-op heartbeat task (proves queue works)
- Schedule heartbeat every 5 minutes via Celery beat
- Log task execution to structured logger
**Acceptance Criteria:**
- Worker starts without error on Railway
- Heartbeat task executes every 5 minutes (visible in logs)
- Web process is unaffected by worker crashes
**Dependencies:** Task 063
**DB Changes:** Add `celery_task_log` table (id, task_name, status, created_at, result_json)
**API Changes:** None | **Frontend Changes:** None
**Testing:** Test task registration, test heartbeat task runs
**Commit:** `feat: add Celery worker and beat scheduler to Railway deployment`
**Follow-up:** Task 065 (move ingest to Celery)

---

### Task 065 — Move SAM.gov API pull to Celery background task
**Epic:** E02 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Replace `subprocess.Popen` ingest with a Celery task. Add `/ingest/status`
polling to show progress.
**Requirements:**
- Create `tasks/ingest_task.py` with `run_ingest()` Celery task
- Task calls `recompete_report.py` logic directly (no subprocess)
- `/ingest` POST `action=api` enqueues the Celery task and returns task_id
- `/ingest/status?task_id=<id>` returns `{status, progress, message}`
- Schedule nightly ingest via Celery beat at 02:00 UTC
**Acceptance Criteria:**
- Ingest triggered from UI runs as background Celery task
- Status polling shows PENDING → RUNNING → SUCCESS/FAILURE
- Nightly schedule appears in beat log
**Dependencies:** Tasks 063, 064
**DB Changes:** None (use celery_task_log from Task 064)
**API Changes:** `/ingest/status` returns JSON with task progress
**Frontend Changes:** Update `ingest.html` to poll status
**Testing:** Mock Celery task, test enqueue and status endpoints
**Commit:** `feat: move SAM.gov ingest to Celery background task with nightly schedule`
**Follow-up:** Task 087 (nightly contract scan with change detection)

---

## EPIC E03 — Authentication & User Management

---

### Task 066 — Add email verification on registration
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Require email verification before granting full access. Send verification
email on registration.
**Requirements:**
- Add `email_verified` (bool, default false) and `verification_token` (text) to users table
- On registration, generate UUID token, store, send verification email via transactional email
- Add `GET /verify-email?token=<tok>` route that sets `email_verified=true`
- Unverified users see a banner and cannot access /contracts, /vendor, /agency
- Resend verification link available from the banner
**Acceptance Criteria:**
- Registration sends email with verification link
- Clicking link marks user as verified and redirects to dashboard
- Unverified user cannot access protected routes
- Expired token (24h) shows friendly error and resend option
**Dependencies:** Task 063 (email delivery needs transactional email — see Task 174)
**Note:** Can be merged with Task 174 (email integration) for single session
**DB Changes:** `users` table: add `email_verified BOOLEAN DEFAULT FALSE`, `verification_token TEXT`, `verification_sent_at TEXT`
**API Changes:** New routes: `GET /verify-email`, `POST /resend-verification`
**Frontend Changes:** Banner in base.html for unverified state
**Testing:** 6 new tests in test_auth.py
**Commit:** `feat: add email verification on registration`
**Follow-up:** Task 067 (password reset)

---

### Task 067 — Add password reset via email token
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow users to reset their password via a time-limited email token.
**Requirements:**
- `GET/POST /forgot-password` — submit email, send reset link if account exists
- Add `reset_token` and `reset_token_expires_at` to users table
- `GET /reset-password?token=<tok>` — show new password form
- `POST /reset-password` — validate token (< 1h), update password hash, invalidate token
- Send confirmation email after successful reset
**Acceptance Criteria:**
- Reset email sent within 30 seconds of request
- Token expires after 1 hour; expired token shows friendly error
- Password successfully updated; user can log in with new password
- Old token cannot be reused
**Dependencies:** Task 066, Task 174
**DB Changes:** `users`: add `reset_token TEXT`, `reset_token_expires_at TEXT`
**API Changes:** `GET/POST /forgot-password`, `GET/POST /reset-password`
**Frontend Changes:** New templates: `forgot_password.html`, `reset_password.html`
**Testing:** 8 new tests in test_auth.py
**Commit:** `feat: add password reset via time-limited email token`
**Follow-up:** Task 068 (user profile)

---

### Task 068 — Add user profile page
**Epic:** E03 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Let users edit their display name, company name, and NAICS codes of interest.
**Requirements:**
- `GET/POST /profile` — view and edit profile fields
- Add `display_name TEXT`, `company_name TEXT`, `naics_codes TEXT` to users table
- Store NAICS codes as comma-separated string
- Profile changes reflected in nav header (display name instead of email)
**Acceptance Criteria:**
- User can update name and company without losing session
- NAICS codes saved as comma-separated and displayed correctly
- Profile page requires auth
**Dependencies:** Task 062
**DB Changes:** `users`: add `display_name TEXT`, `company_name TEXT`, `naics_codes TEXT`
**API Changes:** `GET/POST /profile`
**Frontend Changes:** `templates/profile.html`, update `base.html` nav
**Testing:** 3 new tests
**Commit:** `feat: add user profile page with name, company, NAICS codes`
**Follow-up:** Task 069 (org model)

---

### Task 069 — Add organization model (orgs, memberships)
**Epic:** E03 | **Milestone:** M2 | **Complexity:** XL | **Sessions:** 3
**Objective:** Add the multi-tenant organization model that all team and sharing features depend on.
**Business Value:** Foundation for team collaboration, data isolation, plan enforcement.
**Requirements:**
- Create `organizations` table: `id, name, slug, plan, trial_ends_at, created_at, stripe_customer_id`
- Create `org_memberships` table: `id, org_id, user_id, role (owner/admin/member/viewer), joined_at`
- On first login after migration, auto-create a personal org for each existing user
- All existing users become owner of their personal org
- Add `org_id` to session after login (`g.org` populated alongside `g.user`)
- Update `require_login` to also require org membership
**Acceptance Criteria:**
- All existing users retain access via auto-created personal orgs
- `g.org` available in all authenticated routes
- No existing tests broken
- New tests: create org, add member, check membership
**Dependencies:** Task 062
**DB Changes:** New tables: `organizations`, `org_memberships`
**API Changes:** None (internal model change)
**Frontend Changes:** None (org context used internally)
**Testing:** 10 new tests in `test_auth.py` or new `test_orgs.py`
**Commit:** `feat: add organization model with auto-created personal orgs`
**Follow-up:** Task 070 (team invites), Task 071 (RBAC)

---

### Task 070 — Add team invitation flow
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow org owners to invite users by email. Invitees receive an email link,
register (or log in) and are added to the org.
**Requirements:**
- Create `invitations` table: `id, org_id, email, token, role, invited_by, expires_at, accepted_at`
- `GET/POST /settings/invite` — owner/admin sends invitation
- Send invitation email with acceptance link
- `GET /accept-invite?token=<tok>` — unauthenticated; register if new, add to org if existing
- `GET /settings/team` — list members and pending invitations
- Remove member: `POST /settings/team/remove` (owner only)
**Acceptance Criteria:**
- Invitation email sent on form submit
- New user clicking link: registration page pre-fills email, on register → added to org
- Existing user clicking link: redirected to accept confirmation, then added to org
- Expired invites (7 days) show friendly error
**Dependencies:** Task 069, Task 174
**DB Changes:** New table: `invitations`
**API Changes:** `/settings/invite`, `/accept-invite`, `/settings/team`
**Frontend Changes:** `templates/settings/invite.html`, `templates/settings/team.html`
**Testing:** 8 new tests
**Commit:** `feat: add team invitation flow with email-based org membership`
**Follow-up:** Task 071 (RBAC)

---

### Task 071 — Add role-based permissions (RBAC) within org
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Enforce role-based access for org-scoped actions (admin functions require admin+).
**Requirements:**
- Define roles: `owner`, `admin`, `member`, `viewer`
- `viewer`: read-only (no saves, no notes, no capture tasks)
- `member`: full read + write in capture workspace
- `admin`: member + can invite, remove members, change settings
- `owner`: admin + can delete org, change plan
- Create `require_role(min_role)` decorator
- Apply to: invite (admin+), remove member (admin+), org settings (owner)
- Viewer restriction: disable edit controls in templates, 403 on write routes
**Acceptance Criteria:**
- Viewer cannot POST to any write route; gets 403
- Member can create capture tasks but not invite users
- Admin can invite but not delete org
- Owner can do everything
**Dependencies:** Task 069
**DB Changes:** None (role column already in org_memberships from Task 069)
**API Changes:** 403 responses on unauthorized actions
**Frontend Changes:** Conditionally hide edit controls based on `g.member.role`
**Testing:** 8 new tests asserting role enforcement
**Commit:** `feat: add RBAC with viewer/member/admin/owner roles`
**Follow-up:** Task 193 (audit log)

---

## EPIC E04 — Customer Onboarding

---

### Task 072 — Build onboarding wizard step 1: company identification
**Epic:** E04 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Show a setup wizard on first login. Step 1 collects company name, UEI,
CAGE code, or website URL.
**Requirements:**
- Detect first-time login (new org with no profile data) and redirect to `/onboarding/step1`
- `GET/POST /onboarding/step1` — form: company name, UEI (optional), CAGE (optional), website (optional)
- Save to `organizations` table (name, uei_hint, cage_hint, website_hint)
- On submit, redirect to step 2
- Skip link (for users who want to explore manually)
- Progress indicator: Step 1 of 3
**Acceptance Criteria:**
- New org user is redirected to onboarding on first login
- Form validates at least one field is provided
- Skip goes directly to dashboard
- Existing org users never see onboarding
**Dependencies:** Task 069
**DB Changes:** `organizations`: add `uei_hint TEXT`, `cage_hint TEXT`, `website_hint TEXT`, `onboarding_complete BOOLEAN DEFAULT FALSE`
**API Changes:** `/onboarding/step1`, `/onboarding/skip`
**Frontend Changes:** `templates/onboarding/step1.html`
**Testing:** 4 new tests
**Commit:** `feat: add onboarding wizard step 1 (company identification)`
**Follow-up:** Task 073

---

### Task 073 — Build onboarding wizard step 2: NAICS code selection
**Epic:** E04 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Let the user select the NAICS codes most relevant to their business.
**Requirements:**
- `/onboarding/step2` — display top-level NAICS sectors as checkboxes
- Allow drilling into 6-digit codes within a selected sector
- Pre-select based on UEI hint if available (from SAM entity enrichment)
- Save selected codes to `org_naics_codes` table
- Maximum 20 codes selected
**Acceptance Criteria:**
- User can select 1–20 NAICS codes
- Selection persists after form submit
- Pre-population works when UEI was provided in step 1
**Dependencies:** Task 072
**DB Changes:** New table: `org_naics_codes (org_id, naics_code, naics_title, selected_at)`
**API Changes:** `/onboarding/step2`
**Frontend Changes:** `templates/onboarding/step2.html` with NAICS selector
**Testing:** 3 new tests
**Commit:** `feat: add onboarding wizard step 2 (NAICS code selection)`
**Follow-up:** Task 074

---

### Task 074 — Build onboarding wizard step 3: alert thresholds
**Epic:** E04 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Collect initial alert preferences: expiration windows and minimum contract value.
**Requirements:**
- `/onboarding/step3` — form: expiration alert at 180/90/60/30 days (multi-select), min contract value
- Save to `org_alert_settings` table
- On complete, set `org.onboarding_complete = true`
- Redirect to dashboard with welcome message
**Acceptance Criteria:**
- Alert settings saved, onboarding flag set
- Dashboard loads on completion
- Welcome flash message on first dashboard visit
**Dependencies:** Task 073
**DB Changes:** New table: `org_alert_settings (org_id, alert_days_json, min_value, digest_frequency)`
**API Changes:** `/onboarding/step3`, `/onboarding/complete`
**Frontend Changes:** `templates/onboarding/step3.html`
**Testing:** 3 new tests
**Commit:** `feat: add onboarding wizard step 3 (alert thresholds) and completion`
**Follow-up:** Task 176 (email alerts use these settings)

---

### Task 075 — Add demo mode with sample data
**Epic:** E04 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow unauthenticated visitors to explore the platform with sample data.
**Requirements:**
- `/demo-mode` route — publicly accessible, sets a `demo_session=true` cookie
- Demo session bypasses auth but serves read-only data from a demo org (seeded sample data)
- Create `seed_demo_data()` function: 50 sample contracts, 3 sample vendors, 2 agencies
- Demo mode shows a "Sign Up" banner on every page
- Demo data refreshes nightly (Celery task)
- `/demo-exit` clears the demo cookie
**Acceptance Criteria:**
- Unauthenticated user can reach `/demo-mode` and browse contracts, vendors, agencies
- Demo data is clearly labelled as sample data
- Sign-up CTA visible on all demo pages
- Write routes (notes, watchlist, capture) are disabled in demo mode
**Dependencies:** Task 065 (Celery), Task 075 (seed data function)
**DB Changes:** Add `is_demo BOOLEAN DEFAULT FALSE` to `organizations`; add demo org to seed
**API Changes:** `/demo-mode`, `/demo-exit`
**Frontend Changes:** Demo banner in base.html, disabled state for write actions
**Testing:** 4 new tests
**Commit:** `feat: add demo mode with sample data for unauthenticated exploration`
**Follow-up:** Task 076 (company intelligence enriches demo profile)

---

## EPIC E05 — Company Intelligence (Partial — continues in 03_TASKS_101_150)

---

### Task 076 — SAM.gov entity search by UEI
**Epic:** E05 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Given a UEI number, fetch the entity record from SAM.gov entity API and return
structured data (legal name, CAGE, certifications, NAICS codes, registration status).
**Business Value:** Core intelligence about the customer's own business — the foundation of
company profiles and auto-discovery.
**Requirements:**
- Create `sam_entity_service.py` with `lookup_by_uei(uei)` function
- Call `https://api.sam.gov/entity-information/v3/entities?ueiSAM=<uei>&api_key=<key>`
- Parse response: extract legalBusinessName, cageCode, certifications, naicsCodeList,
  registrationStatus, expirationDate, physicalAddress
- Return structured dict; return None on not found
- Cache result in `sam_entity_cache` table (TTL 24h)
**Acceptance Criteria:**
- Valid UEI returns structured entity dict
- Invalid UEI returns None without raising exception
- Cached response served on second call within 24h
- SAM_API_KEY required; warn (not crash) if missing
**Dependencies:** Task 062
**DB Changes:** New table: `sam_entity_cache (uei TEXT PK, data_json TEXT, cached_at TEXT)`
**API Changes:** None (internal service)
**Testing:** 5 new tests with mocked HTTP responses
**Commit:** `feat: add SAM.gov entity lookup service by UEI`
**Follow-up:** Task 077 (CAGE lookup), Task 079 (company profile)

---

### Task 077 — SAM.gov entity search by CAGE code
**Epic:** E05 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Extend `sam_entity_service.py` with `lookup_by_cage(cage)`.
**Requirements:**
- Add `lookup_by_cage(cage)` to `sam_entity_service.py`
- Use `cageCode=<cage>` query param on same entity API
- Reuse cache table and same response parsing
**Acceptance Criteria:** Same as Task 076 for CAGE input
**Dependencies:** Task 076
**DB Changes:** None (reuses cache from Task 076)
**Testing:** 3 new tests
**Commit:** `feat: add SAM.gov entity lookup by CAGE code`
**Follow-up:** Task 078

---

### Task 078 — SAM.gov entity search by company name
**Epic:** E05 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Add `search_by_name(name)` to `sam_entity_service.py`. Returns top 5 matches.
**Requirements:**
- `search_by_name(name)` — use `entityName=<name>` param, return list of up to 5 matches
- Each match: `{uei, legal_name, cage, city, state, registration_status}`
- `/company/search?q=<name>` route returns JSON list (used by onboarding autocomplete)
**Acceptance Criteria:**
- Name search returns ranked list
- `/company/search?q=Acme` returns JSON array
- Partial name matches work
**Dependencies:** Task 076
**DB Changes:** None
**API Changes:** `GET /company/search?q=<name>` returns JSON
**Testing:** 4 new tests
**Commit:** `feat: add SAM entity name search with autocomplete route`
**Follow-up:** Task 079 (company profile page)

---

### Task 079 — Build company profile page
**Epic:** E05 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Create `/company/<uei>` page showing certifications, NAICS codes, registration
status, and contract history for any SAM-registered entity.
**Requirements:**
- `/company/<uei>` route: fetch entity from cache or API, render profile
- Display: legal name, CAGE, certifications (8a, SDVOSB, WOSB, HUBZone, etc.),
  NAICS codes, address, registration status, expiration date
- Show all contracts in the database where vendor matches this entity
- Link to `/vendor/<name>` for contract analytics
**Acceptance Criteria:**
- Page loads for any valid UEI
- Certifications displayed as tags/badges
- Contract count shown from local database
- Page shows "Not found in SAM.gov" gracefully for invalid UEI
**Dependencies:** Task 076
**DB Changes:** None (uses cache)
**API Changes:** `GET /company/<uei>`
**Frontend Changes:** `templates/company.html`
**Testing:** 3 route tests
**Commit:** `feat: add company profile page with SAM entity data`
**Follow-up:** Task 080 (link org to SAM entity), Task 081 (certifications analytics)

---

### Task 080 — Link user organization to SAM entity
**Epic:** E05 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow an org to associate with a SAM entity (UEI), enabling auto-discovery
of the org's own contracts and competitors.
**Requirements:**
- On onboarding step 1, if UEI provided, auto-fetch entity and associate
- `organizations.uei` column stores confirmed UEI
- `GET /settings/company` — org settings page to update SAM association
- On association, trigger background enrichment: fetch org's own contracts from DB,
  link to company profile, compute incumbency stats
**Acceptance Criteria:**
- Org with UEI shows "Your Company" profile on dashboard
- Own contracts highlighted in contract list
- SAM entity data displayed in org settings
**Dependencies:** Tasks 069, 076, 079
**DB Changes:** `organizations`: add `uei TEXT`, `cage TEXT`, `sam_entity_json TEXT`, `sam_last_refreshed TEXT`
**API Changes:** `GET/POST /settings/company`
**Frontend Changes:** `templates/settings/company.html`, dashboard org summary card
**Testing:** 4 new tests
**Commit:** `feat: link organization to SAM entity for company self-identification`
**Follow-up:** Task 081 (certification tracking), Task 086 (business DNA)

---

### Task 081 — Certification tracking and expiration alerts
**Epic:** E05 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1
**Objective:** Track SAM registration and certification expirations; alert org when renewals are due.
**Requirements:**
- Parse SAM entity `expirationDate` and certification-specific expiration dates
- Store in `org_certifications` table
- Alert org 90/30 days before registration expires
- Dashboard widget: "Your SAM registration expires in X days"
**Acceptance Criteria:**
- Certification data parsed from SAM entity response
- Dashboard widget visible when within 90 days of expiration
- Alert email sent at 90 and 30 day thresholds
**Dependencies:** Task 080, Task 176 (email alerts)
**DB Changes:** New table: `org_certifications (org_id, cert_type, cert_number, expires_at, source)`
**API Changes:** None
**Frontend Changes:** Dashboard widget
**Testing:** 3 new tests
**Commit:** `feat: add SAM certification tracking with expiration alerts`
**Follow-up:** Task 082 (NAICS code discovery from SAM entity)

---

### Task 082 — Auto-populate org NAICS codes from SAM entity
**Epic:** E05 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** When org is linked to a SAM entity, automatically populate the org's NAICS
codes from the entity's primary and secondary NAICS list.
**Requirements:**
- After org-SAM entity association (Task 080), call `sync_naics_from_entity(org_id, uei)`
- Upsert NAICS codes into `org_naics_codes` with `source='sam_entity'`
- Onboarding step 2 pre-populates from these codes
- User can add/remove codes after auto-population
**Acceptance Criteria:**
- SAM entity NAICS codes appear pre-selected in onboarding step 2
- Codes labelled with "From SAM registration" source tag
- User edits persist independently of SAM data
**Dependencies:** Tasks 073, 080
**DB Changes:** `org_naics_codes`: add `source TEXT`
**Testing:** 3 new tests
**Commit:** `feat: auto-populate org NAICS codes from SAM entity registration`
**Follow-up:** Task 083 (NAICS-based opportunity filtering)

---

### Task 083 — Filter opportunity recommendations by org NAICS codes
**Epic:** E05 | **Milestone:** M1 | **Complexity:** S | **Sessions:** 1
**Objective:** Scope the dashboard opportunity recommendations to contracts in the org's NAICS codes.
**Requirements:**
- `opportunity_recommendations()` in `analytics.py` accepts `org_naics_codes` list
- When list is non-empty, add `AND naics_code IN (?)` filter
- Contracts table needs `naics_code TEXT` column (populated during ingest)
- Dashboard passes org NAICS codes from `g.org`
**Acceptance Criteria:**
- Recommendations only show contracts in org's NAICS codes when codes are set
- Falls back to all contracts when org has no NAICS codes
**Dependencies:** Tasks 062, 082
**DB Changes:** `contracts`: add `naics_code TEXT`, `psc_code TEXT` columns
**API Changes:** None
**Frontend Changes:** Dashboard shows "Filtered to your NAICS codes" when applied
**Testing:** 3 new tests
**Commit:** `feat: filter opportunity recommendations by org NAICS codes`
**Follow-up:** Task 123 (full scoring engine uses NAICS)
