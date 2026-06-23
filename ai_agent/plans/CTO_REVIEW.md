# CTO REVIEW — Master Engineering Roadmap
# Date: 2026-06-20 | Reviewer: CTO (Claude)

---

## Executive Summary

The roadmap is architecturally sound and product-directed. The critical path is correctly
identified. However, there are 9 categories of issues requiring correction before any
implementation session begins: milestone contradictions, missing task definitions, security
gaps, moat-building opportunities, and AI workflow blind spots.

No existing task numbers or content should be modified. Corrections are addressed through
ordering guidance and new tasks appended after Task 271.

---

## 1. Milestone Ordering Contradictions

### Problem A: M1 exit criteria depend on M2 tasks
The M1 exit criteria list "Watchlist (Task 107)" and "Email alerts on contract expiration
(Task 128)" as required. But Task 107 depends on Task 062 (PostgreSQL) and Task 069 (org
model), both of which are M2 tasks. Task 128 additionally depends on Task 127 (email
service), which depends on Task 064 (Celery). This is an impossible M1 requirement.

**Recommendation:** Revise M1 exit criteria to remove Task 107 and Task 128. Replace with:
- "Contract notes (Task 106) working" (has no M2 deps)
- "CSV export (Task 109) working"
- "Billing portal (Task 201) accessible"
- "Saved views rendering correctly (Tasks 059–060)"

Move watchlist and email alerts to M2 exit criteria where they belong.

### Problem B: Tasks 084–100 are undefined
The milestone map assigns Tasks 084–133 to M2, but the task files define only Tasks
056–083 and then jump to 101–130. Tasks 084–100 (17 tasks) are completely undefined.
These are referenced as M2 tasks by the milestone summary but have no content anywhere
in the roadmap.

**Recommendation:** Tasks 272–284 (defined at end of this document) partially fill these
gaps. The remaining task numbers (085–100) should be treated as reserved for future
definition rather than implying they are complete.

### Problem C: Security and observability too late
Tasks 210 (CSRF), 218 (structured logging), and 219 (Sentry) are scheduled for M2.
CSRF is a security baseline that should exist before any paying customer submits a form.
Logging and error tracking are required to diagnose production issues with the first customer.

**Recommendation:**
- Move Task 210 (CSRF) to M1. It has no dependencies and takes one session.
- Move Task 218 (structured logging) to M1. No dependencies.
- Move Task 219 (Sentry) to M1. No dependencies.

---

## 2. Missing Capabilities

### 2.1 Two-Factor Authentication (2FA)
The platform stores an org's entire competitive BD strategy — competitor analysis, pWin
estimates, win themes, proposal content. A compromised account could expose strategy to
a competitor. No task in the 214-task roadmap covers 2FA (TOTP or SMS).
**New task recommended:** Task 272

### 2.2 Past Performance Citation Repository
Every federal proposal requires past performance narratives. Capture managers currently
store these in Word docs and SharePoint. No roadmap task builds a structured repository
for the org's own past performance citations (contract, agency, scope, value, POC,
performance rating). This is a high-value daily-use feature that increases platform stickiness.
**New task recommended:** Task 273

### 2.3 Key Contact / Relationship Tracking
GovWin's most defensible feature is human-curated agency contact intelligence. The roadmap
mentions "agency contacts" only in competitive context. No task builds a CRM-style contact
tracker for contracting officers, program managers, and end users — the relationships that
win contracts. This is a critical gap in the capture workspace.
**New task recommended:** Task 274

### 2.4 Win/Loss Debrief with Automatic Outcome Prompt
Task 270 (ML pWin model) requires historical WON/LOST outcome data. But no task makes
outcome recording frictionless. When a proposal due date passes, nothing prompts the user
to record the outcome. Without this, the ML model starves for training data.
**New task recommended:** Task 275

### 2.5 RFP Document Parsing
Tasks 104 (solicitation linking) and 160 (compliance matrix) assume the user manually
reads the RFP. No task auto-downloads the solicitation attachment from SAM.gov and extracts
evaluation criteria, page limits, due dates, and set-aside type. This is the highest-value
AI application in the entire proposal workflow — and it is absent.
**New task recommended:** Task 276

### 2.6 Set-Aside Eligibility Check
The system knows org certifications (Task 081) and contract set-aside types (Task 103).
But no task explicitly computes and surfaces "Your org is ELIGIBLE / NOT ELIGIBLE /
CONDITIONALLY ELIGIBLE for this set-aside" on the contract detail or capture workspace.
This prevents the most obvious disqualification check and is a source of wasted BD effort.
**New task recommended:** Task 277

### 2.7 In-App Bid Calendar
Task 154 generates an iCal file for milestone exports. But there is no in-app unified
calendar showing proposal due dates, milestone dates, contract expiration dates, and
alert thresholds across all active captures. Capture managers live by their calendar.
This is a high-retention feature that currently requires iCal export to a third-party calendar.
**New task recommended:** Task 278

### 2.8 Database Backup Automation
The roadmap covers PostgreSQL migration (Task 062) but no task defines automated backup
verification. Railway has point-in-time recovery, but it must be explicitly configured
and tested. A failed migration or accidental bulk delete without backups is an existential
risk for a B2B SaaS with paying customers.
**New task recommended:** Task 279

### 2.9 Object Storage for Generated Files
PDF exports (Task 209), data exports (Task 254), and scheduled exports (Task 264) write
files to the filesystem or generate them in memory. On Railway, the filesystem is ephemeral.
Large files (50,000-contract exports, multi-section PDF reports) will exhaust memory or
be lost on redeploy. No task covers object storage (S3-compatible) for generated artifacts.
**New task recommended:** Task 280

### 2.10 Celery Beat Health Monitoring
The roadmap relies on Celery beat for nightly scans, daily briefings, weekly digests,
alert delivery, and ML retraining. If the beat scheduler dies silently, customers stop
receiving alerts and data stops refreshing — with no notification to anyone. No task
monitors beat health.
**New task recommended:** Task 281

---

## 3. Moat-Building Gaps

### 3.1 Cross-Org Opportunity Signals (Biggest Untapped Moat)
When 100+ orgs are on the platform, aggregate behavioral signals become enormously
valuable: "7 organizations are tracking this contract," "4 proposals were submitted
on this solicitation's last recompete," "This contract has the highest tracking density
in NAICS 561720." GovWin charges thousands/year for analyst-derived versions of this.
The platform can generate it automatically and opt-in from aggregate user behavior.
No task in the roadmap exploits this signal. It is the single largest moat opportunity.
**New task recommended:** Task 282

### 3.2 AI Prompt Registry and Quality Tracking
The roadmap generates AI content in Tasks 102, 120, 160–168, 267, and 268. All prompts
are implied to be hardcoded in service files with no versioning, A/B testing, or quality
measurement. As the prompt count grows, managing prompt quality becomes a competitive
advantage — better prompts produce better capture plans, which produce better win rates,
which produce more data for the ML model. No task builds prompt governance infrastructure.
**New task recommended:** Task 283

### 3.3 User Feedback on AI Outputs
No task in the roadmap collects explicit user feedback on AI-generated content (capture
plans, opportunity analysis, win themes, competitor research). Without this signal, there
is no way to know whether AI outputs are actually helping customers win contracts. A simple
👍/👎 mechanism per AI output, feeding into a quality dashboard, would close this gap
and provide data to improve prompts systematically.
**New task recommended:** Task 284

---

## 4. Duplicate / Overlapping Concerns

### 4.1 Notes Pattern Applied Twice Without Shared Base
Task 106 (contract notes) and Task 153 (capture notes) build the same pattern. Task 153
says "reuse contract_notes pattern" but this is left for the implementing agent to infer.
Both tasks should explicitly reference a shared `BaseNotes` model or mixin that is
defined once. Otherwise two divergent implementations will drift.

**Recommendation (no new task):** When implementing Task 153, extract the common notes
logic from Task 106 into a `notes_service.py` module. Document this in HANDOFF.md.

### 4.2 AI Analyses Table Used by 8+ Tasks Without a Service Layer
The `ai_analyses` table is created in Task 102 and reused by Tasks 120, 163, 164, 167,
and others. But each task independently calls the Anthropic API. There is no shared
`ai_service.py` with token budgeting, model selection (haiku vs. sonnet), caching,
retry logic, and quality logging in one place.

**Recommendation (no new task):** When implementing Task 102, create `ai_service.py`
as the single point of entry for all Anthropic API calls. All subsequent AI tasks should
call `ai_service.call(prompt, model, cache_key, ttl)`. Add this instruction to HANDOFF.md
after Task 102 ships.

---

## 5. Hidden Dependencies Not in Dependency Table

| Issue | Affected Tasks |
|---|---|
| Task 066 (email verify) → 127 → 064 → 063 — chain is 4 deep, not 1 | 066, 067, 070 |
| Task 210 (CSRF) breaks all existing form tests (test_auth.py, test_app.py) | 210 |
| Task 270 (ML pWin) requires 30+ closed captures — data availability dependency | 270 |
| Task 265 (company discovery) implicitly needs 074 (alert threshold) to complete onboarding | 265 |
| Task 069 (org model) adds `org_id` to session — all existing route tests need `g.org` fixture | 069, all route tests |
| Task 062 (PostgreSQL) must precede any task that adds new columns — init_db() restructure affects all table tests | 062, all DB tests |

**Recommendation:** Add these to the dependency table in MASTER_ROADMAP_08 before Task 062 is implemented.

---

## 6. Architecture Risks Not in Risk Register

### AR01 — No API Versioning Strategy
When the public REST API ships (Tasks 214, 226), there is no versioned URL prefix strategy.
Future breaking changes to response schemas will break customer integrations. Establish
`/api/v1/` as the URL prefix convention before any API routes ship.

### AR02 — pgvector Enabled But Never Installed
The architecture document lists pgvector as part of the target PostgreSQL setup, but no
task installs or enables the extension. If Tasks 267 (NLU search) or 270 (ML pWin) evolve
to use embeddings, the extension must already be in the database. Add a one-line extension
install to the Task 062 migration.

### AR03 — Railway Single Region
The entire deployment is on Railway in a single region. For enterprise customers or
government-adjacent compliance requirements, multi-region or at minimum a defined
failover region will be required. No task addresses this. Flag for M5 enterprise work.

### AR04 — No Session Invalidation Mechanism
Users have no way to see or revoke active sessions. If a device is stolen, the attacker
retains access until the session cookie expires. This is a security gap for a platform
storing sensitive competitive strategy.
**New task recommended:** Task 279 (see below — superseded by backup task, renumber to 285)

---

## 7. Competitive Weaknesses

### CW01 — No Pre-Solicitation / Forecast Data from Agency Plans
GovWin's most defensible premium feature is pre-solicitation intelligence: knowing about
an opportunity 12–18 months before the RFP drops. This comes from agency acquisition
plans (required to be published publicly, but hard to aggregate). No roadmap task harvests
these. An automated scraper for agency acquisition plans (many are PDF/HTML on agency
websites) would provide a capability GovTribe does not have at our price point.

### CW02 — No Bid Protest Tracking
When a contract award is protested at GAO or Court of Federal Claims, recompete timelines
shift. Competitors use bid protest data to find vulnerable incumbents (multiple protests =
unhappy customer). No task monitors the GAO protest docket. This is publicly available data.

### CW03 — Subcontract Opportunity Blind Spot
The entire platform assumes the org pursues as a prime. Many small businesses start as
subcontractors. Contracts with mandatory small business subcontracting plans (FAR 52.219-9)
identify primes that must give small businesses work. No task builds this discovery path.

---

## 8. Recommended New Tasks (append after Task 271)

---

### Task 272 — Two-factor authentication (TOTP)
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M
**Objective:** Add TOTP-based 2FA (Google Authenticator, Authy) as an optional but
strongly encouraged security layer for all user accounts.
**Requirements:** TOTP setup via QR code at `/settings/security`. Recovery codes (10)
generated and shown once. 2FA enforced org-wide if admin enables it. Session requires
re-verification after 12h. Backup: recovery code accepted in lieu of TOTP.
**DB Changes:** `users`: add `totp_secret TEXT`, `totp_enabled BOOLEAN`, `recovery_codes_json TEXT`
**Dependencies:** Task 069
**Commit:** `feat: add TOTP two-factor authentication with org-wide enforcement option`

---

### Task 273 — Past performance citation repository
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** Store and manage the org's own past performance references for use in proposals.
**Requirements:** `past_performance` table per org: contract number, agency, scope summary,
period of performance, value, POC name/phone/email, performance rating, NAICS code. CRUD at
`/settings/past-performance`. Link citations to proposal sections (Task 159). Search by NAICS
and agency. Export as formatted list (PDF/CSV).
**DB Changes:** New table: `past_performance (id, org_id, contract_num, agency, scope, pop_start, pop_end, value, poc_name, poc_email, poc_phone, rating, naics_code, notes)`
**Dependencies:** Task 069
**Commit:** `feat: add past performance citation repository linked to proposal workspace`

---

### Task 274 — Key contact / relationship tracker
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** Track the org's relationships with agency personnel: contracting officers,
program managers, and end users — the contacts that determine who wins contracts.
**Requirements:** `agency_contacts` table per org: name, title, agency, office, email, phone,
LinkedIn URL, relationship strength (1–5), last interaction date, notes. CRUD at
`/contacts`. Link contacts to specific contracts and capture opportunities. Show on agency
profile: "You have 3 contacts at this agency."
**DB Changes:** New table: `agency_contacts`, `capture_contacts (opp_id, contact_id, role)`
**Dependencies:** Tasks 069, 151
**Commit:** `feat: add key contact and relationship tracker linked to agency and capture workspaces`

---

### Task 275 — Win/loss debrief with automatic outcome prompt
**Epic:** E10 | **Milestone:** M3 | **Complexity:** S
**Objective:** When a capture moves to SUBMITTED and the proposal due date passes, prompt
the capture manager to record the outcome. Structured debrief feeds ML pWin training data.
**Requirements:** Celery daily task: find SUBMITTED captures with proposal_due_date in the
past. Send email and in-app notification: "Did you win Contract X? Record outcome." Debrief
form: WON/LOST, award amount (if won), winner (if lost), loss reason (price/technical/past
performance/other), customer feedback notes. Store in `capture_debriefs` table. Feed Task 270.
**DB Changes:** New table: `capture_debriefs (opp_id, outcome, award_amount, winner_vendor, loss_reason, feedback_notes, recorded_by, recorded_at)`
**Dependencies:** Tasks 151, 127, 169
**Commit:** `feat: add win/loss debrief form with automatic outcome prompt after proposal due date`

---

### Task 276 — RFP document download and AI parsing
**Epic:** E11 | **Milestone:** M4 | **Complexity:** XL
**Objective:** When a solicitation is linked to a contract (Task 104), automatically download
the solicitation package from SAM.gov and use Claude to extract evaluation criteria, page
limits, proposal due date, set-aside type, and key requirements.
**Requirements:** Celery task triggered when solicitation linked: download SAM.gov attachment
(PDF/DOCX). Use Claude to extract: L-sections (instructions), M-sections (evaluation criteria),
page limits per volume, proposal due date, set-aside type, key personnel requirements. Store
structured extraction in `solicitation_extracts` table. Display on contract detail.
Pre-populate compliance matrix (Task 160) from extracted L-requirements.
**DB Changes:** New table: `solicitation_extracts (solicitation_num, extracted_json, raw_text, model_version, extracted_at)`
**Dependencies:** Tasks 104, 159, 160
**Commit:** `feat: add AI RFP document parsing with automatic compliance matrix pre-population`

---

### Task 277 — Set-aside eligibility check on contract detail
**Epic:** E05 | **Milestone:** M2 | **Complexity:** S
**Objective:** Compute and display org eligibility for a contract's set-aside type using
the org's SAM certifications.
**Requirements:** `check_set_aside_eligibility(org_id, set_aside_type)` function. Returns
ELIGIBLE / INELIGIBLE / NOT_CERTIFIED (no data). Displayed on contract detail as a colored
badge. Set-aside types mapped to certifications: 8(a), SDVOSB, WOSB, HUBZone, SB, VOSB.
Filter `/contracts` by `eligible_only=true` to show only eligible contracts.
**DB Changes:** None (reads org_certifications and contracts tables)
**Dependencies:** Tasks 081, 103
**Commit:** `feat: add set-aside eligibility check using org SAM certifications`

---

### Task 278 — In-app bid calendar
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** A unified in-app calendar view showing all capture milestone dates, proposal
due dates, contract expiration alerts, and scheduled export dates across all active captures.
**Requirements:** `GET /calendar` — month/week toggle. Events from: capture_milestones,
capture_opportunities.proposal_due_date, expiration_alerts_sent thresholds, org_scheduled_exports.
Click event → navigate to relevant capture or contract. Color-coded by type. iCal feed
at `/calendar.ics` for the full org calendar (not just per-capture).
**DB Changes:** None (derived from existing tables)
**Dependencies:** Tasks 154, 128
**Commit:** `feat: add in-app bid calendar with unified milestone and expiration view`

---

### Task 279 — Database backup automation and verification
**Epic:** E18 | **Milestone:** M2 | **Complexity:** M
**Objective:** Ensure daily automated backups with verified restore capability.
**Requirements:** Configure Railway PostgreSQL daily snapshots and point-in-time recovery.
Celery weekly task: restore verification (restore to test DB, run `SELECT COUNT(*)` on
key tables, alert if mismatch). `GET /health/deep` (Task 220) reports last successful
backup timestamp. Document restore procedure in `docs/RESTORE.md`.
**DB Changes:** None
**Dependencies:** Tasks 062, 220
**Commit:** `feat: add database backup verification job and restore documentation`

---

### Task 280 — Object storage for generated files
**Epic:** E17 | **Milestone:** M3 | **Complexity:** M
**Objective:** Store generated PDFs, data export ZIPs, and scheduled export files in
S3-compatible object storage rather than the ephemeral filesystem.
**Requirements:** Add `boto3` to requirements. Configure `OBJECT_STORAGE_URL`,
`OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_KEY`, `OBJECT_STORAGE_SECRET`. Create
`storage_service.py` with `upload(key, bytes)` and `get_presigned_url(key, expires_in=3600)`.
Replace filesystem writes in Tasks 209, 254, 264 with `storage_service.upload()`. Railway
provides Cloudflare R2 as S3-compatible storage.
**DB Changes:** None
**Dependencies:** Tasks 064, 209, 254
**Commit:** `feat: add S3-compatible object storage for generated exports and PDF reports`

---

### Task 281 — Celery beat health monitoring
**Epic:** E18 | **Milestone:** M2 | **Complexity:** S
**Objective:** Detect and alert when Celery beat stops scheduling tasks, preventing silent
failure of nightly scans, alert delivery, and daily briefings.
**Requirements:** Heartbeat task registered in beat schedule (every 5 min, already Task 064).
Celery task `record_beat_heartbeat()` writes timestamp to `beat_health` Redis key. Celery
task `check_beat_health()` — if `beat_health` timestamp > 15 min old, send alert email to
org admin list and log to Sentry. `/health/deep` (Task 220) checks beat health.
**DB Changes:** None (Redis key only)
**Dependencies:** Tasks 064, 219, 220
**Commit:** `feat: add Celery beat health monitoring with Sentry alert on scheduler failure`

---

### Task 282 — Cross-org opportunity signal aggregation (moat feature)
**Epic:** E09 | **Milestone:** M4 | **Complexity:** L
**Objective:** Aggregate anonymous behavioral signals across all opted-in orgs to surface
"market heat" signals: how many orgs are tracking a contract, how many orgs have it in
their pipeline. This data is unavailable from any competitor.
**Requirements:** Opt-in at org level (`org.share_signals BOOLEAN DEFAULT FALSE`, requires
admin consent). When org tracks/watchlists/captures a contract, increment `contract_signals`
counter if org has opted in. Display on contract detail: "Tracked by 8 organizations" (no
org names revealed). Filter `/contracts` by `signal_heat=high` (≥ 5 orgs tracking).
Dashboard: "Trending this week — 12 orgs newly tracking NAICS 561720."
**DB Changes:** New table: `contract_signals (internal_id, track_count INT, capture_count INT, last_updated TEXT)`. `organizations`: add `share_signals BOOLEAN DEFAULT FALSE`.
**Dependencies:** Tasks 069, 107, 151, 202 (gated on Professional+ plan)
**Commit:** `feat: add cross-org opportunity signal aggregation with opt-in privacy model`

---

### Task 283 — AI prompt registry with version tracking
**Epic:** E12 | **Milestone:** M3 | **Complexity:** M
**Objective:** Centralize all Anthropic API prompts in a versioned registry so prompts can
be improved, A/B tested, and rolled back without code changes.
**Requirements:** Create `ai_prompts` table: `name, version, system_prompt, user_prompt_template,
model_preference, max_tokens, active`. Load active prompts at startup and cache. All AI
service calls reference a prompt by name (not hardcoded string). `GET /admin/prompts` (admin
only) to view all active prompts and version history. When a prompt is updated, the prior
version is retained for comparison.
**DB Changes:** New table: `ai_prompts`, new table: `ai_prompt_history`
**Dependencies:** Task 102 (ai_service.py should exist before this)
**Commit:** `feat: add AI prompt registry with versioning and admin management UI`

---

### Task 284 — User feedback on AI-generated content
**Epic:** E12 | **Milestone:** M3 | **Complexity:** S
**Objective:** Collect explicit thumbs-up/thumbs-down feedback on every AI-generated output
to measure quality and drive prompt improvements.
**Requirements:** After any AI-generated content is displayed (capture plan, opportunity
analysis, win themes, competitor research, agency brief), show a discreet 👍/👎 feedback
widget. `POST /ai-feedback` — stores `{analysis_id, rating, comment, user_id, org_id}` in
`ai_feedback` table. Weekly Celery task aggregates ratings by prompt name and version.
`GET /admin/ai-quality` — dashboard showing rating distribution per prompt, with trend.
**DB Changes:** New table: `ai_feedback (id, analysis_id, rating, comment, user_id, org_id, created_at)`
**Dependencies:** Task 102 (ai_analyses table), Task 169 (notifications pattern)
**Commit:** `feat: add thumbs up/down feedback on AI outputs with admin quality dashboard`

---

## 9. Recommended Milestone Corrections Summary

| Issue | Action |
|---|---|
| M1 gate includes Tasks 107, 128 (M2 dependencies) | Remove from M1, add to M2 gate |
| Tasks 084–100 undefined | Treat as reserved; new tasks 272–284 fill most gaps |
| Tasks 210, 218, 219 scheduled too late | Move to M1 (no dependencies) |
| Missing 2FA | Task 272 (M2) |
| Missing backup verification | Task 279 (M2) |
| Missing beat monitoring | Task 281 (M2) |

---

## 10. Implementation Sequencing Adjustments

Within the existing task numbering, these ordering adjustments maximize safety:

1. **Task 210 (CSRF)** → implement immediately after Task 060 (before any M2 work)
2. **Task 218 (logging)** → implement immediately after Task 057 (first session after backlog)
3. **Task 219 (Sentry)** → implement with Task 218 (same session)
4. **Task 279 (backups)** → implement with Task 062 (same sprint — migrate then immediately protect)
5. **Task 281 (beat health)** → implement with Task 064 (same sprint — set up beat, then monitor it)
6. **`ai_service.py` extraction** → implement as part of Task 102, before any other AI task

---

## 11. Long-Term Moat Assessment

| Moat Vector | Status | Priority |
|---|---|---|
| Proprietary win/loss outcome data | Partially covered (Task 270, 275) | HIGH — start collecting immediately |
| Cross-org behavioral signals | Not covered → Task 282 | HIGH — defensible at scale |
| AI-improved platform over time | Covered (Tasks 102, 270, 284) | HIGH — feedback loop is the moat |
| SAM entity + contract graph enrichment | Partially covered (Tasks 076–083) | MEDIUM |
| Partner marketplace network effect | Covered (Task 269) | MEDIUM — M6 |
| Low switching cost | RISK — capture workspace data helps retention | Need Task 273, 274 to increase stickiness |

**The two highest-priority moat investments are:**
1. Start collecting win/loss outcomes from day one (Task 275 — move to M2)
2. Build cross-org signals (Task 282) before competitors recognize this opportunity

---
*End of CTO Review — 12 new tasks recommended (272–284), 6 ordering corrections, 4 architecture risks added to register.*
