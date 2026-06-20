# MASTER ROADMAP — 09: Risks, Technical Debt Strategy & Future Expansion
# Government Recompete Monitor → AI-Powered GovCon Capture Platform

---

## 1. Risk Register

### R01 — PostgreSQL Migration Complexity
**Probability:** Medium | **Impact:** High
**Description:** The migration from SQLite to PostgreSQL (Task 062) is the highest-risk
single task in the roadmap. SQLite and PostgreSQL have subtle SQL syntax differences,
trigger behavior differences, and the FTS5 → tsvector migration requires query rewriting.
Any regression breaks the core application for all users.
**Mitigation:**
- Run all tests against both SQLite (CI fast path) and PostgreSQL (integration tests)
- Migrate in stages: schema first → queries second → FTS third
- Keep SQLite fallback for local dev permanently
- Deploy to staging and run full smoke test before production
- Zero-downtime migration: read from old, write to new, cut over
**Owner:** Backend engineer (Task 062)
**Contingency:** If PostgreSQL migration takes > 2 weeks, split into:
  - 062a: Schema + basic queries only (unblock org model)
  - 062b: FTS migration (defer until 062a stable)

---

### R02 — SAM.gov API Rate Limiting and Breaking Changes
**Probability:** High | **Impact:** Medium
**Description:** SAM.gov API has documented rate limits (100 req/day for entity lookup
on free tier, higher on System Account tier). Any feature that calls SAM.gov synchronously
will hit this limit as the user base grows. SAM.gov also has a history of undocumented
API breaking changes.
**Mitigation:**
- Cache all SAM.gov responses aggressively (24h TTL minimum)
- Use background Celery tasks for SAM API calls, never on the request path
- Obtain System Account API key (free for federal data consumers) to increase limits
- Monitor `sam_entity_cache` hit rate — alert if miss rate > 20%
- Store raw API response JSON so we can re-parse without re-fetching
- Subscribe to SAM.gov API changelog notifications
**Owner:** Data integrations (Tasks 076–083, 260)

---

### R03 — Anthropic API Cost Overruns
**Probability:** Medium | **Impact:** Medium
**Description:** AI features (capture plan, opportunity analysis, competitor research,
daily briefings, NLU search) consume Anthropic API tokens. Uncontrolled usage could
result in significant unexpected costs, especially if orgs abuse on-demand features.
**Mitigation:**
- Implement per-org monthly AI token budget (linked to plan tier)
- Cache AI results aggressively: opportunity analysis (24h), agency brief (7d), competitive research (48h)
- Use streaming for user-facing generation to avoid timeouts
- Alert when org exceeds 80% of monthly AI budget
- Rate limit AI-on-demand endpoints: 10 requests/hour/org (Task 211)
- Start with claude-haiku-4-5 for low-priority tasks, claude-sonnet-4-6 for high-value outputs
**Owner:** AI workflows (Tasks 163–168), security/rate limiting (Task 211)

---

### R04 — Celery/Redis Reliability in Production
**Probability:** Medium | **Impact:** High
**Description:** Celery workers on Railway can fail silently. If the worker crashes
during a nightly scan or email delivery, users don't get alerts. Redis connection
drops can lose queued tasks (if not using persistent Redis).
**Mitigation:**
- Use Celery's `task_acks_late = True` so tasks are only acknowledged after completion
- Configure `task_reject_on_worker_lost = True` to re-queue lost tasks
- Use `task_serializer = 'json'` (not pickle) for security and portability
- Enable Celery Flower (monitoring) in staging to observe task execution
- All critical tasks (email alerts, nightly scan) wrapped in retry logic (3x with backoff)
- Railway Redis: enable persistence (AOF) or use Redis Cloud with AOF
- Alert via Sentry on all Celery task failures
**Owner:** Platform foundation (Tasks 063–065), Operations (Task 219)

---

### R05 — Multi-tenant Data Isolation Failure
**Probability:** Low | **Impact:** Critical
**Description:** If `org_id` filtering is missing from any query, one org's data
could be visible to another org. This would be a catastrophic security breach.
**Mitigation:**
- All queries that touch org-scoped data go through `require_org_scope(org_id)` helper
- Automated test: `test_data_isolation.py` — create two orgs, add data to each, verify
  neither can see the other's data through any route
- Code review rule: any query on `contracts`, `capture_opportunities`, `proposals`,
  `watchlists`, `saved_searches`, `capture_notes` MUST have `AND org_id = ?` or equivalent
- Integration test: attempt cross-org data access via URL manipulation, assert 404
**Owner:** Org model (Task 069), integration tests (Task 223)

---

### R06 — SQLite Data Loss Before PostgreSQL Migration
**Probability:** High | **Impact:** Medium
**Description:** Current production runs on SQLite on Railway's ephemeral filesystem.
Every redeploy wipes the database. If a customer ingests data and we redeploy before
Task 062, they lose everything.
**Mitigation:** (Already partially addressed — DB_PATH points to Railway volume)
- Verify Railway volume is configured and DB_PATH is set to `/data/contracts.db`
- Add volume mount check to startup warning (already done)
- Add `/health/deep` endpoint (Task 220) to verify DB_PATH is persistent
- Communicate clearly to customers: "Data is stored on this server. Back up by exporting
  to CSV weekly until we migrate to PostgreSQL."
- Prioritize Task 062 in M2 as the first completed task

---

### R07 — AI Agent Engineering System Failures
**Probability:** Medium | **Impact:** Low–Medium
**Description:** The ai_agent/ system autonomously writes and commits code. A faulty
AI-generated patch could introduce bugs, break tests, or commit incorrect logic.
**Mitigation:**
- DRY_RUN=true default prevents any code modification without explicit authorization
- reviewer.py safety scanner blocks dangerous patterns before any patch is applied
- pytest must pass before any commit is made by the agent
- Agent never commits to main — only to ai-agent branch
- Human reviews the PR before merging to main
- Recovery system (ai_agent/recovery.py) tracks failures and prevents retry loops
- Task 048 (AI Reviewer) adds an additional AI review stage before commit

---

### R08 — Stripe Webhook Reliability
**Probability:** Low | **Impact:** High
**Description:** Stripe webhooks deliver subscription state changes. If a webhook
fails repeatedly (app unavailable), plan state in the DB gets out of sync with Stripe.
**Mitigation:**
- Stripe retries webhooks for 72 hours — ensure `/stripe/webhook` is always healthy
- Verify webhook signature on every delivery (already implemented)
- Idempotency: check `stripe_event_id` before processing to handle duplicate delivery
- Daily reconciliation Celery task: compare Stripe customer subscriptions to DB plan state
- Alert (Sentry) on any webhook processing error

---

### AR01 — No API Versioning Strategy (CTO Review Addition)
**Probability:** Low | **Impact:** Medium
**Description:** When the public REST API ships (Tasks 214, 226), there is no versioned URL
prefix strategy. Future breaking changes to response schemas will break customer integrations.
**Mitigation:**
- Establish `/api/v1/` URL prefix convention before any API route ships in Task 214
- Include `"api_version": "1.0"` in all API responses
- Never remove or rename response fields without bumping the version prefix
**Owner:** Security/API tasks (Task 214, 226)

---

### AR02 — pgvector Extension Never Installed (CTO Review Addition)
**Probability:** Medium | **Impact:** Low–Medium
**Description:** The architecture document lists pgvector as part of the target PostgreSQL
setup for future embedding-based features (NLU search, pWin, opportunity matching), but no
task installs or enables the extension. If Tasks 267 or 270 evolve to use embeddings, the
extension must already be in the database.
**Mitigation:**
- Add `CREATE EXTENSION IF NOT EXISTS vector;` to the Task 062 migration script or Task 279
- No additional libraries required until embeddings are actually used — this is a one-line addition
**Owner:** Platform foundation (Task 062) or backup task (Task 279)

---

### AR03 — Single Railway Region with No Failover (CTO Review Addition)
**Probability:** Low | **Impact:** Medium
**Description:** The entire deployment runs on Railway in a single region. Enterprise
customers or government-adjacent compliance requirements may demand multi-region deployment
or at minimum a defined failover region.
**Mitigation:**
- Document current region in `docs/ARCHITECTURE.md`
- Design stateless web tier from the start (no local file state — enforced by Task 280)
- Add multi-region evaluation as a gate item for M5 enterprise onboarding
**Owner:** Operations (Task 222), Enterprise Readiness (E21)

---

### AR04 — No Session Invalidation Mechanism (CTO Review Addition)
**Probability:** Low | **Impact:** Medium
**Description:** Users cannot see or revoke active sessions. If a device is stolen,
the attacker retains access until the session cookie expires. For a platform storing
competitive BD strategy, this is a material security gap.
**Mitigation:**
- Add `user_sessions` table: `session_token_hash, user_id, created_at, last_seen, user_agent, ip_address`
- `GET /settings/security/sessions` — list and revoke active sessions
- Add as a scope-expansion task to Task 272 (2FA) or create as Task 285 if scope is too large
**Owner:** Auth (Task 272)

---

## 2. Technical Debt Strategy

### Current Known Debt

| Item | Severity | Payoff Task | Rationale |
|---|---|---|---|
| SQLite in production | Critical | Task 062 | Cannot support multi-user writes or persistence |
| No connection pooling | High | Task 217 | Multiple workers exhaust connections at low scale |
| No CSRF protection | High | Task 210 | Security risk on all state-modifying forms |
| analytics.py monolith | Medium | Ongoing | All analytics in one file; refactor as modules emerge |
| Inline SQL in multiple files | Medium | Task 062 | Centralizing SQL in db.py reduces duplicate query logic |
| subprocess.Popen for ingest | Medium | Task 065 | Fragile; replaced by Celery task |
| No structured logging | Medium | Task 218 | Cannot debug production issues without log correlation |
| No rate limiting on auth | Medium | Task 211 | Brute force login vulnerability |
| Hardcoded public path list | Low | Ongoing | `_PUBLIC_PATHS` set in app.py and auth.py (duplicate) |
| FTS triggers + ON CONFLICT | Low | Task 062 | FTS triggers don't fire on ON CONFLICT → rebuild workaround |

### Debt Accumulation Policy

**Allowable debt:**
- Temporary SQLite usage during active development (until Task 062)
- Skipping connection pooling on single-worker deployments (until Task 217)
- Using SQLite FTS5 in dev/test even after PostgreSQL in production

**Not allowable:**
- New routes without CSRF protection (after Task 210 ships)
- New DB queries without parameterization
- New AI calls without caching (must cache or justify why not)
- New user-facing features without tests

### Refactoring Strategy

**Never refactor for its own sake.** Refactor when:
1. A new feature requires extending something that is currently hard to extend
2. The same pattern is needed in 3+ places and copy-paste creates divergence
3. A security fix requires changing the underlying structure

**Approved future refactors (scheduled at the start of each milestone):**
- M2 start: Extract `analytics.py` into `analytics/vendor.py`, `analytics/agency.py`, `analytics/dashboard.py`
- M3 start: Extract email sending from individual task files into `email_service.py`
- M4 start: Extract Stripe handling from app.py into `billing_service.py`

---

## 3. Future Expansion Strategy

### Year 2: AI Capture Manager (M5)
The platform evolves from passive intelligence to active assistance. The system
proactively finds, analyzes, and surfaces opportunities without the user searching.

**Key capabilities:**
- Zero-setup company discovery (Task 265)
- Daily autonomous opportunity scan (Task 266)
- Natural language search (Task 267)
- AI capture coaching (Task 268)
- ML pWin model (Task 270)

**Architecture additions:**
- AI agent runs as a scheduled Railway job, not just a local tool
- pgvector extension on PostgreSQL for embedding-based opportunity matching
- Event-driven architecture: contract changes → event stream → AI analysis

### Year 2–3: Autonomous Platform (M6)
The platform develops a feedback loop: it learns from the outcomes of the org's
captures (WON/LOST) and continuously improves recommendations.

**Key capabilities:**
- Feedback loops from capture outcomes to recommendation model
- Self-tuning scoring model (retrains on new outcome data)
- Autonomous competitive monitoring (daily, not just on demand)
- Partner marketplace with AI-powered matching
- Government pulse feed: budget legislation tracking via Claude

**Architecture additions:**
- Separate analytics data warehouse (read replicas or Redshift)
- ML pipeline (MLflow or simple train/deploy via Celery)
- Event-sourced architecture for capture lifecycle
- Multi-region deployment for enterprise SLA requirements

### Year 3+: Network Effects
When enough orgs are on the platform, the aggregate data creates network effects
that individual data sources cannot match.

**Potential capabilities:**
- Anonymized win/loss signals across the platform (opt-in)
- Bid community: share non-sensitive insights
- Teaming marketplace with AI-powered match recommendations (Task 269)
- Agency relationship mapping: who knows who across the contractor community

### Expansion into Adjacent Markets (Phase 5)
Once the core platform is stable and profitable in the federal prime market:

1. **State and local contracting** — same intelligence model applied to state procurement systems
2. **Grant intelligence** — federal grants (grants.gov) use similar recompete dynamics
3. **Subcontracting intelligence** — identify prime contractors likely to need subs for upcoming awards
4. **International contracting** — USAID, MCC, World Bank opportunities for international development contractors

---

## 4. Architecture Evolution Scenarios

### Scenario A: Scale to 10,000 Orgs (keep current stack)
- PostgreSQL handles up to ~1M contracts with proper indexing
- Redis + Celery scales horizontally (add worker replicas on Railway)
- Add read replicas for analytics queries
- CDN for static assets
- **No architecture change needed**

### Scenario B: Scale to 100,000 Orgs (add services)
- Separate analytics PostgreSQL read replica
- Add Elasticsearch for contract FTS (replace PostgreSQL tsvector)
- Add object storage (S3/Railway) for PDF exports and data exports
- API gateway for rate limiting and API key validation
- Microservices candidate: AI analysis service (separate from web service)

### Scenario C: Enterprise On-Premise Deployment
- Containerize everything (Docker Compose for dev, Kubernetes for enterprise)
- Replace Railway-specific env vars with generic 12-factor config
- Swap Railway PostgreSQL + Redis for customer-provided instances
- Remove hardcoded Railway volume paths
- Add LDAP/Active Directory authentication option (extend Task 251)

---

## 5. Monitoring and Success Metrics

### Platform Health Metrics
| Metric | Target | Source |
|---|---|---|
| API response p95 | < 200ms | Sentry performance |
| Celery task success rate | > 99% | Celery Flower / logs |
| Email delivery rate | > 98% | SendGrid/Postmark dashboard |
| Test coverage | > 80% | Codecov |
| Uptime | > 99.5% | Railway + uptime monitor |
| SAM.gov sync lag | < 24h | `daily_scan_log` |

### Business Health Metrics
| Metric | Target | Source |
|---|---|---|
| Trial → paid conversion | > 20% | HubSpot + Stripe |
| Monthly churn | < 5% | Stripe |
| DAU / MAU ratio | > 40% | `usage_events` |
| Contracts viewed / session | > 10 | `usage_events` |
| Captures created / org | > 2 (M3+) | `capture_opportunities` |
| NPS score | > 50 (M4) | Survey email |

### AI Quality Metrics
| Metric | Target | Source |
|---|---|---|
| AI analysis generation success | > 95% | `ai_analyses` + Sentry |
| NLU query accuracy | > 80% | Manual spot-check + user feedback |
| Recommendation relevance (user rating) | > 70% positive | Future feedback UI |
| ML pWin model AUC-ROC | > 0.65 | `ml_models.auc_roc` |

---

## 6. Recommended Implementation Order (Summary)

The single highest-ROI sequence for the next 60 days (M1):

```
1. Task 056 — min_value filter (30 min)
2. Task 057 — /health test (20 min)
3. Task 058 — ingest logging (45 min)
4. Task 059 — views labels (20 min)
5. Task 060 — pagination (20 min)
6. Task 061 → 062 — PostgreSQL (2–3 sessions: CRITICAL)
7. Task 063 → 064 → 065 — Redis + Celery (2 sessions)
8. Task 127 — transactional email (1 session)
9. Task 069 → 070 → 071 — org model + invites + RBAC (3–4 sessions)
10. Task 107 — watchlist (1 session)
11. Task 128 — expiration alerts (1 session)
12. Task 201 → 202 → 203 — billing + trial (2 sessions)
13. Task 106 — contract notes (1 session)
14. Task 072 → 073 → 074 — onboarding wizard (2 sessions)
```

This sequence delivers the minimum viable M1 in approximately 15–18 AI sessions:
first paying customer can register, track contracts, get alerts, and manage their subscription.
```
