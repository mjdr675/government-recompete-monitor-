# MASTER ROADMAP — 01: Architecture Overview
# Government Recompete Monitor → AI-Powered GovCon Capture Platform

---

## 1. Executive Architecture Overview

### Current State (June 2026)
A single-user Flask web application deployed on Railway with SQLite. It ingests federal
contract data from SAM.gov, scores recompete probability, and surfaces opportunities via
a dashboard, vendor/agency profiles, and a searchable contract list. Authentication is
email/password session-based. Stripe and HubSpot are wired for sales pipeline capture.
An AI agent system (ai_agent/) autonomously builds and maintains the software.

### Target State (End of Roadmap)
A multi-tenant SaaS platform serving small and mid-sized federal contractors as their
primary AI-powered capture operating system. A customer provides minimal input (company
name, UEI, or website) and the platform discovers the business, identifies certifications,
discovers current and historical contracts, surfaces recompete opportunities, generates
capture plans, manages BD workflow, and continuously improves recommendations — requiring
as little manual configuration as possible.

---

## 2. Product Evolution Arc

```
Phase 1 (DONE):     Data + Search
                    Ingest SAM.gov → score → display

Phase 2 (Active):   Intelligence + Collaboration
                    Multi-tenant → email alerts → capture pipeline

Phase 3 (Next):     AI Assistance
                    Company discovery → capture plans → proposal outlines

Phase 4 (Future):   Autonomous Operations
                    Self-directed monitoring → continuous improvement → NLU interface
```

---

## 3. Target System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Browser / API Clients                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS
┌──────────────────────────────▼──────────────────────────────────┐
│                     Railway (Cloud Host)                        │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │           Flask Application (app.py)                   │     │
│  │   auth blueprint · require_login · before_request      │     │
│  │   Jinja2 templates (existing) + HTMX progressive UX    │     │
│  └──────┬──────────────────────────────┬──────────────────┘     │
│         │                              │                        │
│  ┌──────▼────────┐          ┌──────────▼──────────────────┐     │
│  │  PostgreSQL   │          │   Analytics / AI Services   │     │
│  │  (multi-      │          │   analytics.py              │     │
│  │   tenant,     │          │   scoring_engine.py (new)   │     │
│  │   pgvector)   │          │   recommendation_engine.py  │     │
│  └──────┬────────┘          │   capture_manager.py (new)  │     │
│         │                   └──────────────────────────────┘     │
│  ┌──────▼────────┐                                              │
│  │  Redis        │          ┌──────────────────────────────┐     │
│  │  (cache +     │          │   Celery Workers             │     │
│  │   queue)      ├──────────►  daily_scan_worker           │     │
│  └───────────────┘          │   alert_delivery_worker      │     │
│                             │   ai_enrichment_worker       │     │
│                             │   company_discovery_worker   │     │
│                             └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘

External Services:
  SAM.gov API      → contract data, entity search
  USAspending API  → historical awards, spending trends
  FPDS             → contract modifications, option exercises
  Anthropic API    → AI analysis, capture plans, enrichment
  Stripe           → billing, subscriptions, portal
  HubSpot          → sales CRM, contact management
  SendGrid/Postmark→ transactional email
  Sentry           → error tracking
```

---

## 4. System Architecture Recommendations

### 4.1 Database: SQLite → PostgreSQL
**Why:** SQLite is single-writer. Multi-tenant concurrent access will cause lock
contention and data loss risk on Railway's ephemeral filesystem. PostgreSQL is
required before any organization/multi-user features ship.

**How:** Use SQLAlchemy Core (not ORM) to preserve the existing raw SQL patterns
while enabling PostgreSQL-compatible query syntax. Migrate schema incrementally.
Add pgvector extension for future AI embedding search.

**Multi-tenancy:** Row-level tenancy via `org_id` column on all user-facing tables.
No separate schemas per tenant — simpler to operate and migrate. All queries must
filter by `org_id` derived from `g.org`.

### 4.2 Background Jobs: Celery + Redis
**Why:** Nightly SAM.gov data refresh, email delivery, AI enrichment, and company
discovery all require async execution outside the request lifecycle.

**Pattern:** Single Celery app instance. Tasks enqueued from Flask routes, picked
up by Railway worker service. Redis as both broker and result backend.

**Worker services:** Add `worker: celery -A tasks worker` to Procfile alongside
the existing `web: gunicorn app:app`.

### 4.3 Frontend: Jinja2 + HTMX (not a full SPA rewrite)
**Why:** A React rewrite would require a full API layer and months of rewrite time.
The existing Jinja2 templates work and are tested. HTMX provides dynamic interactions
(capture task updates, live search, inline editing) with minimal JavaScript and no
build pipeline.

**Pattern:** Progressive enhancement. Static pages work without JS. HTMX adds
reactivity where needed. Alpine.js for simple client state (modal open/close).

### 4.4 AI Integration: Anthropic Claude API
**Tier 1 (synchronous):** Contract analysis, capture plan generation, opportunity
explanation — triggered by user action, streamed to the browser.

**Tier 2 (async):** Company discovery enrichment, daily opportunity briefing,
competitor research — run by Celery workers, results stored in PostgreSQL.

**Tier 3 (autonomous):** AI agent system (ai_agent/) continues building the
software autonomously. This is the engineering layer, not the product layer.

### 4.5 Search: PostgreSQL FTS → Later Elasticsearch
**Phase 2:** Migrate from SQLite FTS5 to PostgreSQL tsvector/tsquery. Covers all
existing search functionality. Simpler than adding Elasticsearch.

**Phase 4+:** If search volume demands it, add Elasticsearch or OpenSearch as a
separate service. Do not optimize prematurely — PostgreSQL FTS handles millions of
documents comfortably.

### 4.6 API: Internal First, External in Phase 4
**Phase 2-3:** All endpoints serve the Flask frontend. No public REST API needed.

**Phase 4:** Add `/api/v1/` prefix routes with API key authentication. Generate
OpenAPI spec. Release Python SDK. Rate-limit per plan tier.

---

## 5. Engineering Principles

### 5.1 Extend, Never Rewrite
The existing Flask app, db.py patterns, analytics.py structure, auth system, and
test suite are proven and tested. Every new feature extends them. No route handler
rewrites. No schema drops. No template framework changes.

### 5.2 Smallest Possible Migrations
Every database schema change is an additive migration: ADD COLUMN, CREATE TABLE,
CREATE INDEX. Never DROP or ALTER in a destructive way. Write idempotent migration
scripts (`IF NOT EXISTS`, `IF NOT EXISTS`).

### 5.3 One Task = One Working State
Every task in this backlog must leave the application in a fully working state
with all tests passing. No partial features. No commented-out code. No TODO
stubs left in production paths.

### 5.4 AI-First Development Discipline
The AI agent system executes tasks autonomously. Every task must be:
- Self-contained (completable in one session)
- Precisely specified (no ambiguity about what "done" means)
- Dependency-explicit (agent can verify prerequisites before starting)
- Test-driven (acceptance criteria are verifiable by pytest)

### 5.5 Security by Default
- All routes require authentication unless explicitly public
- All database queries parameterized (no string formatting)
- All user input validated at the Flask layer boundary
- No secrets in code, git history, or logs
- CSRF protection on all state-modifying forms
- Rate limiting on auth endpoints from day one

### 5.6 Observability Before Features
Structured logging (JSON), error tracking (Sentry), and uptime monitoring ship
before complex features. You cannot fix what you cannot see.

### 5.7 Backwards Compatibility
Existing users, routes, and data survive every deployment. If a schema migration
is required, it runs on startup via init_db() and is idempotent. Old URLs redirect
rather than 404.

### 5.8 Test Coverage as a Gate
No new feature ships without tests. The test count grows monotonically. Any PR
that drops the test count is rejected. Target: 80% coverage by M2, 90% by M4.

---

## 6. Technology Stack (Locked Decisions)

| Layer | Current | Target | Change Trigger |
|---|---|---|---|
| Web framework | Flask 3.x | Flask 3.x | None — no rewrite |
| Templates | Jinja2 | Jinja2 + HTMX | Add HTMX in M2 |
| Database | SQLite | PostgreSQL | Before org features (Task 062) |
| ORM | None (raw SQL) | SQLAlchemy Core | With PostgreSQL migration |
| Cache / Queue | None | Redis + Celery | Before nightly scan (Task 064) |
| Auth | Session cookie | Session cookie + email verification | Task 066 |
| AI | Anthropic SDK | Anthropic SDK (Claude Sonnet) | Already wired |
| Billing | Stripe | Stripe + billing portal | Task 184 |
| CRM | HubSpot | HubSpot (extended) | Task 186 |
| Email | None | SendGrid or Postmark | Task 174 |
| Error tracking | None | Sentry | Task 221 |
| Deployment | Railway | Railway (+ worker dyno) | Task 064 |
| CI/CD | None | GitHub Actions | Task 225 |

---

## 7. Data Model Overview (Target)

### Core Entities
```
organizations        (id, name, slug, plan, trial_ends_at, stripe_customer_id)
  └── users          (id, org_id, email, password_hash, role, email_verified)
  └── sam_entities   (id, org_id, uei, cage, legal_name, certifications_json)
  └── watchlists     (id, org_id, user_id, name)
      └── watchlist_contracts (watchlist_id, internal_id)
  └── saved_searches (id, org_id, user_id, name, filters_json)
  └── capture_opps   (id, org_id, internal_id, status, priority, owner_id)
      └── capture_tasks  (id, opp_id, title, due_date, assignee_id, status)
      └── capture_notes  (id, opp_id, user_id, body, created_at)
  └── proposals      (id, org_id, opp_id, title, due_date, status)
      └── proposal_sections (id, proposal_id, type, body, order)

contracts            (existing — add org_id scope for saved/pipeline data)
contract_snapshots   (existing)
changes              (existing)
users                (existing — add org_id, role, email_verified)
```

### New AI Tables
```
ai_analyses          (id, entity_type, entity_id, analysis_type, result_json, created_at)
company_profiles     (id, org_id, uei, enrichment_json, last_enriched_at)
opportunity_scores   (id, internal_id, org_id, score, factors_json, scored_at)
```

---

## 8. Deployment Architecture (Target)

```
Railway Project: government-recompete-monitor

Services:
  web     → gunicorn app:app --workers 2
  worker  → celery -A tasks worker --concurrency 2 --queues default,alerts,enrichment
  beat    → celery -A tasks beat (scheduled tasks: nightly scan, digest emails)

Railway Plugins:
  postgresql  → DATABASE_URL
  redis       → REDIS_URL

Volumes:
  /data/contracts.db  → legacy SQLite (deprecated after Task 062)

Environment Variables (required by M2):
  SECRET_KEY, DATABASE_URL, REDIS_URL,
  ANTHROPIC_API_KEY, STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET,
  HUBSPOT_ACCESS_TOKEN, SENDGRID_API_KEY (or POSTMARK_API_KEY),
  SENTRY_DSN, SAM_API_KEY
```
