# MASTER ROADMAP — 07: Tasks 251–278
# Epics: E21 (Enterprise Readiness), E23 (Data Integrations),
#         E24 (Demo, Sample Data & Import/Export), M5 AI Capture Manager

---

## EPIC E21 — Enterprise Readiness

---

### Task 251 — Add SSO / SAML 2.0 authentication
**Epic:** E21 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 4
**Objective:** Enterprise customers require SSO (SAML 2.0 / OIDC) for their auth
policies. Users should log in with company credentials, not a separate password.
**Requirements:**
- Use `python3-saml` or `python-social-auth` for SAML 2.0 support
- Per-org SSO configuration: `org_sso_config` table (entity_id, sso_url, cert, attribute_mapping)
- `GET /sso/<org_slug>` — SAML-initiated login
- `POST /sso/<org_slug>/callback` — assertion consumer service
- Map SAML attributes to user fields (email, name, groups)
- Auto-provision users on first SSO login
- Existing email/password login still works (not removed)
**Acceptance Criteria:**
- SSO login flow completes in < 5 seconds
- New users auto-created on first SSO login
- Existing users linked by email to SSO identity
- SSO failures show helpful error (certificate expired, attribute missing)
**Dependencies:** Tasks 069, 071
**DB Changes:** New table: `org_sso_config (org_id, provider, entity_id, sso_url, slo_url, cert_pem, attribute_map_json, enabled)`; `users`: add `sso_id TEXT`, `sso_provider TEXT`
**API Changes:** `/sso/<slug>`, `/sso/<slug>/callback`
**Frontend Changes:** "Sign in with SSO" button on login page
**Testing:** 6 new tests (mock SAML assertions)
**Commit:** `feat: add SAML 2.0 SSO authentication with per-org configuration`
**Follow-up:** Task 252 (OIDC support)

---

### Task 252 — Add OIDC authentication (Google, Microsoft)
**Epic:** E21 | **Milestone:** M5 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow users to sign in with Google or Microsoft accounts as an alternative
to email/password. Simpler than SAML for smaller enterprises.
**Requirements:**
- OIDC via `authlib` or `flask-dance`
- Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Microsoft: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
- Callback: `GET /auth/google/callback`, `GET /auth/microsoft/callback`
- On first OIDC login: find existing user by email or create new one
- Link OIDC identity to existing account if email matches
**Acceptance Criteria:**
- "Sign in with Google" and "Sign in with Microsoft" buttons on login page
- First-time OIDC login creates account and joins any invited org
- Email/password still works for non-SSO users
**Dependencies:** Tasks 066, 069
**DB Changes:** `users`: add `oidc_provider TEXT`, `oidc_sub TEXT`
**API Changes:** OAuth callback routes
**Frontend Changes:** Social login buttons on login.html
**Testing:** 4 new tests (mock OIDC token response)
**Commit:** `feat: add OIDC authentication with Google and Microsoft providers`
**Follow-up:** Task 253 (white-label)

---

### Task 253 — White-label support (custom domain + logo)
**Epic:** E21 | **Milestone:** M5 | **Complexity:** M | **Sessions:** 2
**Objective:** Enterprise customers want the platform on their own domain with their logo.
**Requirements:**
- `org_custom_domain` column on `organizations`: `custom_domain TEXT`
- Railway custom domain: documented process for org to point their DNS
- `org_logo_url TEXT` on organizations: upload/link to org logo
- `base.html` reads `g.org.org_logo_url` and replaces default logo
- Platform name in emails: `g.org.platform_name or "Recompete Monitor"`
- Custom domain routing: Flask reads `Host` header and looks up org
**Acceptance Criteria:**
- App served on `recompete.clientname.com` with their logo
- Email footer shows `Powered by Recompete Monitor` unless white-label configured
- Custom domain users redirected to their subdomain on login
**Dependencies:** Task 069
**DB Changes:** `organizations`: add `custom_domain TEXT`, `org_logo_url TEXT`, `platform_name TEXT`
**API Changes:** Domain lookup middleware
**Frontend Changes:** Dynamic logo in base.html
**Testing:** 3 new tests
**Commit:** `feat: add white-label support with custom domain and logo configuration`
**Follow-up:** None

---

### Task 254 — Add data export (full org data export for portability)
**Epic:** E21 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow org owners to export all their data for portability or offboarding.
**Requirements:**
- `POST /settings/export/request` — triggers Celery task, emails download link
- Export: ZIP containing:
  - `contracts_watched.csv` (watchlist)
  - `capture_opportunities.csv`
  - `capture_tasks.csv`
  - `capture_notes.jsonl`
  - `proposals.csv`
  - `saved_searches.json`
  - `audit_log.csv` (last 12 months)
- Link expires in 24 hours
- Export stored in `/tmp` or object storage, cleaned up after download
**Acceptance Criteria:**
- Export generated in < 2 minutes for typical org
- All files present in ZIP
- Download link expires after 24 hours
**Dependencies:** Tasks 062, 064, 069
**DB Changes:** New table: `data_exports (id, org_id, status, download_url, expires_at, created_at)`
**API Changes:** `POST /settings/export/request`, `GET /settings/export/<id>/download`
**Frontend Changes:** "Export My Data" button in settings
**Testing:** 3 new tests
**Commit:** `feat: add full org data export as ZIP with time-limited download link`
**Follow-up:** None

---

### Task 255 — Add org deletion and account termination
**Epic:** E21 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow org owners to delete their account and all associated data.
Required for GDPR/CCPA compliance.
**Requirements:**
- `POST /settings/delete-account` (owner only, password confirmation required)
- Soft delete: set `org.deleted_at`, `user.deleted_at` — retain 30 days then hard delete
- Hard delete Celery task: runs 30 days after soft delete
- Cancel Stripe subscription on soft delete
- Send confirmation email: "Your account has been scheduled for deletion"
- Notify HubSpot: deal stage → "Churned"
**Acceptance Criteria:**
- Org data inaccessible immediately after soft delete
- Hard delete removes all rows in 30 days (cascade)
- Stripe subscription cancelled same day
- Cannot undo after 30-day grace period
**Dependencies:** Tasks 069, 201, 204
**DB Changes:** `organizations`, `users`: add `deleted_at TEXT`
**API Changes:** `POST /settings/delete-account`
**Frontend Changes:** Delete account section in settings (destructive UI pattern)
**Testing:** 4 new tests
**Commit:** `feat: add org deletion with 30-day grace period and Stripe cancellation`
**Follow-up:** None

---

## EPIC E23 — Data Integrations

---

### Task 256 — Integrate USAspending.gov API for historical awards
**Epic:** E23 | **Milestone:** M3 | **Complexity:** L | **Sessions:** 3
**Objective:** Pull historical award data from USAspending.gov to enrich vendor profiles
with long-term contract history beyond what's in the local database.
**Requirements:**
- Create `usaspending_service.py` with `get_vendor_awards(vendor_name, years=10)` function
- Call `https://api.usaspending.gov/api/v2/search/spending_by_award/` with recipient name filter
- Parse: award amount, agency, NAICS, period_of_performance, award_type
- Store in `historical_awards` table (separate from contracts table)
- Celery task: enrich vendor profile on background when vendor page first viewed
- Display on vendor.html: "Historical Awards (USAspending)" section
**Acceptance Criteria:**
- Historical awards loaded within 30 seconds of first vendor page view
- Vendor win rate improved by including USAspending history
- "Data from USAspending.gov" attribution shown
**Dependencies:** Tasks 064, 111
**DB Changes:** New table: `historical_awards (id, vendor_name, agency, naics_code, award_amount REAL, award_date TEXT, period_end TEXT, source TEXT, source_id TEXT)`
**API Changes:** None
**Frontend Changes:** Historical awards section on vendor.html
**Testing:** 4 new tests (mock USAspending responses)
**Commit:** `feat: integrate USAspending.gov for historical vendor award enrichment`
**Follow-up:** Task 257 (FPDS direct integration)

---

### Task 257 — FPDS direct API integration for contract modification history
**Epic:** E23 | **Milestone:** M3 | **Complexity:** L | **Sessions:** 3
**Objective:** Pull contract modifications directly from FPDS-NG API to track option
exercises, extensions, and terminations more accurately than SAM.gov CSV.
**Requirements:**
- Create `fpds_service.py` enhancements for FPDS Atom feed API
- Endpoint: `https://www.fpds.gov/ezsearch/FEEDS/ATOM?PIID=<piid>`
- Parse: modification type (Option, Admin, Funding, Termination), effective date, cumulative value
- Store in existing `contract_modifications` table (Task 105)
- Celery task: sync modifications for all contracts with a known PIID weekly
**Acceptance Criteria:**
- Option exercise history accurate to within 1 week of FPDS publication
- Terminations detected and reflected in contract priority score
- Rate limiting: max 10 FPDS requests/second to avoid throttling
**Dependencies:** Task 105
**DB Changes:** None (extends existing contract_modifications)
**Testing:** 4 new tests (mock FPDS Atom feed)
**Commit:** `feat: add FPDS direct API integration for accurate modification history`
**Follow-up:** Task 258 (NAICS lookup service)

---

### Task 258 — Add NAICS code lookup service and browsable index
**Epic:** E23 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Provide human-readable NAICS code titles and sector hierarchy for
filtering, onboarding, and display throughout the app.
**Requirements:**
- Import NAICS 2022 code list (CSV from Census Bureau) into `naics_codes` table
- Columns: `code, title, sector_code, sector_title, subsector_code, subsector_title`
- `GET /api/naics?q=<search>` — search by code or title, return JSON
- `GET /api/naics/<code>` — full hierarchy for a code
- Used by: onboarding step 2 selector, contract filter, vendor/agency profiles
**Acceptance Criteria:**
- All 2022 NAICS codes searchable by name or code prefix
- Hierarchy returns sector → subsector → industry group → code
- Autocomplete returns results in < 100ms
**Dependencies:** Task 062
**DB Changes:** New table: `naics_codes (code TEXT PK, title TEXT, sector_code TEXT, sector_title TEXT, subsector_code TEXT)`; preloaded from Census CSV
**API Changes:** `GET /api/naics`, `GET /api/naics/<code>`
**Frontend Changes:** Autocomplete component (used in onboarding, filters)
**Testing:** 3 new tests
**Commit:** `feat: add NAICS 2022 lookup service with hierarchy and autocomplete API`
**Follow-up:** Task 259 (PSC code lookup)

---

### Task 259 — Add PSC code lookup service
**Epic:** E23 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Provide human-readable PSC (Product and Service Code) titles for
contract filtering and display.
**Requirements:**
- Import PSC code list from SAM.gov data dictionary into `psc_codes` table
- `GET /api/psc?q=<search>` — search by code or description
- Used in contract detail display and filter bar
**Acceptance Criteria:**
- All active PSC codes searchable
- Contract detail shows "PSC S208 — Housekeeping" (code + title)
**Dependencies:** Task 062
**DB Changes:** New table: `psc_codes (code TEXT PK, description TEXT, category TEXT)`
**API Changes:** `GET /api/psc`, `GET /api/psc/<code>`
**Testing:** 2 new tests
**Commit:** `feat: add PSC code lookup service with autocomplete API`
**Follow-up:** None

---

### Task 260 — Build SAM.gov entity live event stream monitor
**Epic:** E23 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 4
**Objective:** Monitor SAM.gov for new opportunities matching org NAICS codes in
near-real-time (not just nightly batch). Alert within 1 hour of a new solicitation
matching an org's profile.
**Requirements:**
- SAM.gov `GET /opportunities/v2/search` with `postedFrom=<last_run_time>`
- Celery beat task: every 2 hours, fetch new solicitations posted since last check
- Match against all orgs' NAICS codes and alert settings
- For matches: create `new_solicitation_alerts` and send email + in-app notification
- Store solicitations in `sam_solicitations` table (separate from contracts)
**Acceptance Criteria:**
- New solicitation alert delivered within 2 hours of posting on SAM.gov
- Alerts respect org alert settings (minimum value, NAICS filter)
- No duplicate alerts for the same solicitation+org
**Dependencies:** Tasks 065, 127, 169
**DB Changes:** New tables: `sam_solicitations`, `solicitation_alerts_sent`
**API Changes:** None
**Frontend Changes:** New solicitation alerts in notification center
**Testing:** 4 new tests
**Commit:** `feat: add SAM.gov live solicitation monitoring with 2-hour alert latency`
**Follow-up:** None

---

## EPIC E24 — Demo, Sample Data & Import/Export

---

### Task 261 — Seed comprehensive demo dataset
**Epic:** E24 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Create a realistic, self-consistent demo dataset with 200 contracts,
5 vendors, 8 agencies, 3 capture opportunities, and 2 proposals.
**Requirements:**
- `seed_data/demo_seed.py` — generates all demo data programmatically
- Contracts: realistic values ($500K–$25M), NAICS codes from 5 sectors,
  realistic expiration dates (mix of past, current, upcoming)
- Vendors: 5 fictional but plausible company names with contract histories
- Capture opportunities: 2 PURSUING, 1 QUALIFYING, with tasks, notes, milestones
- Proposals: 1 DRAFTING with sections, 1 SUBMITTED
- `flask seed-demo` CLI command to apply seed data to any environment
**Acceptance Criteria:**
- Demo dataset installable in < 30 seconds
- Demo data visually plausible (no lorem ipsum in titles)
- Demo captures and proposals demonstrate AI features
**Dependencies:** Tasks 062, 075, 151, 159
**DB Changes:** None (data only)
**Testing:** 2 tests (seed runs without error, data count assertions)
**Commit:** `feat: add comprehensive demo dataset with captures and proposals`
**Follow-up:** Task 262 (import from CSV)

---

### Task 262 — Add bulk CSV import (multiple contract formats)
**Epic:** E24 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Accept CSV uploads in multiple common formats: SAM.gov bulk download,
FPDS export, USAspending download, and a custom template.
**Requirements:**
- Extend `ingest.html` upload with format selector
- Format parsers: `parsers/sam_bulk.py`, `parsers/fpds_csv.py`, `parsers/usaspending.py`, `parsers/custom_template.py`
- Custom template: downloadable blank CSV with column documentation
- Preview before import: show first 5 rows with parsed field mapping
- Async import via Celery (large files can take minutes)
- Import progress shown via `/ingest/status`
**Acceptance Criteria:**
- All 4 formats parse without error on standard exports from each source
- Preview shows correct field mapping before commit
- Import of 5,000 contracts completes in < 2 minutes
**Dependencies:** Task 065 (Celery ingest task)
**DB Changes:** None
**API Changes:** `/ingest` accepts `format` param
**Frontend Changes:** Format selector and preview table on ingest.html
**Testing:** 6 new tests (one per format + preview)
**Commit:** `feat: add multi-format CSV import with preview for SAM, FPDS, USAspending`
**Follow-up:** None

---

### Task 263 — Add XLSX export from any contract list
**Epic:** E24 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Export contract lists as formatted Excel workbooks with metadata header.
**Requirements:**
- `GET /contracts/export.xlsx` — same filters as CSV export (Task 109)
- Use `openpyxl` to generate XLSX
- Format: header row styled, value column formatted as currency, date columns as date type
- Metadata sheet: export date, filters applied, total count
**Acceptance Criteria:**
- File opens in Excel without warnings
- Currency formatted as $X,XXX,XXX
- Metadata sheet present
**Dependencies:** Task 109 (CSV export)
**DB Changes:** None
**API Changes:** `GET /contracts/export.xlsx`
**Frontend Changes:** XLSX export button alongside CSV button
**Testing:** 2 new tests
**Commit:** `feat: add XLSX contract list export with currency and date formatting`
**Follow-up:** None

---

### Task 264 — Add scheduled export delivery (weekly to email)
**Epic:** E24 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow orgs to schedule automatic weekly contract list exports delivered
by email (useful for teams using external spreadsheets).
**Requirements:**
- `org_scheduled_exports` table: `org_id, filter_json, format (csv/xlsx), frequency (weekly/monthly), day_of_week, email_recipients, enabled`
- Settings page: configure scheduled export
- Celery beat: run exports on schedule, email ZIP attachment
- Org admin only
**Acceptance Criteria:**
- Weekly export arrives on configured day by 08:00 UTC
- Export matches the configured filters
- Recipients configurable (comma-separated emails)
**Dependencies:** Tasks 109, 127, 263
**DB Changes:** New table: `org_scheduled_exports`
**API Changes:** `GET/POST /settings/exports`
**Frontend Changes:** `templates/settings/exports.html`
**Testing:** 3 new tests
**Commit:** `feat: add scheduled weekly contract export delivered by email`
**Follow-up:** None

---

## M5 — AI Capture Manager (Foundation Tasks)

---

### Task 265 — Zero-setup company discovery (name/website → full profile)
**Epic:** E05/E12 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 4
**Objective:** Given only a company name or website, automatically discover UEI, CAGE,
SAM registrations, NAICS codes, certifications, and historical contracts — with no
manual input required beyond the initial identifier.
**Requirements:**
- `company_discovery_worker(org_id, seed_input)` — Celery task
- Phase 1: Try UEI/CAGE lookup (Task 076/077), then name search (Task 078)
- Phase 2: If website provided, scrape `robots.txt`-compliant public pages to extract
  company name, UEI mentions, CAGE, email domains
- Phase 3: Match discovered identifiers to SAM entity, fetch full entity profile
- Phase 4: Search local contracts for vendor name variations
- Phase 5: Claude enrichment: synthesize into business_dna (Task 101)
- Report result to user: "Discovered: [legal name], UEI [xxx], [N] contracts found"
- Complete in < 5 minutes
**Acceptance Criteria:**
- Company entered during onboarding fully auto-discovered without further input
- Discovery uses ≤ 5 API calls to SAM.gov (respect rate limits)
- Business DNA computed from discovered data
- User sees progress: "Searching SAM.gov... Found entity... Loading contract history..."
**Dependencies:** Tasks 072, 076, 077, 078, 079, 080, 101, 102, 065
**DB Changes:** `organizations`: add `discovery_status TEXT`, `discovery_log_json TEXT`
**API Changes:** `GET /onboarding/discovery-status` (HTMX polling)
**Frontend Changes:** Discovery progress card on onboarding completion page
**Testing:** 6 new tests (mock all external APIs, test discovery stages)
**Commit:** `feat: add zero-setup company discovery from name or website input`
**Follow-up:** Task 266 (autonomous daily opportunity scan)

---

### Task 266 — Autonomous daily opportunity scan agent
**Epic:** E12 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 3
**Objective:** A daily Celery task that, for each org, automatically runs the full
intelligence pipeline: pull new data, score opportunities, generate recommendations,
send briefing — with no human trigger required.
**Requirements:**
- `daily_scan_agent(org_id)` Celery task:
  1. Check for new SAM.gov solicitations in org's NAICS (Task 260)
  2. Run expiration alerts (Task 128)
  3. Recalculate recommendations (Task 123)
  4. Generate briefing content (Task 165)
  5. Send daily briefing email (if enabled)
  6. Log scan results to `daily_scan_log` table
- Scheduled at 04:00 UTC for all orgs
- Parallelized: each org scanned as a separate Celery task
**Acceptance Criteria:**
- Full scan completes for 100 orgs in < 15 minutes
- Briefing email delivered by 06:00 UTC
- Failed scans logged and retried once
**Dependencies:** Tasks 123, 128, 165, 260
**DB Changes:** New table: `daily_scan_log (id, org_id, scan_date, tasks_run, duration_ms, errors_json, created_at)`
**API Changes:** None
**Frontend Changes:** None (background only)
**Testing:** 4 new tests
**Commit:** `feat: add autonomous daily opportunity scan agent for all orgs`
**Follow-up:** Task 267 (NLU contract search)

---

### Task 267 — Natural language contract search
**Epic:** E12 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 3
**Objective:** Allow users to search contracts using plain English queries that are
automatically translated to structured filters.
**Requirements:**
- Search box accepts natural language: "8a set-aside janitorial contracts expiring next quarter"
- NLU layer (Claude): parse intent → extract: NAICS codes, agency, days_remaining range,
  set-aside type, value range, keywords
- Translate to existing `get_contracts()` parameters
- Show parsed filters as chips: "NAICS: 561720 | Set-aside: 8(a) | Expiring in: 90 days"
- User can edit parsed filters
- Falls back to keyword search if NLU fails
**Acceptance Criteria:**
- 80% of natural language queries produce correct filter parameters
- Parsed filter chips visible and editable
- Response time < 3 seconds (NLU call + DB query)
- Falls back gracefully when Anthropic API unavailable
**Dependencies:** Tasks 056, 065, Anthropic SDK
**DB Changes:** None
**API Changes:** `POST /search/nlq` — natural language query → filters JSON
**Frontend Changes:** NLU search mode toggle on contracts list
**Testing:** 5 new tests (query → expected filters assertions)
**Commit:** `feat: add natural language contract search powered by Claude`
**Follow-up:** None

---

### Task 268 — AI capture coaching (proactive guidance)
**Epic:** E12 | **Milestone:** M5 | **Complexity:** L | **Sessions:** 3
**Objective:** Proactively surface capture coaching suggestions on the capture workspace:
"You haven't updated this capture in 14 days", "Bid decision is in 7 days — go/no-go
not completed", "No teaming partner identified for this 8(a) opportunity."
**Requirements:**
- `capture_coach_service.py`: generate coaching hints for each capture opportunity
- Rule engine + Claude validation:
  - Inactivity: no activity in 14+ days → "Capture appears stalled"
  - Missing go/no-go: bid decision < 30 days away
  - Missing teaming: 8(a)/SDVOSB contract, no confirmed partner
  - Stale intel: agency brief not refreshed in 30 days
  - Missing PTW: pursuing stage, no price-to-win estimate
- Hints shown as a notification panel on capture workspace
- User can dismiss hints (stored in `dismissed_hints` table)
**Acceptance Criteria:**
- Coaching panel shows on workspace when hints are active
- Hints accurate to capture state (no false positives)
- Dismissals persist per-user per-capture
**Dependencies:** Tasks 151, 156, 157, 168
**DB Changes:** New table: `dismissed_hints (user_id, opp_id, hint_type, dismissed_at)`
**API Changes:** `GET /capture/<opp_id>/coaching-hints`
**Frontend Changes:** Coaching hints panel on capture workspace
**Testing:** 4 new tests
**Commit:** `feat: add AI capture coaching with proactive guidance hints`
**Follow-up:** None

---

### Task 269 — Partner marketplace (connect small businesses)
**Epic:** E21 | **Milestone:** M6 | **Complexity:** XL | **Sessions:** 4
**Objective:** Allow orgs to discover potential teaming partners across the platform
based on complementary capabilities and certifications.
**Requirements:**
- Opt-in: orgs can publish a "teaming profile" listing capabilities, NAICS codes,
  certifications, and teaming preferences
- `GET /marketplace` — browse/search teaming profiles
- Filter by: certification type, NAICS sector, contract size preference, location
- Contact request: `POST /marketplace/<org_slug>/contact` — sends intro email to partner org
- Privacy: only opted-in orgs visible; contact info only after mutual opt-in
**Acceptance Criteria:**
- Org teaming profile publishable in < 5 minutes
- Search results filterable by certification and NAICS
- Contact request goes to partner's org admin email (not direct user email)
- Partner accepts/ignores contact request — no auto-reveal of email
**Dependencies:** Tasks 069, 079, 127
**DB Changes:** New table: `teaming_profiles (org_id, capabilities_text, naics_codes_json, certs_json, size_preference, is_published)`; new table: `teaming_contacts (from_org_id, to_org_id, message, status, created_at)`
**API Changes:** `GET/POST /marketplace`, `GET /marketplace/<slug>`, `POST /marketplace/<slug>/contact`
**Frontend Changes:** `templates/marketplace.html`, `templates/marketplace_profile.html`
**Testing:** 5 new tests
**Commit:** `feat: add opt-in partner marketplace for teaming discovery`
**Follow-up:** None

---

### Task 270 — AI win probability model (ML-based pWin)
**Epic:** E09 | **Milestone:** M5 | **Complexity:** XL | **Sessions:** 5
**Objective:** Train a machine learning model on historical capture outcomes (WON/LOST)
to predict pWin for new opportunities based on org characteristics, opportunity features,
and competitive context.
**Requirements:**
- Collect training data: all closed captures with WON/LOST outcome + feature vector
  (recompete score, org-contract NAICS match, certification fit, incumbent tenure,
  days_remaining at capture start, competitive threat level)
- Train sklearn `GradientBoostingClassifier` when ≥ 30 training examples available
- Store model in `ml_models` table (serialized with joblib)
- Integrate prediction into `capture_opportunities.ml_pwin REAL`
- Display alongside user-entered pWin estimate: "Model estimate: 67%"
- Retrain weekly when new closed captures available
**Acceptance Criteria:**
- Model trained when ≥ 30 examples available
- Prediction shown on capture workspace
- Model accuracy (AUC-ROC) > 0.65 on validation set
- Graceful degradation when insufficient data
**Dependencies:** Tasks 151, 156, 121, 064
**DB Changes:** New table: `ml_models (id, model_type, model_blob, training_examples, auc_roc, trained_at)`;  `capture_opportunities`: add `ml_pwin REAL`
**API Changes:** None (background computation)
**Frontend Changes:** ML pWin shown alongside manual estimate on workspace
**Testing:** 4 new tests (mock training data, prediction assertions)
**Commit:** `feat: add ML-based win probability model trained on historical capture outcomes`
**Follow-up:** None

---

### Task 271 — Build MASTER_ROADMAP index file
**Epic:** E22 | **Milestone:** M1 | **Complexity:** XS | **Sessions:** 0.5
**Objective:** Create `ai_agent/plans/MASTER_ROADMAP_INDEX.md` — a single-file index
of all roadmap files, task numbers, titles, epics, and milestones. This is the
navigation file for autonomous AI agents and human reviewers.
**Requirements:**
- List every task (056–270) with: number, title, epic, milestone, complexity
- Link to the correct roadmap file (03–07)
- Mark completed tasks as DONE as they are shipped
- Include epic and milestone summary tables
**Acceptance Criteria:**
- Index covers all 214 tasks
- AI agent can find any task in < 5 seconds using this index
- Updated automatically after each task ships (add to HANDOFF.md instructions)
**Dependencies:** All roadmap files complete
**DB Changes:** None | **API Changes:** None | **Frontend Changes:** None
**Testing:** None
**Commit:** `docs: add MASTER_ROADMAP_INDEX.md as navigation file for all 214 tasks`
**Follow-up:** None

---

## CTO REVIEW ADDITIONS — Tasks 272–284
# Source: ai_agent/plans/CTO_REVIEW.md
# Added: 2026-06-20

---

### Task 272 — Add two-factor authentication (TOTP)
**Epic:** E03 | **Milestone:** M2 | **Complexity:** M
**Objective:** Add TOTP-based 2FA (RFC 6238 compatible — Google Authenticator, Authy) as
optional but org-enforceable security layer. The platform stores an org's entire competitive
BD strategy; a compromised account is a catastrophic business risk.
**Requirements:**
- TOTP setup via QR code at `GET /settings/security/2fa/setup`
- 10 one-time recovery codes generated at setup, shown once, hashed and stored
- `POST /settings/security/2fa/verify` — confirm TOTP enrollment
- `POST /settings/security/2fa/disable` — disable with current TOTP code required
- Login flow: after password check, if TOTP enabled → redirect to `/login/2fa` before session creation
- Org admin can enforce 2FA for all members: `organizations.require_2fa BOOLEAN DEFAULT FALSE`
- Members without 2FA enrolled redirected to setup if org enforces it
**Acceptance Criteria:**
- [ ] QR code scannable by standard authenticator apps
- [ ] 10 recovery codes generated, any one works in lieu of TOTP
- [ ] Session not created until TOTP verified
- [ ] Org-wide enforcement redirects unenrolled members to setup
- [ ] All existing tests still pass
**Hard Dependencies:** Task 069
**DB Changes:** `users`: add `totp_secret TEXT`, `totp_enabled BOOLEAN DEFAULT FALSE`, `recovery_codes_json TEXT`; `organizations`: add `require_2fa BOOLEAN DEFAULT FALSE`
**API Changes:** `GET /settings/security/2fa/setup`, `POST /settings/security/2fa/verify`, `POST /settings/security/2fa/disable`, `GET /login/2fa`, `POST /login/2fa`
**Frontend Changes:** Security settings section in settings; TOTP step in login flow
**New Dependencies (requirements.txt):** `pyotp` — TOTP generation and verification
**Suggested Commit Message:** `feat: add TOTP two-factor authentication with org-wide enforcement (Task 272)`

---

### Task 273 — Past performance citation repository
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** Store and manage the org's own past performance references for reuse in
proposals. This is the most-referenced data source in federal proposal writing; storing it
in the platform directly increases daily stickiness.
**Requirements:**
- CRUD at `GET/POST /settings/past-performance` and `GET/POST/DELETE /settings/past-performance/<id>`
- Fields: contract number, agency name, scope summary, period of performance (start/end),
  total value, POC name/phone/email, performance rating (Exceptional/Very Good/Satisfactory/
  Marginal/Unsatisfactory/N/A), NAICS code, notes
- Search by NAICS code and agency name
- Export as formatted CSV and as formatted plain text block (for direct paste into proposals)
- Link citations to proposal sections (Task 159): `proposal_section_citations (section_id, past_perf_id)`
**Acceptance Criteria:**
- [ ] CRUD operations complete without error
- [ ] Search by NAICS and agency returns correct results
- [ ] Export produces properly formatted CSV
- [ ] Citations linkable from proposal section editor
- [ ] All existing tests still pass
**Hard Dependencies:** Task 069
**DB Changes:** New table: `past_performance (id, org_id, contract_num TEXT, agency TEXT, scope TEXT, pop_start TEXT, pop_end TEXT, value REAL, poc_name TEXT, poc_email TEXT, poc_phone TEXT, rating TEXT, naics_code TEXT, notes TEXT, created_at TEXT, updated_at TEXT)`; new table: `proposal_section_citations (section_id INT, past_perf_id INT)`
**API Changes:** `GET/POST /settings/past-performance`, `GET/POST/DELETE /settings/past-performance/<id>`, `GET /settings/past-performance/export.csv`
**Frontend Changes:** `templates/settings/past_performance.html`
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add past performance citation repository with proposal section linking (Task 273)`

---

### Task 274 — Key contact and relationship tracker
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** Track the org's relationships with agency personnel — contracting officers,
program managers, end users — the human relationships that determine who wins contracts.
Fills the gap that GovWin charges thousands per year to partially address.
**Requirements:**
- CRUD at `GET/POST /contacts` and `GET/POST/DELETE /contacts/<id>`
- Fields: name, title, agency, office/division, email, phone, LinkedIn URL,
  relationship strength (1–5 stars), last interaction date, notes
- Link contacts to specific contracts: `contract_contacts (internal_id, contact_id, role TEXT)`
- Link contacts to capture opportunities: `capture_contacts (opp_id, contact_id, role TEXT)`
- Agency profile shows: "You have N contacts at this agency"
- Contract detail shows linked contacts if any
**Acceptance Criteria:**
- [ ] CRUD operations complete without error
- [ ] Contacts linkable to contracts and capture opportunities
- [ ] Agency profile contact count is accurate
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 069, 151
**DB Changes:** New table: `agency_contacts (id, org_id, name TEXT, title TEXT, agency TEXT, office TEXT, email TEXT, phone TEXT, linkedin_url TEXT, relationship_strength INT, last_interaction TEXT, notes TEXT, created_at TEXT)`; new table: `contract_contacts (internal_id TEXT, contact_id INT, role TEXT)`; new table: `capture_contacts (opp_id INT, contact_id INT, role TEXT)`
**API Changes:** `GET/POST /contacts`, `GET/POST/DELETE /contacts/<id>`
**Frontend Changes:** `templates/contacts.html`, contact count on agency profile, contact panel on contract detail
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add key contact and relationship tracker linked to agencies and captures (Task 274)`

---

### Task 275 — Win/loss debrief with automatic outcome prompt
**Epic:** E10 | **Milestone:** M3 | **Complexity:** S
**Objective:** When a capture moves to SUBMITTED and the proposal due date passes, prompt
the capture manager to record WON/LOST outcome. Structured outcome data is required to
train the ML pWin model (Task 270) — without this, the model starves for training data.
**Requirements:**
- Celery daily task: find SUBMITTED captures with `proposal_due_date` ≥ 7 days in the past
  and no debrief recorded → send email + in-app notification: "Did you win [contract name]?"
- `GET /capture/<opp_id>/debrief` — debrief form
- `POST /capture/<opp_id>/debrief` — submit debrief
- Debrief fields: outcome (WON / LOST / NO_BID / CANCELLED), award amount (if WON),
  winning vendor (if LOST), loss reason (price / technical / past_performance / relationships / other),
  customer feedback notes, would_bid_again (BOOLEAN)
- Debrief stored in `capture_debriefs` table
- Capture pipeline view shows debrief status indicator
**Acceptance Criteria:**
- [ ] Celery daily task fires without error
- [ ] Email notification sent to capture owner after proposal_due_date + 7 days
- [ ] Debrief form saves all fields correctly
- [ ] Debrief visible on capture workspace summary
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 151, 127, 169
**DB Changes:** New table: `capture_debriefs (id, opp_id INT UNIQUE, outcome TEXT, award_amount REAL, winning_vendor TEXT, loss_reason TEXT, feedback_notes TEXT, would_bid_again BOOLEAN, recorded_by INT, recorded_at TEXT)`
**API Changes:** `GET/POST /capture/<opp_id>/debrief`
**Frontend Changes:** Debrief link on capture workspace; debrief status chip in pipeline view
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add win/loss debrief with automatic outcome prompt after proposal due date (Task 275)`

---

### Task 276 — RFP document download and AI parsing
**Epic:** E11 | **Milestone:** M4 | **Complexity:** XL
**Objective:** When a solicitation is linked (Task 104), automatically download the
solicitation package from SAM.gov and use Claude to extract evaluation criteria, page
limits, key dates, and requirements. Pre-populate the compliance matrix (Task 160)
from extracted L-sections. This is the highest-value AI application in the proposal workflow.
**Requirements:**
- Celery task triggered on solicitation link: download SAM.gov attachment (PDF/DOCX/ZIP)
- Store raw document bytes in object storage (Task 280)
- Claude extraction prompt: identify L-sections (instructions to offerors), M-sections
  (evaluation criteria), page limits per volume, proposal due date, set-aside type,
  key personnel requirements, oral presentation requirements if any
- Store structured extraction in `solicitation_extracts` table as JSON
- Display extracted summary on contract detail page
- `POST /solicitation/<solnum>/parse` — re-trigger parsing (manual refresh)
- Pre-populate compliance matrix rows from extracted L-requirements (Task 160)
**Acceptance Criteria:**
- [ ] PDF download completes without timeout for typical SAM.gov solicitation (<50MB)
- [ ] Claude extraction returns valid JSON with all required fields
- [ ] Compliance matrix pre-populated from L-section extraction
- [ ] Extraction visible on contract detail within 60 seconds of solicitation link
- [ ] Graceful fallback if SAM.gov attachment unavailable
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 104, 159, 160, 280
**DB Changes:** New table: `solicitation_extracts (solnum TEXT PK, extracted_json TEXT, raw_storage_key TEXT, model_version TEXT, extracted_at TEXT, status TEXT)`
**API Changes:** `POST /solicitation/<solnum>/parse`, `GET /solicitation/<solnum>/extract`
**Frontend Changes:** Extraction summary card on contract detail; pre-fill on compliance matrix
**New Dependencies (requirements.txt):** `pypdf2` or `python-docx` — document text extraction
**Suggested Commit Message:** `feat: add AI RFP document parsing with automatic compliance matrix pre-population (Task 276)`

---

### Task 277 — Set-aside eligibility check on contract detail
**Epic:** E05 | **Milestone:** M2 | **Complexity:** S
**Objective:** Compute and display whether the org is eligible for a contract's set-aside
type using the org's SAM certifications (Task 081). Prevents wasted BD effort on
ineligible set-asides and is the most obvious filtering use of org profile data.
**Requirements:**
- `check_set_aside_eligibility(org_id, set_aside_type)` function in a new `eligibility.py` module
- Returns: `ELIGIBLE` / `INELIGIBLE` / `NOT_CERTIFIED` (no data on file) / `OPEN` (no set-aside)
- Set-aside to certification mapping:
  - 8(a) → `8a_certified`
  - SDVOSB → `sdvosb_certified`
  - WOSB → `wosb_certified`
  - HUBZone → `hubzone_certified`
  - SB → `small_business` (size standard check vs. NAICS code)
  - VOSB → `vosb_certified`
- Display on contract detail as a color-coded badge: green (ELIGIBLE), red (INELIGIBLE), grey (OPEN/NOT_CERTIFIED)
- `GET /contracts?eligible_only=true` filter: show only ELIGIBLE or OPEN contracts
**Acceptance Criteria:**
- [ ] Eligibility badge appears on contract detail for all set-aside types
- [ ] `eligible_only=true` filter reduces contract list to eligible contracts
- [ ] NOT_CERTIFIED shown when org has no certification data (not INELIGIBLE)
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 081, 103
**DB Changes:** None (reads `org_certifications` and `contracts` tables)
**API Changes:** `eligible_only` query param added to `GET /contracts`
**Frontend Changes:** Eligibility badge on contract detail; filter option on contract list
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add set-aside eligibility check using org SAM certifications (Task 277)`

---

### Task 278 — In-app bid calendar
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M
**Objective:** Unified in-app calendar view showing proposal due dates, capture milestone
dates, contract expiration alert thresholds, and scheduled exports across all active
captures. Capture managers live by their calendar; this feature drives daily return visits.
**Requirements:**
- `GET /calendar` — month/week toggle (default: month)
- Events sourced from: `capture_milestones` (Task 154), `capture_opportunities.proposal_due_date`,
  contract expiration alert thresholds (Task 128), `org_scheduled_exports` (Task 264)
- Click on any event → navigate to the relevant capture, contract, or settings page
- Color coding by event type: green (milestone), orange (proposal due), red (expiration), blue (export)
- `GET /calendar.ics` — iCal feed for the full org calendar (all event types, not just per-capture)
- Week view shows events by day with time (for due dates/times that have them)
**Acceptance Criteria:**
- [ ] Calendar renders all event types in correct date positions
- [ ] Click navigation works for all event types
- [ ] iCal feed downloadable and valid RFC 5545
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 154, 128
**DB Changes:** None (derived from existing tables)
**API Changes:** `GET /calendar`, `GET /calendar.ics`
**Frontend Changes:** `templates/calendar.html`; link in main navigation
**New Dependencies (requirements.txt):** `icalendar` — iCal feed generation
**Suggested Commit Message:** `feat: add in-app bid calendar with milestone and expiration view (Task 278)`

---

### Task 279 — Database backup automation and verification
**Epic:** E18 | **Milestone:** M2 | **Complexity:** M
**Objective:** Ensure daily automated backups with verified restore capability. A failed
migration or accidental bulk delete without backup verification is existential for a B2B
SaaS with paying customers. Implement alongside Task 062 (same sprint).
**Requirements:**
- Enable Railway PostgreSQL point-in-time recovery and daily snapshot configuration
- Celery weekly task `verify_backup_integrity()`:
  - Trigger restore to a test schema (`backup_verify` schema within same PG instance)
  - Run `SELECT COUNT(*) FROM contracts`, `users`, `organizations` in restore schema
  - Assert row counts match production (±0)
  - Alert via Sentry + admin email if mismatch
  - Drop test schema after verification
- `GET /health/deep` (Task 220) response includes `last_backup_verified_at` timestamp
- Create `docs/RESTORE.md` with step-by-step restore procedure
**Acceptance Criteria:**
- [ ] Weekly verification task runs without error
- [ ] Health endpoint reports backup status
- [ ] Mismatch triggers Sentry alert and admin email
- [ ] RESTORE.md documents step-by-step procedure
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 062, 220
**DB Changes:** None
**API Changes:** `last_backup_verified_at` added to `GET /health/deep` response
**Frontend Changes:** None
**New Dependencies (requirements.txt):** None (uses existing Celery, Sentry, email)
**Suggested Commit Message:** `feat: add database backup verification job and restore documentation (Task 279)`

---

### Task 280 — Object storage for generated files
**Epic:** E17 | **Milestone:** M3 | **Complexity:** M
**Objective:** Store generated PDFs, data export ZIPs, and scheduled exports in
S3-compatible object storage instead of the ephemeral Railway filesystem. Without this,
large generated files are lost on redeploy and memory-constrained exports will fail.
**Requirements:**
- Add `boto3` to requirements
- Environment vars: `OBJECT_STORAGE_URL`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_KEY`, `OBJECT_STORAGE_SECRET`
- Create `storage_service.py`:
  - `upload(key: str, data: bytes, content_type: str) -> str` — returns public or signed URL
  - `get_presigned_url(key: str, expires_in: int = 3600) -> str`
  - `delete(key: str) -> None`
- Replace filesystem writes in Tasks 209 (PDF), 254 (data export), 264 (scheduled export) with `storage_service.upload()`
- In local dev without object storage configured: fall back to `/tmp` with a logged warning
- Railway provides Cloudflare R2 as S3-compatible storage (preferred)
**Acceptance Criteria:**
- [ ] `storage_service.py` tests pass (mock boto3)
- [ ] PDF export (Task 209) uses object storage in production
- [ ] Data export (Task 254) uses object storage in production
- [ ] Local dev falls back gracefully without `OBJECT_STORAGE_URL` set
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 064, 209, 254
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** None (transparent to end user)
**New Dependencies (requirements.txt):** `boto3` — S3-compatible object storage client
**Suggested Commit Message:** `feat: add S3-compatible object storage for generated exports and PDF reports (Task 280)`

---

### Task 281 — Celery beat health monitoring
**Epic:** E18 | **Milestone:** M2 | **Complexity:** S
**Objective:** Detect and alert when Celery beat stops scheduling tasks, preventing silent
failure of nightly scans, alert delivery, and daily briefings. Implement alongside Task 064
(same sprint — set up beat, immediately add health monitoring).
**Requirements:**
- Register heartbeat task in beat schedule: `record_beat_heartbeat` every 5 minutes
- `record_beat_heartbeat()` Celery task: write `{timestamp}` to `beat:health` Redis key with 15-min TTL
- `check_beat_health()` Celery task (scheduled every 10 min):
  - Read `beat:health` key — if missing or timestamp > 15 min old: fire Sentry alert + send email to platform admin list
  - If healthy: no action
- `GET /health/deep` (Task 220) checks `beat:health` key and includes `celery_beat_healthy: true/false`
**Acceptance Criteria:**
- [ ] `record_beat_heartbeat` runs every 5 min when beat is healthy
- [ ] `/health/deep` reports beat status
- [ ] Sentry alert fires when beat key is missing for > 15 minutes
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 064, 219, 220
**DB Changes:** None (Redis key only)
**API Changes:** `celery_beat_healthy` field added to `GET /health/deep` response
**Frontend Changes:** None
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add Celery beat health monitoring with alert on scheduler failure (Task 281)`

---

### Task 282 — Cross-org opportunity signal aggregation
**Epic:** E09 | **Milestone:** M4 | **Complexity:** L
**Objective:** Aggregate anonymous behavioral signals across opted-in orgs to surface
"market heat" — how many orgs are tracking a contract, how many have it in their pipeline.
This data is unavailable from any competitor and grows more valuable as the platform scales.
It is the platform's largest network-effect moat opportunity.
**Requirements:**
- Opt-in at org level: `org.share_signals BOOLEAN DEFAULT FALSE`, toggled by admin in settings
- When opted-in org watchlists (Task 107) or captures (Task 151) a contract: increment anonymous counter
- `contract_signals` table: `internal_id TEXT PK, track_count INT DEFAULT 0, capture_count INT DEFAULT 0, last_updated TEXT`
- Display on contract detail: "Tracked by N organizations" — no org names or identifying info revealed
- `GET /contracts?signal_heat=high` filter: show contracts with track_count ≥ 5
- Dashboard widget: "Trending this week — N orgs newly tracking NAICS 561720"
- Gated on Professional+ plan (Task 202)
**Acceptance Criteria:**
- [ ] Opt-in toggle works; non-opted-in org actions do not increment counters
- [ ] Contract detail shows tracking count for opted-in data
- [ ] `signal_heat=high` filter returns correct contracts
- [ ] Dashboard widget shows NAICS trends
- [ ] No org identity revealed in any signal
- [ ] Gated correctly by plan tier
- [ ] All existing tests still pass
**Hard Dependencies:** Tasks 069, 107, 151, 202
**DB Changes:** `organizations`: add `share_signals BOOLEAN DEFAULT FALSE`; new table: `contract_signals (internal_id TEXT PK, track_count INT DEFAULT 0, capture_count INT DEFAULT 0, last_updated TEXT)`
**API Changes:** `signal_heat` filter param on `GET /contracts`
**Frontend Changes:** Signal count badge on contract detail; trending widget on dashboard
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add cross-org opportunity signal aggregation with opt-in privacy model (Task 282)`

---

### Task 283 — AI prompt registry with version tracking
**Epic:** E12 | **Milestone:** M3 | **Complexity:** M
**Objective:** Centralize all Anthropic prompts in a versioned registry. Currently, prompts
are implied to be hardcoded in service files. As prompt count grows (8+ tasks generate AI
content), managing prompt quality becomes a competitive advantage. Implement after Task 102
establishes `ai_service.py`.
**Requirements:**
- `ai_prompts` table: `name TEXT PK`, `version INT`, `system_prompt TEXT`, `user_prompt_template TEXT`,
  `model_preference TEXT`, `max_tokens INT`, `active BOOLEAN DEFAULT TRUE`
- `ai_prompt_history` table: logs prior versions on update
- `ai_service.py` updated: `call(prompt_name, context_vars, override_model=None)` — loads prompt by name
- All existing AI calls (Tasks 102, 120, 160–168) updated to reference prompt by name
- `GET /admin/prompts` (admin role only) — list all active prompts and version history
- `POST /admin/prompts/<name>` — update prompt text (creates history record, bumps version)
**Acceptance Criteria:**
- [ ] All AI calls reference a prompt name, not a hardcoded string
- [ ] Admin prompt editor loads, displays, and saves without error
- [ ] Prior prompt version retained in history table on update
- [ ] All existing AI feature tests still pass (update mocks to use registry)
- [ ] All existing tests still pass
**Hard Dependencies:** Task 102
**DB Changes:** New table: `ai_prompts`; new table: `ai_prompt_history`
**API Changes:** `GET /admin/prompts`, `POST /admin/prompts/<name>`
**Frontend Changes:** `templates/admin/prompts.html`
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add AI prompt registry with versioning and admin management UI (Task 283)`

---

### Task 284 — User feedback on AI-generated content
**Epic:** E12 | **Milestone:** M3 | **Complexity:** S
**Objective:** Collect explicit thumbs-up/thumbs-down feedback on every AI-generated output.
Without this signal, there is no way to know whether AI outputs are helping customers win
contracts. Feedback data drives prompt improvement and is a source of proprietary quality
signal competitors cannot replicate.
**Requirements:**
- After any AI-generated content displayed (capture plan, opportunity analysis, win themes,
  competitor research, agency brief): show a discreet 👍/👎 widget below the content
- `POST /ai-feedback` — `{analysis_id, rating (1/-1), comment (optional), user_id, org_id}`
- Store in `ai_feedback` table
- Weekly Celery task `aggregate_ai_quality()`: compute rating distribution by prompt name + version
  from `ai_prompt_history`; store summary in `ai_quality_snapshots` table
- `GET /admin/ai-quality` (admin only) — dashboard: rating % per prompt, trend over last 4 weeks
**Acceptance Criteria:**
- [ ] 👍/👎 widget visible under all AI-generated content blocks
- [ ] Feedback stores correctly in DB with user and org context
- [ ] Admin quality dashboard loads and shows rating distribution
- [ ] Weekly aggregation task runs without error
- [ ] All existing tests still pass
**Hard Dependencies:** Task 102 (`ai_analyses` table), Task 169 (notification pattern reference)
**DB Changes:** New table: `ai_feedback (id, analysis_id INT, rating INT, comment TEXT, user_id INT, org_id INT, created_at TEXT)`; new table: `ai_quality_snapshots (id, prompt_name TEXT, prompt_version INT, week TEXT, positive_count INT, negative_count INT, total_count INT)`
**API Changes:** `POST /ai-feedback`, `GET /admin/ai-quality`
**Frontend Changes:** Feedback widget component in base AI content template; `templates/admin/ai_quality.html`
**New Dependencies (requirements.txt):** None
**Suggested Commit Message:** `feat: add thumbs up/down feedback on AI outputs with admin quality dashboard (Task 284)`
