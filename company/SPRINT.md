# SPRINT.md — Execution Plan

**Owner:** Technical Program Manager  
**Last revised:** 2026-06-20  
**Active milestone:** M3 — Production Launch  
**Objective:** First paying customer can register, search, bookmark, receive alerts, and manage their subscription without any manual intervention from the team.

---

## Active Sprint — M3 Foundation

This sprint addresses every P0 blocker and establishes the technical baseline for all M3 feature work. Nothing else starts until this sprint is done.

**Done when:** PostgreSQL auth and analytics are fully operational, compromised credentials are rotated, CSRF is in place, and the test suite passes on a clean PostgreSQL connection.

---

### P0 Checklist — Must Complete Before Anything Else

| Status | Item | Risk if skipped |
|---|---|---|
| OPEN | Rotate Stripe live secret key | Active financial exposure |
| OPEN | Rotate HubSpot access token | CRM data breach risk |
| OPEN | Generate new SECRET_KEY for Flask | Session forgery possible |
| OPEN | Fix `users.py` PostgreSQL compatibility | Login/register broken on prod DB |
| OPEN | Fix `analytics.py` PostgreSQL compatibility | Dashboard/vendor/agency pages broken on prod DB |
| OPEN | CSRF protection on all POST routes | Forms vulnerable to cross-site forgery |
| OPEN | Enforce Stripe webhook signature | Accepts unsigned events without STRIPE_WEBHOOK_SECRET |
| OPEN | Rate limit `/login` | Brute force auth attacks unblocked |

---

## Sprint Sequence — M3

Sprints are ordered by dependency. Do not start a sprint until its predecessor is complete.

---

### Sprint A — Platform Stability (P0)

**Goal:** Zero production blockers. System is safe and PostgreSQL-compatible.

**Deployment:** Deploy immediately after each item. These are emergency fixes.

| # | Task | Size | Owner |
|---|---|---|---|
| A-1 | Rotate Stripe secret key in Stripe dashboard; update Railway env var | XS | DevOps |
| A-2 | Rotate HubSpot access token; update Railway env var | XS | DevOps |
| A-3 | Generate and set new SECRET_KEY; document rotation in runbook | XS | DevOps |
| A-4 | Rewrite `users.py` to use SQLAlchemy (replace sqlite3 imports, `?` → `:param`, `sqlite3.Row` → dict) | S | Backend |
| A-5 | Rewrite `analytics.py` `dashboard_analytics()` to use named SQLAlchemy params | S | Backend |
| A-6 | Rewrite `analytics.py` `vendor_profile_analytics()` to use named SQLAlchemy params | S | Backend |
| A-7 | Rewrite `analytics.py` `agency_profile()` to use named SQLAlchemy params | S | Backend |
| A-8 | Rewrite `analytics.py` `opportunity_recommendations()` to use named SQLAlchemy params | S | Backend |
| A-9 | Add CSRF token to `/login`, `/register`, `/ingest`, `/demo`, `/early-access` POST forms | S | Backend |
| A-10 | Enforce `STRIPE_WEBHOOK_SECRET` — reject unsigned webhook events with 400 | XS | Backend |
| A-11 | Add rate limiting to `/login`: 5 attempts per minute per IP | S | Backend |
| A-12 | Pin all unpinned packages in `requirements.txt` (celery, redis, sqlalchemy) | XS | DevOps |

**Test checkpoint:** Full test suite must pass. Add PostgreSQL integration tests for auth and analytics.

**Deployment checkpoint:** Deploy A-1 through A-3 immediately (credential rotation). Deploy A-4 through A-12 as a single release after the test suite passes.

---

### Sprint B — Retention Core (P2)

**Goal:** Users have a reason to return to the product every day.

**Dependency:** Sprint A must be complete.

| # | Task | Size | Owner |
|---|---|---|---|
| B-1 | Add `user_watchlist` table (user_id, contract_id, added_at) | XS | Backend |
| B-2 | Add `POST /watchlist/add` and `DELETE /watchlist/remove` routes | S | Backend |
| B-3 | Add bookmark toggle button to contract list rows | S | Frontend |
| B-4 | Add bookmark toggle button to contract detail page | XS | Frontend |
| B-5 | Add `GET /watchlist` page listing bookmarked contracts | S | Frontend |
| B-6 | Add watchlist count badge to nav | XS | Frontend |
| B-7 | Add `user_saved_searches` table (user_id, name, query_params_json, created_at) | XS | Backend |
| B-8 | Add `POST /searches/save` and `DELETE /searches/:id` routes | S | Backend |
| B-9 | Add "Save this search" button to contracts filter bar | S | Frontend |
| B-10 | Add `GET /searches` page listing saved searches with run links | S | Frontend |
| B-11 | Add contract notes table (user_id, contract_id, body, created_at) | XS | Backend |
| B-12 | Add `POST /contract/:id/note` and display notes on contract detail page | S | Backend/Frontend |
| B-13 | Add CSV export from `/contracts` (streams current filtered result set) | S | Backend |

**Test checkpoint:** Watchlist, saved search, and CSV export endpoints all have unit and integration tests. Full suite passes.

**Deployment checkpoint:** Deploy B-1 through B-6 (watchlist) together. Deploy B-7 through B-10 (saved searches) together. Deploy B-11 through B-13 (notes + export) together. Three deploys total.

---

### Sprint C — Data Trust (P2)

**Goal:** Users can verify data freshness and trust what they see.

**Dependency:** Sprint A must be complete. Sprint B can run in parallel.

| # | Task | Size | Owner |
|---|---|---|---|
| C-1 | Add `ingest_log` table (run_date, source, record_count, duration_seconds, status) | XS | Backend |
| C-2 | Write ingest metadata to `ingest_log` at end of `run_ingest` Celery task | S | Backend |
| C-3 | Add `GET /api/data-freshness` route returning last successful ingest timestamp and count | S | Backend |
| C-4 | Add data freshness indicator to dashboard (e.g., "Data updated 6 hours ago") | S | Frontend |
| C-5 | Add data quality alert: log ERROR if ingest returns < 10 records (detect silent failures) | XS | Backend |
| C-6 | Confirm nightly ingest calls SAM.gov API (not a cached CSV); document data source | XS | Backend |
| C-7 | Update `ARCHITECTURE.md` to reflect actual current state (PostgreSQL, Celery, Redis, Stripe, HubSpot, test count) | S | Docs |

**Test checkpoint:** Freshness route has unit tests. Ingest metadata is verified in test.

**Deployment checkpoint:** Single deploy after all C tasks pass.

---

### Sprint D — Email Infrastructure (P1)

**Goal:** The platform can send transactional email. This unlocks Sprint E (alerts) and Sprint F (trial emails).

**Dependency:** Sprint A must be complete.

| # | Task | Size | Owner |
|---|---|---|---|
| D-1 | Select and provision transactional email provider (Resend, SendGrid, or Postmark) | XS | DevOps |
| D-2 | Add `email_service.py` with `send_email(to, subject, html_body, text_body)` | S | Backend |
| D-3 | Add `SMTP_FROM`, `EMAIL_API_KEY` env vars to Railway config | XS | DevOps |
| D-4 | Write `/ingest/email-test` admin route to verify email delivery | XS | Backend |
| D-5 | Add email send queue: `email_queue` Celery task wrapping `send_email()` | S | Backend |
| D-6 | Write `templates/email/base.html` — branded email layout (logo, footer, unsubscribe) | S | Frontend |
| D-7 | Write welcome email template sent on registration | S | Frontend |
| D-8 | Wire welcome email into `register` route: enqueue via Celery after user creation | XS | Backend |
| D-9 | Add `reset_token` and `reset_token_expires_at` columns to `users` table | XS | Backend |
| D-10 | Add `GET/POST /forgot-password` route: accept email, generate token, send reset link | S | Backend |
| D-11 | Write password reset email template | S | Frontend |
| D-12 | Add `GET/POST /reset-password?token=<tok>` route: validate token (1h TTL), update hash, invalidate token | S | Backend |

**Test checkpoint:** `send_email()` is mockable; all callers tested with mock. D-8 verified with integration test. Password reset flow tested end-to-end: request → token → update → login with new password. Expired token returns 400.

**Deployment checkpoint:** Single deploy after D-1 through D-8 pass. Manual test: register a new account, verify welcome email arrives.

---

### Sprint E — Expiration Alerts (P1)

**Goal:** Users receive timely email notifications about contracts they care about.

**Dependency:** Sprint B (watchlist) and Sprint D (email) must be complete.

| # | Task | Size | Owner |
|---|---|---|---|
| E-1 | Add `alert_preferences` table (user_id, alert_days JSON array, min_value, enabled) | XS | Backend |
| E-2 | Add `GET/POST /settings/alerts` page to configure alert preferences | S | Backend/Frontend |
| E-3 | Write `check_watchlist_alerts()` Celery task: find contracts expiring at user's thresholds | S | Backend |
| E-4 | Write expiration alert email template | S | Frontend |
| E-5 | Enqueue alert emails from `check_watchlist_alerts()` | S | Backend |
| E-6 | Schedule `check_watchlist_alerts` via beat: daily at 07:00 UTC | XS | Backend |
| E-7 | Add `alert_log` table to prevent duplicate sends (user_id, contract_id, days_threshold, sent_at) | XS | Backend |
| E-8 | Add unsubscribe route: `GET /unsubscribe?token=<tok>` that disables alerts | S | Backend |
| E-9 | Write status change alert email (when a watched contract changes priority) | S | Backend/Frontend |
| E-10 | Trigger status change alert in `change_detector.py` when a watched contract changes | S | Backend |

**Test checkpoint:** Alert task tested with mock email and mock DB. Deduplication via `alert_log` verified. Schedule registration tested.

**Deployment checkpoint:** Deploy E-1 through E-7 (watchlist alerts) together. Deploy E-8 through E-10 (status change + unsubscribe) as a follow-up. Manual test: watch a contract, wait for scheduled run or trigger manually, verify email arrives.

---

### Sprint F — Monetization (P1)

**Goal:** Customers can subscribe, upgrade, downgrade, and cancel without our help.

**Dependency:** Sprint D (email) must be complete. Sprint A must be complete.

| # | Task | Size | Owner |
|---|---|---|---|
| F-1 | Enable Stripe Customer Portal in Stripe dashboard; configure allowed plan changes | XS | DevOps |
| F-2 | Add `POST /billing/portal` route: creates Stripe Customer Portal session, redirects | S | Backend |
| F-3 | Add "Manage Subscription" link to user account nav | XS | Frontend |
| F-4 | Add `stripe_customer_id` and `subscription_status` columns to `users` (or `organizations`) table | XS | Backend |
| F-5 | Handle `customer.subscription.updated` Stripe webhook event: update `subscription_status` | S | Backend |
| F-6 | Handle `customer.subscription.deleted` Stripe webhook event: downgrade to free tier | S | Backend |
| F-7 | Add `plan` field enforcement: define feature flags per tier (Starter/Professional/Team) | S | Backend |
| F-8 | Add trial start on registration: set `trial_ends_at = now + 14 days` in users table | XS | Backend |
| F-9 | Add trial expiry gate: redirect to `/subscribe` when trial expired and no subscription | S | Backend |
| F-10 | Write trial day-3 email: "You have 11 days left — here's what you can do" | S | Frontend |
| F-11 | Write trial day-10 email: "4 days left — start your subscription to keep access" | S | Frontend |
| F-12 | Write trial expiry email: "Your trial ended — subscribe to continue" | S | Frontend |
| F-13 | Schedule trial email Celery tasks: check daily at 08:00 UTC | S | Backend |
| F-14 | Build `/subscribe` page with tier comparison and checkout CTA | S | Frontend |
| F-15 | Polish `/success` and `/cancel` pages with real layout and next-step guidance | S | Frontend |

**Test checkpoint:** All Stripe webhook handlers tested with mock Stripe events. Trial gate tested with clock-mocked date. Email templates have snapshot tests.

**Deployment checkpoint:** Deploy F-1 through F-3 (billing portal) alone — this is safe and immediately useful. Deploy F-4 through F-7 (subscription status sync) together. Deploy F-8 through F-15 (trial flow) together. Three deploys total.

---

### Sprint G — Operational Excellence (P3)

**Goal:** Failures surface immediately. The product is observable.

**Dependency:** Sprint A must be complete. Can run in parallel with F.

| # | Task | Size | Owner |
|---|---|---|---|
| G-1 | Add Sentry to `requirements.txt`; initialize with Railway environment tag | XS | DevOps |
| G-2 | Wire Sentry `capture_exception()` in all `except` blocks in `app.py` and `tasks.py` | S | Backend |
| G-3 | Add structured logging format (JSON lines) to all modules | S | Backend |
| G-4 | Add `GET /api/health/detailed` (auth required): DB ping, Redis ping, last ingest time | S | Backend |
| G-5 | Add beat health alert: email admin if `beat:health` Redis key is stale > 20 min | S | Backend |
| G-6 | Document credential rotation runbook in `docs/OPERATIONS.md` | S | Docs |
| G-7 | Enable Railway PostgreSQL point-in-time recovery; verify restore from backup completes successfully | XS | DevOps |

**Test checkpoint:** Sentry integration tested with a triggered error in staging. Health endpoint has unit tests.

**Deployment checkpoint:** Single deploy after all G tasks pass.

---

## M3 Exit Criteria Checklist

Before declaring M3 complete:

| # | Criterion | Sprint |
|---|---|---|
| 1 | Live credentials rotated, no keys in git history | A |
| 2 | User login and registration work against PostgreSQL | A |
| 3 | Dashboard, vendor, agency pages work against PostgreSQL | A |
| 4 | CSRF protection on all POST forms | A |
| 5 | Watchlist: users can bookmark and unbookmark contracts | B |
| 6 | Saved searches: users can save and re-run named filters | B |
| 7 | CSV export from any filtered contract view | B |
| 8 | Data freshness indicator on dashboard | C |
| 9 | Welcome email sent on registration; password reset flow working | D |
| 10 | Expiration alerts sent at user-defined thresholds | E |
| 11 | Status change alerts sent for watched contracts | E |
| 12 | Billing portal live (upgrade/downgrade/cancel) | F |
| 13 | 14-day trial with hard gate at expiry | F |
| 14 | Trial email sequence (day 3, day 10, day 14) | F |
| 15 | Sentry error tracking live | G |
| 16 | Railway PostgreSQL backups enabled and restore verified | G |
| 17 | Test count ≥ 250, full suite passes | All |
| 17 | ≥ 1 paying organization | Business |

---

## Dependency Graph

```
EXTERNAL (non-code):
  Credential Rotation (A-1, A-2, A-3)    ← do first, no dependencies
  Email Provider (D-1)                    ← do before Sprint D begins

SPRINT A (P0 — blocks everything):
  A-4: Fix users.py ──────────────────────────────────────────────┐
  A-5 to A-8: Fix analytics.py ───────────────────────────────────┤
  A-9: CSRF ──────────────────────────────────────────────────────┤
  A-10: Webhook signature ──────────────────────────────────────── → Sprint B, C, D, F can start
  A-11: Rate limiting ─────────────────────────────────────────────┘

SPRINT B (watchlist + search):        No internal deps | Needs Sprint A
  B-1: watchlist table
    └─ B-2: routes
         └─ B-3: list toggle
              └─ B-4: detail toggle
                   └─ B-5: /watchlist page
                        └─ B-6: nav badge
  B-7: saved_search table
    └─ B-8: routes
         └─ B-9: UI button
              └─ B-10: /searches page
  B-11: notes table ─→ B-12: routes+UI
  B-13: CSV export     (no deps — standalone)

SPRINT C (data trust):                No internal deps | Needs Sprint A
  C-1: ingest_log table ─→ C-2: write metadata ─→ C-3: API route ─→ C-4: dashboard widget
  C-5, C-6: independent
  C-7: docs (no deps)

SPRINT D (email infrastructure):      Needs Sprint A | Blocks E and F emails
  D-1: provider (external) ─→ D-2: email_service ─→ D-3: env vars
                                └─ D-4: test route
                                └─ D-5: email Celery task
                                     └─ D-6: email base template
                                          └─ D-7: welcome template
                                               └─ D-8: wire to register

SPRINT E (alerts):                    Needs Sprint B (watchlist) + Sprint D (email)
  E-1: alert_prefs table ─→ E-2: settings page
  E-3: alert task ─→ E-4: template ─→ E-5: enqueue ─→ E-6: schedule
  E-7: alert_log (dedup)              ← pair with E-3
  E-8: unsubscribe route              ← pair with E-5
  E-9: status change template ─→ E-10: trigger in change_detector

SPRINT F (monetization):              Needs Sprint A + Sprint D
  F-1: Stripe portal config (external)
    └─ F-2: /billing/portal route ─→ F-3: nav link
  F-4: subscription fields ─→ F-5: webhook updated ─→ F-6: webhook deleted
                           └─ F-7: plan enforcement
  F-8: trial_ends_at ─→ F-9: trial gate
                    └─ F-10 to F-12: email templates ─→ F-13: schedule
  F-14: /subscribe page (needs F-7 for feature comparison)
  F-15: polish success/cancel pages (no deps)

SPRINT G (operations):                Needs Sprint A | Can run in parallel with F
  G-1: Sentry setup ─→ G-2: wire capture_exception
  G-3: structured logging (independent)
  G-4: /api/health/detailed (independent)
  G-5: beat health alert (needs Sprint D for email)
  G-6: runbook docs (independent)

CRITICAL PATH:
  A → D → E (longest chain: 3 sprints sequential)
  A → B (parallel with D)
  A → F (starts after D, runs in parallel with E)
  A → G (parallel with everything)
```

---

## Milestone Execution Order

| Phase | Sprints | Parallelism | Gate |
|---|---|---|---|
| **Phase 1: Stabilize** | A only | None (all serial) | All P0s resolved, suite passes on PostgreSQL |
| **Phase 2: Build** | B + C + D | B, C, D run in parallel | Watchlist works, email sends, data freshness visible |
| **Phase 3: Connect** | E + F + G | E, F, G run in parallel | Alerts fire, billing portal live, errors tracked |
| **Phase 4: Ship M3** | — | — | All exit criteria met, first customer paying |

---

## Deployment Strategy

### Principles

- **One concern per deploy.** Never mix a security fix with a feature in the same release.
- **Deploy P0 fixes immediately.** Do not batch security fixes with feature work.
- **Deploy by sprint segment.** Deploy each labelled group within a sprint as a unit.
- **Green test suite before every deploy.** No exceptions.
- **Verify `/health` after every deploy.** If health fails, roll back immediately.

### Deployment Checkpoints

| Checkpoint | When | What to verify |
|---|---|---|
| **D0** | After A-1 to A-3 (credential rotation) | Stripe and HubSpot API calls succeed with new keys |
| **D1** | After A-4 to A-12 | Full test suite passes; login, dashboard, vendor pages work on PostgreSQL |
| **D2** | After B-1 to B-6 (watchlist) | Bookmark and unbookmark a contract in production |
| **D3** | After B-7 to B-10 (saved searches) | Save and re-run a search in production |
| **D4** | After B-11 to B-13 (notes + export) | Add a note; download CSV |
| **D5** | After C-1 to C-7 | Freshness indicator shows on dashboard |
| **D6** | After D-1 to D-8 (email infra) | Register new account; verify welcome email arrives |
| **D7** | After F-1 to F-3 (billing portal) | Click "Manage Subscription" from nav; portal opens |
| **D8** | After E-1 to E-10 (alerts) | Trigger alert task manually; verify alert email arrives |
| **D9** | After F-4 to F-15 (trial + plans) | Register new account; verify trial starts; verify expiry gate at day 14 |
| **D10** | After G-1 to G-6 (observability) | Trigger a test error; verify it appears in Sentry |

### Rollback Protocol

Every deploy must be one `git revert` away from the previous working state.
If a deploy causes test failures or health check failures:

1. Revert the commit immediately
2. Push the revert
3. Railway redeploys the working state
4. Diagnose in a branch; do not hotfix on main

---

## Testing Strategy

### Unit Tests (every task)

Every function added or modified gets a unit test in the same commit.
- Target: one positive test + one negative/edge test per function
- Tests must not touch `contracts.db` or a live Redis connection
- Use `pytest` fixtures with `tmp_path` for DB isolation
- Mock `send_email()`, `stripe.*`, `hubspot.*`, and `redis.from_url()` in all tests

### Integration Tests (every route)

Every new Flask route gets at least one integration test using the Flask test client.
- Register a test user, establish session, then test the route
- Test both the success path and the auth-required rejection
- Test error inputs (missing params, invalid data) return appropriate status codes

### PostgreSQL Compatibility Tests (Sprint A)

Sprint A must add parametrized tests that run against both SQLite and PostgreSQL.
- `conftest.py` parametrize fixture: `@pytest.fixture(params=["sqlite", "postgres"])`
- Skip PostgreSQL fixture if `TEST_DATABASE_URL` is not set (so CI doesn't require PG)
- All `users.py` and `analytics.py` functions must pass both backends

### Regression Testing (before every deploy)

Before any deployment checkpoint (D0–D10):

```
pytest -q --tb=short
```

Full suite must pass. Zero failures, zero errors.

If the suite has flaky tests, fix the flakiness before deploying — never skip.

### Deployment Verification (after every deploy)

After each Railway deploy:

1. `curl https://<app>.railway.app/health` → must return `{"status": "ok"}` with 200
2. Log in with a known test account → dashboard must load
3. Run the smoke test checklist for that checkpoint (see Deployment Checkpoints above)
4. Check Sentry for any new errors in the 5 minutes after deploy (once G-1 is live)

---

## Risk Analysis

### High Risk

| Item | Risk | Mitigation |
|---|---|---|
| `users.py` PostgreSQL rewrite (A-4) | Breaks login for all users if wrong | Write PG compatibility tests first; test with a staging DB before deploying |
| `analytics.py` rewrite (A-5 to A-8) | Breaks dashboard for all users | Break into one function per task; deploy each function with its test |
| Email delivery (D-2) | Misconfigured sender domain triggers spam filters | Use a verified custom domain; test with multiple email providers before going live |
| Stripe webhook handlers (F-5, F-6) | Wrong subscription status stored | Test with Stripe CLI webhook replay tool; verify state machine in tests |
| Trial gate (F-9) | Could accidentally lock paying customers out | Check subscription_status first; only gate if no active subscription AND trial expired |

### Medium Risk

| Item | Risk | Mitigation |
|---|---|---|
| Celery beat schedule for alerts (E-6) | Beat restarts lose schedule until next deploy | Use persistent scheduler; verify beat:health key in monitoring |
| Alert deduplication (E-7) | Double-sends damage user trust | `alert_log` table with unique constraint; query before sending |
| CSRF implementation (A-9) | If token missing from a form, that form silently fails for users | Audit all POST forms after deploy; add integration test for each |

### Low Risk

| Item | Risk | Mitigation |
|---|---|---|
| Watchlist (B-1 to B-6) | Simple CRUD; very low risk | Standard pattern; straightforward tests |
| Saved searches (B-7 to B-10) | Stores query params as JSON; trivially reversible | Write migration to drop table if needed |
| Data freshness (C-1 to C-4) | Read-only display; zero risk to data | No migration concerns |
| Billing portal link (F-1 to F-3) | Just a redirect; trivially safe | No state changes on our side |

### Optional Work (not on critical path for M3)

These are valuable but not required for M3 exit criteria:

- Contract comparison upgrades (already working; polish later)
- NAICS code filtering on recommendations (E09 epic, belongs in M4)
- SAM entity lookup (company profiles) — M4 work
- Pipeline view (tag contracts as pursuing) — M4 work
- PDF export — M4 work

---

## Queue Strategy

### Task Sizing

**Target: 5–10 minutes of focused engineering work per task.**

Rules for sizing:
- One new database column or table = one task
- One new Flask route = one task (with its test)
- One new Celery task = one task
- One new email template = one task
- Any task requiring changes to 3+ files = split it

If a task description requires the word "and" more than twice, split it.

### Dependency Ordering

The AI agent should work tasks in this order within each sprint:
1. Database migrations first (tables before routes that need them)
2. Backend logic second (service functions before routes)
3. Routes third (after business logic is tested)
4. Frontend fourth (templates after routes)
5. Tests fifth only if not written inline with each step (preferred: write tests with the function)

### Commit Cadence

- One commit per task
- Commit message format: `type(scope): description` (feat, fix, test, chore, docs)
- Never commit failing tests
- Never commit without running the full test suite

### Review Cadence

- Every commit goes through the AI reviewer (regex + LLM)
- Any commit touching `auth.py`, `users.py`, `db.py`, `tasks.py`, or `stripe` routes triggers human escalation review
- Security-sensitive patches (CSRF, rate limiting, webhook verification) require human approval before deploy

### Deployment Cadence

- Deploy to Railway after each labelled checkpoint (D0–D10)
- Do not accumulate more than 5 commits between deploys
- Never deploy on Friday (no one to monitor over the weekend)
- Each deploy is preceded by: full test run → deploy → health check → smoke test

---

## Archived Sprints

### Sprint 0 — MVP (Complete)

Delivered a working Flask app on Railway with contract search, scoring, vendor
and agency intelligence pages, CSV ingest, and a basic AI agent scaffold.

---

### Sprint 1 — AI Engineering Platform (Complete)

Delivered the multi-agent system with repository memory, patch pipeline, safety
reviewer, and automatic rollback. 84 tests passing.

---

### Sprint 2 — Phase 2: Early Customers (Partial — archiving)

**Completed items:**
- Contract comparison page
- Session-based authentication (register/login/logout)
- Password hashing (scrypt)
- Route protection
- PostgreSQL provisioned and schema migrated (Tasks 061–062)
- Redis + Celery worker + beat (Tasks 063–064)
- Nightly SAM.gov ingest via Celery (Task 065)
- Stripe checkout integration
- HubSpot CRM integration
- Demo request and early access forms
- Min-value filter on contracts
- Ingest logging
- Pagination controls
- Human-readable saved view labels

**Open items — carried into M3 Sprint A (P0):**
- Per-user saved searches → Sprint B
- Watchlist → Sprint B
- Email alerts → Sprint E
- Export to CSV → Sprint B

**Why this sprint is closing:** The M3 roadmap supersedes the Phase 2 structure with a
clearer dependency model and priority ordering. All open items are captured in M3 sprints above.
