# ROADMAP.md — Official Product Roadmap

**Owner:** CTO  
**Last revised:** 2026-06-20  
**Basis:** Full repository audit + product vision

A milestone is not a date. It is a customer outcome. A milestone is not done until its
exit criteria are met — not when its features ship.

---

## Priority Levels

| Level | Meaning |
|---|---|
| **P0** | Launch blocker — nothing ships until these are resolved |
| **P1** | Revenue — directly enables or protects recurring income |
| **P2** | Customer value — improves daily utility for paying users |
| **P3** | Automation — reduces human toil, improves reliability |
| **P4** | Technical improvement — maintainability, test coverage, performance |

---

## Milestone Map

| Milestone | Name | Status | Revenue Target |
|---|---|---|---|
| M1 | MVP | **Complete** | $0 |
| M2 | Early Customers | **Active** | $500 MRR |
| **M3** | **Production Launch** | **Next** | **$2,000 MRR** |
| M4 | Growth | Planned | $10,000 MRR |
| M5 | Market Leader | Roadmap | $50,000 MRR |
| M6 | Autonomous Intelligence Platform | Roadmap | $100,000+ MRR |

---

## M1 — MVP

**Status: Complete**

A new user can find three relevant expiring contracts in under ten minutes.

**Delivered:**
- Contract search with full-text search, priority scoring, recompete score
- Vendor and agency intelligence pages
- Contract comparison page
- Saved views (High Value, Expiring Soon, Critical)
- Session-based authentication (register/login/logout, scrypt hashing)
- Railway deployment with gunicorn
- CSV ingest and API pull via SAM.gov
- AI engineering agent scaffold

---

## M2 — Early Customers

**Status: Active development**

The first paying customer uses the platform weekly as part of their BD workflow.

**Completed this milestone:**
- PostgreSQL provisioned and schema migrated (Tasks 061–062)
- Redis + Celery worker + beat scheduler deployed (Tasks 063–064)
- Nightly SAM.gov ingest at 02:00 UTC (Task 065)
- Stripe checkout integration
- HubSpot CRM integration (demo, early access, Stripe webhook)
- Demo request and early access forms

**Exit criteria (remaining):**
- `users.py` PostgreSQL compatibility fixed (P0)
- `analytics.py` PostgreSQL compatibility fixed (P0)
- Compromised API credentials rotated (P0)
- CSRF protection on all state-modifying routes (P0)
- At least one paying customer ($99–$299/mo)

---

## M3 — Production Launch

**Status: Next milestone**

**Customer Goal:** A paying customer can register, search contracts, bookmark
opportunities, receive expiration alerts, and manage their subscription — without
any manual intervention from us.

**Entry:** M2 complete, first paying customer onboarded.

**Exit Criteria:**
- All P0 blockers resolved
- Watchlist (bookmark contracts) working
- Saved searches (named, persistent filter presets) working
- Email alerts operational (contract expiration, status change)
- Billing portal live (upgrade/downgrade/cancel without our help)
- 14-day free trial with no card required
- Structured logging + Sentry error tracking deployed
- Nightly ingest confirmed working on PostgreSQL
- `/ingest/status` shows data freshness to users
- Test count ≥ 250, zero known P0 or P1 bugs

**Revenue Goal:** $2,000 MRR — ≥ 5 paying organizations.

---

## M4 — Growth

**Customer Goal:** Teams of 2–5 people at the same company collaborate on contract
research, share watchlists, and manage their active pipeline inside the platform.

**Entry:** M3 complete, ≥ 5 paying organizations.

**Exit Criteria:**
- Organization model with team invites
- Shared watchlists and pipeline view
- Onboarding wizard (company name → NAICS codes → alert setup in < 5 min)
- AI-generated opportunity analysis ("why pursue this contract?")
- CSV and PDF export from any filtered view
- SAM.gov live API integration (no manual CSV upload)
- Advanced recompete scoring (multi-factor: incumbent tenure, competition type, agency trend)
- CI/CD pipeline running tests on every PR
- Staging environment separate from production
- Test count ≥ 350, coverage ≥ 80%

**Revenue Goal:** $10,000 MRR — ≥ 25 paying organizations.

---

## M5 — Market Leader

**Customer Goal:** A capture manager's full BD workflow — discovery, qualification,
pursuit tracking, team coordination — runs inside this platform.

**Entry:** M4 complete, ≥ 25 paying organizations.

**Key capabilities:**
- Capture workspace with pipeline, tasks, notes, and milestones
- AI-generated capture plan for any expiring contract
- Solicitation tracking: link contract expirations to open SAM.gov solicitations
- Agency budget intelligence: trending spend by NAICS and PSC
- Vendor win-rate profiles: historical bid outcomes
- REST API with API key authentication
- Email digest (daily/weekly opportunity briefing)
- ML-based recompete probability model

**Revenue Goal:** $50,000 MRR — ≥ 100 paying organizations.

---

## M6 — Autonomous Intelligence Platform

**Customer Goal:** The platform proactively finds, analyzes, and briefs the team
on opportunities without manual prompting. AI handles the research; humans make
the decisions.

**Entry:** M5 complete.

**Key capabilities:**
- Zero-setup company onboarding (website URL → full entity profile in < 2 min)
- Autonomous daily opportunity briefing delivered to inbox
- Proactive competitive analysis on watched contracts
- SAM.gov live event stream monitoring
- Natural language contract search
- Teaming partner recommendations
- Partner marketplace
- Enterprise SSO (SAML/OIDC)
- SOC 2 Type II certification
- White-label for government consulting firms

**Revenue Goal:** $100,000+ MRR — enterprise annual contracts.

---

## Epic Definitions

---

### E01 — Customer Acquisition

**Objective:** Generate awareness, capture leads, and convert them to paying customers.

**Customer value:** Customers can discover, evaluate, and purchase the product without
sales friction.

**Business value:** Pipeline and MRR growth.

**Success criteria:**
- Demo request form converts ≥ 10% of visitors to a scheduled demo
- Early access list ≥ 500 contacts
- HubSpot pipeline reflects every lead conversation and status
- Free trial to paid conversion ≥ 25%

**Dependencies:** Stripe billing portal (E10), working auth (E05)

**Deliverables:**
- Landing page with clear value proposition and demo CTA
- Self-serve demo environment with sample data (no login required)
- Automated email sequence: trial start → day 3 → day 10 → day 14 expiry
- HubSpot lead scoring and deal stage automation
- Referral mechanism for existing customers

**Milestone:** M3 (acquisition infrastructure), M4 (self-serve growth)

---

### E02 — Product Intelligence

**Objective:** Make the intelligence layer smarter, more accurate, and more explainable.

**Customer value:** Capture managers spend less time filtering noise and more time
pursuing the right contracts.

**Business value:** Differentiation from competitors; reduces churn by delivering
consistent "aha" moments.

**Success criteria:**
- Recompete score correlates with actual recompete events (validated with historical data)
- Recommendations show measurable click-through to contract detail pages
- Users report > 3 useful opportunities per weekly session

**Dependencies:** E09 (data depth), E05 (PostgreSQL stable)

**Deliverables:**
- Multi-factor recompete scoring: expiration timeline + incumbent tenure + competition type + value
- Score explainability: tooltip showing why each contract scored as it did
- Opportunity recommendations refresh daily (not just on ingest)
- AI-generated opportunity analysis (one-paragraph summary: incumbent, value, risk)
- ML-based recompete probability model (M5)
- Natural language search: "IT services expiring in 90 days at DoD" (M6)

**Milestone:** M3 (scoring improvements), M4 (AI analysis), M5 (ML model)

---

### E03 — User Experience

**Objective:** Make every user interaction fast, obvious, and friction-free.

**Customer value:** Users accomplish tasks without training, confusion, or extra clicks.

**Business value:** Lower support burden, higher NPS, better trial conversion.

**Success criteria:**
- New user finds their first three relevant contracts in under 10 minutes, unassisted
- Onboarding wizard completion rate ≥ 70%
- Page load time < 1 second on contract list and dashboard
- Mobile layout is readable (no horizontal scroll, readable text)

**Dependencies:** E05 (stable platform)

**Deliverables:**
- Onboarding wizard: company name → NAICS codes → set first alert → done
- Sample data mode: pre-populated demo data visible before login
- Watchlist with one-click bookmark from any contract row
- Saved search presets (save current filter state with a name)
- Data freshness indicator on dashboard ("Data updated 6 hours ago")
- Success/cancel subscription pages with real layout
- Mobile-readable CSS pass
- CSV export from any filtered contract view
- Contract notes (freetext annotation per contract per user)
- Pipeline view: tag contracts as actively pursuing

**Milestone:** M3 (watchlist, alerts, export, freshness), M4 (onboarding, pipeline)

---

### E04 — AI Business Development

**Objective:** Use AI to surface intelligence that would take a human analyst hours to produce.

**Customer value:** BD directors make better bid/no-bid decisions faster with AI-backed
analysis on each opportunity.

**Business value:** Justifies premium pricing; creates product stickiness through daily
AI-generated value.

**Success criteria:**
- AI opportunity analysis used on ≥ 30% of contracts viewed in detail
- Capture plan generation saves users ≥ 2 hours per opportunity
- Users rate AI-generated analysis as "useful" ≥ 70% of the time

**Dependencies:** E02 (intelligence layer), E05 (stable platform), E09 (data depth)

**Deliverables:**
- One-paragraph AI opportunity summary on contract detail page
- AI-generated capture plan: incumbent analysis, competitive risk, proposal themes
- Competitive analysis: who else bids in this NAICS/agency combination?
- Daily email digest: top 5 opportunities matching the user's saved searches
- Autonomous daily briefing: proactive push, no user action required (M5)
- Natural language search interface (M6)

**Milestone:** M4 (analysis + capture plan), M5 (autonomous briefing, NL search)

---

### E05 — Platform & Infrastructure

**Objective:** Make the platform reliable, secure, and developer-friendly.

**Customer value:** The platform is always available, fast, and trustworthy with user data.

**Business value:** Prevents churn from outages, security incidents, or data loss.

**Success criteria:**
- 99.9% uptime measured over any 30-day window
- Zero P0 security vulnerabilities open at any time
- Deployment to production takes < 5 minutes and is fully automated
- Recovery from database failure < 15 minutes

**Dependencies:** None — this epic is a prerequisite for all others

**Deliverables (P0 — immediate):**
- **Rotate compromised Stripe and HubSpot credentials** (live keys in git history)
- **Fix `users.py` PostgreSQL compatibility** (replace sqlite3-specific code with SQLAlchemy)
- **Fix `analytics.py` PostgreSQL compatibility** (replace `?` placeholders with `:param` SQLAlchemy text)
- **CSRF protection** on all POST routes (login, register, ingest, demo, early-access)
- `STRIPE_WEBHOOK_SECRET` enforcement: reject unsigned webhook events
- Rate limiting on `/login` (brute force protection)

**Deliverables (P3–P4 — ongoing):**
- Structured JSON logging across all modules
- Sentry error tracking with Railway environment tagging
- PostgreSQL connection pooling (pgbouncer or SQLAlchemy pool)
- Database backup policy: daily automated backups with verified restore
- CI/CD pipeline: pytest on every PR, deploy only on green
- Staging environment separate from production
- `SECRET_KEY` rotation procedure documented
- `requirements.txt` pinned versions for reproducible builds

**Milestone:** M2 (P0 fixes), M3 (security baseline), M4 (CI/CD, staging)

---

### E06 — Autonomous Engineering

**Objective:** Maintain and improve the AI engineering system that builds this product.

**Customer value:** Indirect — faster feature delivery and fewer bugs reach customers.

**Business value:** Eliminates dependency on human engineering hours for routine
improvements. One engineer can manage a team's worth of output.

**Success criteria:**
- AI agent successfully completes ≥ 80% of queued tasks without human intervention
- Zero AI-introduced regressions reach production (reviewer catches all dangerous changes)
- Cost per completed task < $0.50 (budget tracker enforced)
- Agent unblocks itself from PostgreSQL-incompatible patterns automatically

**Dependencies:** E05 (stable platform to build on)

**Deliverables:**
- Unify `backlog/` and `ai_agent/queue/` into a single task system
- Agent learns PostgreSQL-compatible patterns from corrections (memory update)
- Auto-generated PR descriptions and changelog entries
- Scheduled morning runs via Railway cron or systemd
- Per-specialist prompt tuning based on task success/failure rates
- Agent integration tests: validate patches against a real test database, not mocks
- CTO report auto-posted weekly as GitHub issue summary

**Milestone:** M3 (unification, PR automation), M4 (prompt tuning, cron scheduling)

---

### E07 — Analytics & Reporting

**Objective:** Give customers visibility into their market position, pipeline health,
and competitive landscape.

**Customer value:** BD directors can report pipeline to leadership without building spreadsheets.

**Business value:** Enables upgrade to Professional/Team tiers where analytics depth
justifies higher price points.

**Success criteria:**
- Dashboard shows actionable metrics (not just counts) updated daily
- Agency and vendor profiles display meaningful competitive context
- Users spend ≥ 3 minutes per session on analytics pages (engagement proxy)

**Dependencies:** E09 (data depth), E05 (PostgreSQL stable)

**Deliverables:**
- Dashboard data freshness indicator with last-ingest timestamp
- Agency budget trend: spend by NAICS code over last 3 years
- Vendor win-rate: percentage of contracts a vendor retains at recompete
- Incumbent tenure heatmap: agencies with long-tenured single-vendor relationships
- Pipeline value tracker: total value of contracts user is actively pursuing
- Executive summary PDF: weekly briefing formatted for leadership
- Analytics API endpoint (Team tier only) (M4)

**Milestone:** M3 (enhanced profiles), M4 (pipeline analytics, PDF), M5 (advanced intel)

---

### E08 — Enterprise Readiness

**Objective:** Make the platform suitable for organizations with procurement, security,
and compliance requirements.

**Customer value:** Larger companies can adopt the platform without IT or legal blockers.

**Business value:** Unlocks enterprise contracts at $500–$2,000/month with annual billing.

**Success criteria:**
- Enterprise customer onboards without requesting custom configuration
- SOC 2 Type II audit completed
- SSO integration takes < 1 hour to configure
- Data export gives customers 100% of their data on request

**Dependencies:** M4 complete; E05 (security baseline), E10 (org model)

**Deliverables:**
- Organization-level data isolation (separate schemas or row-level security)
- Team invitations with role-based access control (admin/member/read-only)
- SSO/SAML integration (Okta, Microsoft Entra ID, Google Workspace)
- Audit log: who accessed what contract, when, what actions taken
- Data retention and deletion policy (GDPR-compliant data export and erasure)
- API key authentication for REST API (M4)
- SOC 2 Type II certification process initiated (M5)
- Custom domain support (M6)
- White-label option for consultancies (M6)

**Milestone:** M4 (team model, RBAC), M5 (SSO, audit log), M6 (SOC 2, white-label)

---

### E09 — Data Acquisition & Intelligence

**Objective:** Make the platform's underlying data comprehensive, fresh, and trustworthy.

**Customer value:** Customers trust the data because it is current, sourced from official
records, and transparent about its provenance.

**Business value:** Data freshness is the core product moat. Fresh, accurate data justifies
subscription renewal more than any feature.

**Success criteria:**
- Data updated within 24 hours of SAM.gov publication
- Every data point links to its source record on SAM.gov or FPDS
- Ingest failure rate < 0.1% over any 30-day window
- Schema covers ≥ 95% of fields in SAM.gov contract opportunities endpoint

**Dependencies:** E05 (Celery stable, PostgreSQL stable)

**Deliverables:**
- Confirm nightly ingest pulls live SAM.gov API data (not cached CSV)
- SAM.gov entity lookup by UEI/CAGE: vendor certifications, registration status
- Company profile: SAM entity data + all historical contracts in one view
- FPDS integration: historical contract data pre-award going back 5 years
- NAICS code intelligence: mapping, descriptions, related codes
- PSC code lookup integrated with contract detail pages
- Snapshot retention policy: purge snapshots older than 90 days
- Data quality monitoring: alert on ingest < N records (detect silent failures)
- SAM.gov live API streaming (real-time, replaces nightly batch) (M5)

**Milestone:** M3 (live API confirmed, entity lookup, quality monitoring), M4 (FPDS, NAICS), M5 (streaming)

---

### E10 — SaaS Growth & Monetization

**Objective:** Build the subscription infrastructure that converts free trials to paid
customers and retains them month over month.

**Customer value:** Customers can manage their own subscription without contacting support.

**Business value:** Predictable MRR with self-serve lifecycle management (trial → paid → upgraded → retained).

**Success criteria:**
- Trial-to-paid conversion ≥ 25%
- Monthly churn < 5%
- Average subscription value > $150/month
- Zero manual billing interventions per month

**Dependencies:** E05 (auth stable, PostgreSQL stable), Stripe already integrated

**Deliverables (P1 — immediately revenue-blocking):**
- Billing portal (Stripe Customer Portal): upgrade, downgrade, cancel, view invoices
- 14-day free trial with no card required; day-14 hard gate to billing
- Plan enforcement: feature flags per tier (Starter/Professional/Team)
- Trial expiry email sequence (day 3, day 10, day 13, day 14)
- Post-payment welcome email and onboarding prompt

**Deliverables (P2 — retention):**
- In-app upgrade prompt when a user hits a tier limit
- Monthly usage report email: "You tracked X contracts, found Y expiring this quarter"
- Annual plan discount (20% off, offered after 3 months)
- Churn prevention: email when a customer has not logged in for 7 days
- Referral program: one month free for each paying referral

**Deliverables (P3 — scale):**
- Dunning management: retry failed payments, email customer before cancellation
- Revenue dashboard for operator (MRR, churn, LTV, CAC)
- Stripe Tax integration for automated sales tax collection

**Milestone:** M3 (trial, portal, plan enforcement), M4 (retention, annual plans), M5 (dunning, revenue dashboard)

---

## Dependency Graph

```
E05 (Platform) ──────────────────────────────────────────┐
    │                                                      │
    ├── E10 (Monetization) ────────────────────── M3 Revenue
    │
    ├── E03 (UX) ──────── watchlist, alerts ────── M3 Retention
    │
    ├── E09 (Data) ──── freshness, entity lookup ── M3 Data Trust
    │
    ├── E01 (Acquisition) ─── trial, demo ────────── M3 Growth
    │
    ├── E07 (Analytics) ──────────────────────────── M4 Depth
    │
    └── E02 (Intelligence) ── scoring, AI ───────── M4 Differentiation
              │
              ├── E04 (AI BD) ─── capture plan ─── M4–M5 Premium
              │
              └── E08 (Enterprise) ──────────────── M5 Enterprise

E06 (Autonomous Engineering) runs in parallel with all epics
```

---

## What Is Never on the Roadmap

- Proposal writing automation or auto-generated bid text
- Automatic contract submissions to SAM.gov on behalf of customers
- Bid/no-bid decisions without explicit human review
- Features that remove human judgment from the capture process
- Scope creep into general procurement management (we do recompete intelligence, not ERP)

See `company/VISION.md — AI Philosophy` for the reasoning.

---

## CTO Review — 2026-06-20

**Current milestone:** M2 active. Immediate P0 blockers must be resolved before
M3 planning begins in earnest.

**P0 list (do these before anything else):**
1. Rotate compromised Stripe and HubSpot credentials (live keys in git history)
2. Fix `users.py` PostgreSQL compatibility (sqlite3-specific code breaks auth on PostgreSQL)
3. Fix `analytics.py` PostgreSQL compatibility (all dashboard queries broken on PostgreSQL)
4. CSRF protection on all POST routes

**Highest-ROI next work after P0s:** Watchlist + email alerts + billing portal.
These three features together create a daily-driver product that customers renew.

**Strategic note:** Do not build M4 features (team model, AI analysis) before
M3 exit criteria are met. The first paying customer will churn if they cannot
bookmark contracts and receive alerts. Retention before growth.
