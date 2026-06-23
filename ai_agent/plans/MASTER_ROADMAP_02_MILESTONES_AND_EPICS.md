# MASTER ROADMAP — 02: Milestones and Epics
# Government Recompete Monitor → AI-Powered GovCon Capture Platform

---

## 1. Milestone Definitions

### M1 — Internal Alpha (Days 0–60)
**Customer Goal:** The platform is stable, the backlog is clear, and the first paying
customer can use it daily for contract research and opportunity tracking.

**Entry:** Current state (84 tests, SQLite, single user per deployment)
**Exit Criteria:**
- All open backlog items resolved (056-060)
- Contract notes (Task 106) working
- CSV export (Task 109) working
- Stripe billing portal accessible (Task 201, upgrade/downgrade/cancel)
- CSRF protection (Task 210) deployed on all state-modifying routes
- Structured logging (Task 218) deployed
- Sentry (Task 219) configured with Railway environment
- Test count ≥ 130
- Zero P0 bugs open

> **Note (CTO Review):** Watchlist (107) and expiration alerts (128) were removed from M1
> exit criteria — both depend on PostgreSQL (062) and org model (069), which are M2
> foundation tasks. They are now M2 gate requirements.

**Tasks:** 056–083
**Revenue Goal:** First paying customer ($99–$299/mo)

---

### M2 — Private Beta (Days 60–150)
**Customer Goal:** Multiple people at the same company can collaborate on contract
research. A new customer can onboard in under 5 minutes without manual help.

**Entry:** M1 complete, first paying customer
**Exit Criteria:**
- Organization model with multi-user invite flow
- PostgreSQL deployed and all data migrated
- Onboarding wizard (company name/UEI → NAICS → alert setup)
- UEI/CAGE/company name → SAM entity lookup working
- Company profile page showing certifications and history
- Background job queue (Celery + Redis) operational
- Nightly SAM.gov data refresh running on schedule
- Email delivery operational (transactional email service)
- Watchlist and saved searches working (Tasks 107, 108)
- Email alerts on contract expiration sent reliably (Task 128)
- Database backup verification passing (Task 279)
- Celery beat health monitoring active (Task 281)
- Test count ≥ 200

**Tasks:** 084–133
**Revenue Goal:** 5 paying organizations, $1,000 MRR

---

### M3 — Public Beta (Days 150–240)
**Customer Goal:** A capture manager can manage their full BD pipeline inside the
platform — from opportunity discovery through capture planning.

**Entry:** M2 complete, ≥ 5 paying orgs
**Exit Criteria:**
- Capture workspace: pipeline, tasks, notes, milestones
- AI-generated capture plans
- AI opportunity analysis (why pursue? incumbent? competition?)
- Teaming partner suggestions
- NAICS and PSC code intelligence
- Competitor analytics (who else bids in this space?)
- Advanced recompete scoring with explainability
- Email digests (daily/weekly briefing)
- CSV and PDF export
- Test count ≥ 280

**Tasks:** 134–192
**Revenue Goal:** 20 paying organizations, $5,000 MRR

---

### M4 — Version 1.0 (Days 240–365)
**Customer Goal:** The platform is the single system of record for a BD team's
complete capture-to-proposal workflow.

**Entry:** M3 complete, ≥ 20 paying orgs
**Exit Criteria:**
- Proposal workspace with section templates
- REST API with API key auth
- Advanced ML-based recompete scoring
- Executive analytics dashboard
- Revenue forecasting
- SOC 2 Type II audit started
- CI/CD pipeline on every PR
- Staging environment separate from production
- Sub-200ms p95 response time on contract search
- Test count ≥ 350, coverage ≥ 85%

**Tasks:** 193–251
**Revenue Goal:** 50 paying organizations, $15,000 MRR

---

### M5 — AI Capture Manager (Year 2)
**Customer Goal:** The platform acts as an autonomous AI assistant that proactively
finds, analyzes, and briefs the team on opportunities without manual prompting.

**Entry:** M4 complete
**Key Capabilities:**
- Zero-setup company discovery (name/website → full profile in <2 min)
- Daily autonomous opportunity briefing
- Proactive capture plan generation
- SAM.gov live event stream monitoring
- Natural language contract search ("Find 8(a) set-asides in IT services expiring next quarter")

**Tasks:** 252–265
**Revenue Goal:** 100 paying organizations, $50,000 MRR

---

### M6 — Autonomous Platform (Year 2–3)
**Customer Goal:** The platform continuously improves its own recommendations based
on customer outcomes (wins, losses, pursuits abandoned) with minimal human oversight.

**Entry:** M5 complete
**Key Capabilities:**
- Feedback loops from win/loss data
- Self-tuning scoring models
- Autonomous competitive analysis
- Partner marketplace
- Enterprise SSO and white-label

**Tasks:** 266–278+
**Revenue Goal:** $100,000+ MRR, enterprise contracts

---

## 2. Epic Breakdown

| Epic | Name | Description | Milestone |
|---|---|---|---|
| E01 | Immediate Backlog | Carry-forward open items from backlog/ | M1 |
| E02 | Platform Foundation | PostgreSQL, Redis, Celery, config management | M2 |
| E03 | Auth & User Management | Email verify, password reset, user profiles, org model, team invites, RBAC | M2 |
| E04 | Customer Onboarding | Wizard, demo mode, sample data, first-run experience | M2 |
| E05 | Company Intelligence | UEI/CAGE lookup, SAM entity, certifications, company profiles | M2–M3 |
| E06 | Contract Intelligence | NAICS/PSC, solicitation linking, historical data, notes, watchlist, export | M1–M3 |
| E07 | Vendor Intelligence | Win rate, incumbent tenure, competitive set, teaming network | M3 |
| E08 | Agency Intelligence | Budget trends, NAICS concentration, spend forecast, contact intel | M3 |
| E09 | Opportunity Intelligence | AI recommendations, recompete prediction, heatmap, saved searches | M2–M4 |
| E10 | Capture Management | Workspace, pipeline, tasks, notes, calendar, milestones, teaming | M3 |
| E11 | Proposal Management | Workspace, sections, templates, win themes, compliance matrix | M4 |
| E12 | AI Workflows | Capture plan, opportunity analysis, competitor research, daily brief | M3–M5 |
| E13 | Notifications & Alerts | Email alerts, expiration warnings, digest emails, webhooks | M1–M3 |
| E14 | CRM & Billing | Billing portal, plan enforcement, trial management, HubSpot sync | M1–M2 |
| E15 | Analytics & Reporting | Executive dashboard, revenue forecast, pipeline analytics, PDF | M4 |
| E16 | Security & Compliance | CSRF, rate limiting, audit logs, API keys, SOC 2 prep | M2–M4 |
| E17 | Performance & Scalability | Query optimization, caching, CDN, connection pooling | M3–M4 |
| E18 | Operations & Monitoring | Structured logging, Sentry, uptime, CI/CD, staging | M2–M4 |
| E19 | Testing & Quality | Coverage targets, integration tests, E2E tests, load tests | M2–M4 |
| E20 | Documentation | API docs, user guide, developer guide, changelog | M3–M4 |
| E21 | Enterprise Readiness | SSO/SAML, multi-org, audit compliance, custom domains, SLA | M5–M6 |
| E22 | AI Agents (Engineering) | Autonomous engineering improvements (ai_agent/ system extensions) | M2–M4 |
| E23 | Data Integrations | SAM.gov live API, FPDS, USAspending, NAICS service | M2–M4 |
| E24 | Demo, Sample Data & Export | Demo env, sample company, CSV/XLSX/PDF export, bulk ops | M2–M3 |

---

## 3. Recommended Implementation Order

### Stream A: Foundation (must go first — blocks everything)
```
056 → 057 → 058 (clear backlog)
061 → 062 (PostgreSQL — blocks all multi-tenant features)
063 → 064 → 065 (Redis + Celery — blocks nightly scan and alerts)
066 → 067 → 068 (email verification, password reset — blocks trial management)
069 → 070 → 071 (org model, invites, RBAC — blocks all team features)
```

### Stream B: Customer Value (can parallel with Stream A after 062)
```
084 → 085 → 086 (watchlist and saved searches — immediate customer value)
174 → 175 → 176 (email alerts — immediate retention value)
184 → 185 → 186 (billing portal — immediate revenue value)
072 → 073 → 074 → 075 (onboarding wizard — immediate activation value)
```

### Stream C: Intelligence Depth (starts after M2)
```
076 → 077 → 078 → 079 → 080 (company intelligence / UEI)
087 → 088 → 089 → 090 → 091 (contract intelligence depth)
123 → 124 → 125 → 126 (opportunity scoring engine)
```

### Stream D: AI Features (starts after M2, accelerates in M3)
```
161 → 162 → 163 (AI capture plan generation)
164 → 165 → 166 (AI opportunity analysis)
167 → 168 (AI competitor research)
252 → 253 → 254 (autonomous company discovery)
```

### Stream E: Capture Workflow (M3)
```
134 → 135 → 136 (capture workspace)
137 → 138 → 139 (capture tasks and notes)
140 → 141 → 142 (capture milestones and calendar)
143 → 144 → 145 (teaming partners)
```

### Stream F: Enterprise (M4–M5)
```
242 → 243 → 244 (SSO/SAML)
245 → 246 (multi-org, audit compliance)
225 → 226 → 227 (CI/CD pipeline)
228 → 229 (staging environment)
```

---

## 4. Parallelism Rules for AI Agents

These streams can run in parallel IF their prerequisite tasks are complete:

| Parallel Pair | Prerequisite |
|---|---|
| E06 (Contract Intel) + E07 (Vendor Intel) | Task 062 (PostgreSQL) |
| E10 (Capture Mgmt) + E11 (Proposal Mgmt) | Task 069 (Org model) |
| E12 (AI Workflows) + E13 (Notifications) | Task 064 (Celery) |
| E15 (Analytics) + E16 (Security) | Task 062 (PostgreSQL) |
| E19 (Testing) | Any completed epic |
| E20 (Docs) | Any completed epic |

---

## 5. Complexity Scale

| Level | Description | Typical Session Count |
|---|---|---|
| XS | Single-function change, no DB, no new routes | 0.5 |
| S | 1–3 files, 1 new route or function, minimal test work | 1 |
| M | 3–6 files, new DB column/table, 5–10 new tests | 1–2 |
| L | 6–12 files, new subsystem, 10–20 new tests | 2–3 |
| XL | New epic-level subsystem, major DB changes, 20+ tests | 3–5 |

---

## 6. Milestone Task Count Summary

| Milestone | Task Range | Count | Epic Coverage |
|---|---|---|---|
| M1 | 056–083 | 28 | E01, E06 (partial), E13 (partial), E14 (partial) |
| M2 | 084–133 | 50 | E02, E03, E04, E05, E09, E16 (partial), E18 (partial), E23 |
| M3 | 134–192 | 59 | E07, E08, E10, E12, E13, E15 (partial), E17, E24 |
| M4 | 193–251 | 59 | E11, E15, E16, E18, E19, E20, E22 |
| M5–M6 | 252–284 | 40 | E21, E23 (advanced), AI Agents (advanced), CTO Review additions |
| **Total** | **056–284** | **236** | **24 epics** |
