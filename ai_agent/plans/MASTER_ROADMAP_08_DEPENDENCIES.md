# MASTER ROADMAP — 08: Dependency Graph
# Government Recompete Monitor → AI-Powered GovCon Capture Platform

---

## 1. Critical Path (must complete in order)

The critical path is the sequence of tasks that, if delayed, delays everything.

```
062 (PostgreSQL)
  → 064 (Celery)
    → 065 (nightly ingest)
    → 069 (org model)
      → 070 (team invites)
      → 071 (RBAC)
        → 072–074 (onboarding)
        → 107 (watchlist)
          → 128 (expiration alerts)
            → 129, 130 (change/search alerts)
        → 151 (capture workspace)
          → 152–158 (capture features)
          → 159–162 (proposal features)
            → 163–168 (AI features)
```

**Minimum viable M2:** Tasks 062 → 064 → 069 → 127 → 072 → 107 → 128

---

## 2. Dependency Table (Task → Requires)

| Task | Title (abbreviated) | Hard Dependencies | Soft Dependencies |
|---|---|---|---|
| 056 | min_value filter | none | — |
| 057 | /health test | none | — |
| 058 | ingest logging | none | — |
| 059 | views labels | none | — |
| 060 | pagination controls | none | — |
| 061 | PostgreSQL provision | none | — |
| 062 | Schema migration | 061 | — |
| 063 | Redis provision | 061 | — |
| 064 | Celery worker | 063 | — |
| 065 | Celery ingest task | 063, 064 | 058 |
| 066 | Email verification | 127 | 062 |
| 067 | Password reset | 066, 127 | 062 |
| 068 | User profile | 062 | — |
| 069 | Org model | 062 | — |
| 070 | Team invites | 069, 127 | — |
| 071 | RBAC | 069 | — |
| 072 | Onboarding step 1 | 069 | — |
| 073 | Onboarding step 2 | 072 | — |
| 074 | Onboarding step 3 | 073 | — |
| 075 | Demo mode | 065 | 069 |
| 076 | UEI lookup | 062 | — |
| 077 | CAGE lookup | 076 | — |
| 078 | Name search | 076 | — |
| 079 | Company profile page | 076 | — |
| 080 | Link org to SAM entity | 069, 076, 079 | — |
| 081 | Certification tracking | 080, 127 | — |
| 082 | Auto-populate NAICS | 073, 080 | — |
| 083 | Filter recs by NAICS | 062, 082 | — |
| 101 | Business DNA | 062, 080 | — |
| 102 | AI company enrichment | 101 | Anthropic SDK |
| 103 | NAICS/PSC on contracts | 083 | — |
| 104 | Solicitation linking | 062, 065 | sam_lookup.py |
| 105 | Option exercise history | 062 | — |
| 106 | Contract notes | 062, 069, 071 | — |
| 107 | Watchlist | 062, 069 | — |
| 108 | Saved searches | 062, 069 | — |
| 109 | CSV export | 062 | — |
| 110 | Pipeline view | 107 | — |
| 111 | Vendor win rate | 062, 105 | — |
| 112 | Tenure in scoring | 111, 105 | — |
| 113 | Vendor competitive set | 062 | — |
| 114 | Vendor comparison | 062 | — |
| 115 | Teaming suggestions | 079, 113 | — |
| 116 | Agency budget trends | 062 | — |
| 117 | Agency NAICS concentration | 103 | — |
| 118 | Agency spend forecast | 116, 117 | — |
| 119 | Opportunity heatmap | 117 | — |
| 120 | AI agency brief | 102's pattern, 118, 119 | Anthropic SDK |
| 121 | Multi-factor scoring engine | 111, 112, 116 | — |
| 122 | Score explainability | 121 | — |
| 123 | AI recommendation engine | 082, 083, 121 | — |
| 124 | Forecasted opportunities | 105, 121, 123 | — |
| 125 | Forecast alerts | 074, 124, 127 | — |
| 126 | NAICS heatmap widget | 082, 103 | — |
| 127 | Transactional email | 064 | — |
| 128 | Expiration alerts | 107, 127, 074 | — |
| 129 | Change alerts | 107, 127, 128 | — |
| 130 | Saved search alerts | 108, 127, 065 | — |
| 151 | Capture workspace | 069, 071, 110 | — |
| 152 | Capture tasks | 151 | — |
| 153 | Capture notes | 151, 106 | — |
| 154 | Capture milestones | 151 | — |
| 155 | Milestone alerts | 154, 127 | — |
| 156 | Go/no-go tracker | 151 | — |
| 157 | Teaming partner mgmt | 115, 151 | — |
| 158 | Competitive intel panel | 113, 151 | — |
| 159 | Proposal workspace | 151 | — |
| 160 | Compliance matrix | 159 | Anthropic SDK |
| 161 | AI win themes | 159, 102 | Anthropic SDK |
| 162 | AI section drafting | 159, 161 | Anthropic SDK |
| 163 | AI capture plan | 120, 151, 156, 157, 158 | Anthropic SDK |
| 164 | AI opportunity analysis | 102, 121 | Anthropic SDK |
| 165 | Daily AI briefing | 107, 123, 127, 164 | — |
| 166 | Weekly digest | 165 | — |
| 167 | AI competitive research | 113, 102 | Anthropic SDK |
| 168 | AI price-to-win | 151, 121 | Anthropic SDK |
| 169 | In-app notifications | 069, 128, 155 | — |
| 170 | Webhooks | 069, 064 | — |
| 171 | Slack integration | 127, 128, 065 | — |
| 172 | Teams integration | 171 | — |
| 173 | Notification preferences | 127 | — |
| 201 | Billing portal | 069, Stripe | — |
| 202 | Plan enforcement | 201 | — |
| 203 | 14-day trial | 069, 201, 127 | — |
| 204 | HubSpot lifecycle sync | 201, hubspot_service.py | — |
| 205 | Usage tracking | 064, 069 | — |
| 206 | Executive analytics | 062, 151 | — |
| 207 | Revenue forecasting | 206 | — |
| 208 | Competitor analytics | 158, 206 | — |
| 209 | PDF export | 151–158, 202 | WeasyPrint |
| 210 | CSRF protection | none | — |
| 211 | Rate limiting | 063 | — |
| 212 | Audit logging | 069, 071, 064 | — |
| 213 | Encryption at rest | 062 | — |
| 214 | API key management | 071, 202, 213 | — |
| 215 | Redis analytics cache | 063, 062 | — |
| 216 | Query optimization | 062 | — |
| 217 | Connection pooling | 062 | — |
| 218 | Structured logging | none | — |
| 219 | Sentry | none | — |
| 220 | /health/deep | 063, 062 | — |
| 221 | GitHub Actions CI | none | — |
| 222 | Staging environment | 221 | — |
| 223 | Integration tests | 062, 221 | — |
| 224 | Coverage enforcement | 221 | — |
| 225 | Document routes | none | — |
| 226 | OpenAPI spec | 214 | — |
| 227 | CONTRIBUTING.md | 222 | — |
| 228 | User help center | none | — |
| 229 | Agent PostgreSQL memory | 062 | — |
| 230 | Cloud agent execution | 229, 048, 049 | — |
| 231 | AI task prioritization | 055, 230 | — |
| 251 | SAML SSO | 069, 071 | — |
| 252 | OIDC auth | 066, 069 | — |
| 253 | White-label | 069 | — |
| 254 | Full data export | 062, 064, 069 | — |
| 255 | Account deletion | 069, 201, 204 | — |
| 256 | USAspending integration | 064, 111 | — |
| 257 | FPDS direct API | 105 | — |
| 258 | NAICS lookup service | 062 | — |
| 259 | PSC lookup service | 062 | — |
| 260 | SAM live event monitor | 065, 127, 169 | — |
| 261 | Demo dataset | 062, 075, 151, 159 | — |
| 262 | Multi-format CSV import | 065 | — |
| 263 | XLSX export | 109 | openpyxl |
| 264 | Scheduled export delivery | 109, 127, 263 | — |
| 265 | Zero-setup discovery | 072, 076–080, 101, 102, 065 | — |
| 266 | Daily scan agent | 123, 128, 165, 260 | — |
| 267 | NLU contract search | 056, 065, Anthropic SDK | — |
| 268 | AI capture coaching | 151, 156, 157, 168 | — |
| 269 | Partner marketplace | 069, 079, 127 | — |
| 270 | ML pWin model | 151, 156, 121, 064 | sklearn |
| 271 | Roadmap index | all roadmap files | — |
| 272 | 2FA (TOTP) | 069 | pyotp |
| 273 | Past performance repository | 069 | — |
| 274 | Key contact/relationship tracker | 069, 151 | — |
| 275 | Win/loss debrief | 151, 127, 169 | — |
| 276 | RFP document parsing | 104, 159, 160 | Anthropic SDK |
| 277 | Set-aside eligibility check | 081, 103 | — |
| 278 | In-app bid calendar | 154, 128 | — |
| 279 | Database backup automation | 062, 220 | — |
| 280 | Object storage for exports | 064, 209, 254 | boto3 |
| 281 | Celery beat health monitoring | 064, 219, 220 | — |
| 282 | Cross-org opportunity signals | 069, 107, 151, 202 | — |
| 283 | AI prompt registry | 102 | — |
| 284 | AI output quality feedback | 102, 169 | — |

---

## 3. Parallel Workstreams (safe to run concurrently)

Once the critical path through Task 069 (org model) is complete, these streams
can proceed in parallel without blocking each other:

### Stream A (Intelligence Depth) — after 062
```
076 → 077 → 078 → 079 → 080 → 081 → 082 → 083
103 → 104 → 105 → 111 → 112 → 121 → 122
116 → 117 → 118 → 119 → 120
```

### Stream B (Capture Workflow) — after 069, 071
```
107 → 110 → 151 → 152 → 153 → 154 → 155 → 156 → 157 → 158
108 → 130
```

### Stream C (AI Features) — after 102's pattern established
```
164 → 165 → 166
167
163 (requires 120, 151–158)
168
```

### Stream D (Notifications) — after 127
```
128 → 129 → 130
173
169 → 170
171 → 172
```

### Stream E (Security/Compliance) — any time after 062
```
210 (CSRF — no dependencies)
211 → (after 063)
212 → (after 069)
213 → 214
218, 219 — any time
```

### Stream F (Analytics/Reporting) — after 062 + 151 for full data
```
206 → 207 → 208 → 209
215, 216, 217 (performance — any time after 062)
```

### Stream G (Enterprise) — after M4 complete
```
251 → 252 → 253
254, 255
```

---

## 4. Blocking Dependencies (tasks that unblock many others)

| Task | Unblocks | Risk if Delayed |
|---|---|---|
| 062 (PostgreSQL) | 35+ tasks | All multi-tenant and collaboration features blocked |
| 064 (Celery) | 20+ tasks | All async, scheduled, and email features blocked |
| 069 (Org model) | 25+ tasks | All team, billing, and capture features blocked |
| 127 (Email service) | 15+ tasks | All alert and notification features blocked |
| 151 (Capture workspace) | 15+ tasks | All capture, proposal, and AI plan features blocked |

---

## 5. Milestone Gate Checklist

### M1 Gate (before calling M1 complete)
- [ ] Tasks 056–060 complete (backlog cleared)
- [ ] Task 106 (contract notes) complete
- [ ] Task 109 (CSV export) complete
- [ ] Task 201 (billing portal) complete
- [ ] Task 203 (trial) complete
- [ ] Task 210 (CSRF protection) complete — implement immediately after Task 060
- [ ] Task 218 (structured logging) complete — implement with Task 057
- [ ] Task 219 (Sentry) complete — implement with Task 218
- [ ] First paying customer acquired
- [ ] 130+ tests passing

> **CTO Review fix:** Tasks 107 (watchlist) and 128 (expiration alerts) removed from M1
> gate. Both require PostgreSQL (062) and org model (069) which are M2 tasks. Moved to M2.

### M2 Gate
- [ ] Task 062 (PostgreSQL) complete — first task of M2
- [ ] Task 064 (Celery) complete
- [ ] Task 069 (org model) complete
- [ ] Task 072–074 (onboarding) complete
- [ ] Task 107 (watchlist) complete
- [ ] Task 108 (saved searches) complete
- [ ] Task 127 (email) complete
- [ ] Task 128 (expiration alerts) complete
- [ ] Task 076–080 (company intelligence) complete
- [ ] Task 211, 212 (additional security) complete
- [ ] Task 279 (database backup verification) complete — implement with Task 062
- [ ] Task 281 (Celery beat health monitoring) complete — implement with Task 064
- [ ] 5+ paying orgs
- [ ] 200+ tests passing

### M3 Gate
- [ ] Tasks 103–130 (contract/vendor/agency intelligence) complete
- [ ] Tasks 121–126 (scoring engine) complete
- [ ] Tasks 151–158 (capture workspace) complete
- [ ] Tasks 163–165 (AI workflows) complete
- [ ] Task 169 (in-app notifications) complete
- [ ] 20+ paying orgs
- [ ] 280+ tests passing

### M4 Gate
- [ ] Tasks 159–162 (proposal workspace) complete
- [ ] Tasks 206–209 (analytics) complete
- [ ] Task 214 (API keys) complete
- [ ] Task 221, 222 (CI/CD, staging) complete
- [ ] Task 224 (80% coverage) passing
- [ ] 50+ paying orgs
- [ ] 350+ tests passing

---

## 6. Risk Dependencies (external services)

| Service | Tasks Dependent | Risk |
|---|---|---|
| SAM.gov API | 076–083, 104, 260, 265 | Rate limits, API changes, outages |
| Anthropic API | 102, 120, 160–168, 267 | Rate limits, cost overruns, model changes |
| Stripe | 201–205 | Webhook delivery failure, API changes |
| HubSpot | 204, existing | Token expiration, API changes |
| USAspending | 256 | Undocumented changes, data lag |
| FPDS | 105, 257 | Legacy XML format, unreliable uptime |
| SendGrid/Postmark | 127–130, 165 | Deliverability issues, IP reputation |
| Railway | all deployment | Platform outages, pricing changes |

**Mitigation:** All external service calls wrapped in try/except with graceful degradation.
Never crash the app when an external service fails — log, alert, and continue.

---

## 7. Hidden Dependencies (CTO Review Additions)

These chains are not obvious from the immediate dependency entries above. Flag them before
implementation begins.

| Hidden Chain | Risk |
|---|---|
| 066 (email verify) → 127 → 064 → 063 — four-task chain; Task 063 must exist before any auth email | Block if Redis not yet provisioned |
| 210 (CSRF) — breaks all existing form tests in test_auth.py and test_app.py | Every form test must add `csrf_token` to POST data after Task 210 ships |
| 069 (org model) adds `g.org` to session — all existing route tests need `g.org` fixture | Route test file requires a `mock_org` fixture from Task 069 onward |
| 062 (PostgreSQL) restructures `init_db()` — all table tests must work against PG schema | Run full test suite against PostgreSQL in CI from Task 062 onward |
| 270 (ML pWin) — requires ≥ 30 closed captures with WON/LOST outcome for first training | Data availability dependency; Task 275 (win/loss debrief) must ship early to collect data |
| 265 (company discovery) — implicitly requires Task 074 (alert threshold) to complete onboarding | Verified in dependency table; implementing agent should confirm 074 is DONE |
| pgvector extension — mentioned in architecture as future embedding feature; must be installed | Add `CREATE EXTENSION IF NOT EXISTS vector;` to Task 062 migration or Task 279 |
