# MASTER ROADMAP — 04: Tasks 101–150
# Epics: E05 (Company Intel, cont.), E06 (Contract Intelligence),
#         E07 (Vendor Intelligence), E08 (Agency Intelligence),
#         E09 (Opportunity Intelligence), E13 (Notifications, partial)

---

## EPIC E05 — Company Intelligence (continued)

---

### Task 101 — Build business DNA profile from contract history
**Epic:** E05 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** When org is linked to a SAM entity, analyze historical contract awards
to generate a "business DNA" — the org's primary service categories, agency relationships,
and competitive strengths.
**Requirements:**
- Create `business_profile_service.py` with `compute_business_dna(org_id)` function
- Query USAspending or local contracts table for vendor's historical awards
- Aggregate: top 5 agencies by award value, top 5 NAICS codes by award count,
  average contract size, largest single award, win count by year
- Store result as `organizations.business_dna_json`
- Display on `/settings/company` as "Your Business Profile"
**Acceptance Criteria:**
- Business DNA computed from at least vendor name match in local contracts table
- Dashboard shows top agency and contract category for the org
- Profile refreshed weekly (Celery beat task)
**Dependencies:** Tasks 062, 080
**DB Changes:** `organizations`: add `business_dna_json TEXT`, `dna_computed_at TEXT`
**API Changes:** None
**Frontend Changes:** Business profile card on `/settings/company`
**Testing:** 4 new tests (mock contract data, verify aggregation)
**Commit:** `feat: add business DNA profile computed from historical contract history`
**Follow-up:** Task 102 (AI enrichment of business profile)

---

### Task 102 — AI enrichment of company profile
**Epic:** E05 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Use Claude to analyze the business DNA and produce a plain-English
company summary, competitive positioning, and recommended NAICS focus areas.
**Requirements:**
- Celery task `enrich_company_profile(org_id)` — calls Claude with business_dna_json
- Prompt: "Given this federal contractor's award history, describe their core capabilities,
  primary agency relationships, competitive positioning, and top 3 recommended NAICS codes
  to pursue for recompete opportunities."
- Store result in `ai_analyses` table (entity_type='org', analysis_type='company_summary')
- Display on company profile page under "AI Analysis"
- Refresh monthly or on user request
**Acceptance Criteria:**
- AI summary generated for org with ≥ 3 historical contracts
- Plain-English summary displayed on company profile
- User can regenerate on demand
- Graceful handling if Anthropic API unavailable
**Dependencies:** Task 101, Anthropic SDK (already in requirements)
**DB Changes:** New table: `ai_analyses (id, entity_type, entity_id, org_id, analysis_type, result_text, model_version, created_at, tokens_used)`
**API Changes:** `POST /company/regenerate-analysis` (triggers Celery task)
**Frontend Changes:** AI summary card on company profile
**Testing:** 4 new tests (mock Claude response)
**Commit:** `feat: add AI company profile enrichment using Claude`
**Follow-up:** Task 163 (AI capture plan generation)

---

## EPIC E06 — Contract Intelligence

---

### Task 103 — Add NAICS code and PSC code to contract detail
**Epic:** E06 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Ingest and display NAICS code and PSC (Product Service Code) for each contract.
**Requirements:**
- Parse `naics_code` and `psc_code` from CSV and SAM.gov API response in `recompete_report.py`
- Store in `contracts` table (columns added in Task 083)
- Display on contract detail page: "NAICS: 561720 — Janitorial Services", "PSC: S208"
- Add `naics_code` and `psc_code` filter to `/contracts` route
**Acceptance Criteria:**
- New contract imports populate naics_code and psc_code
- Contract detail page shows NAICS and PSC with human-readable labels
- `/contracts?naics=561720` filters correctly
**Dependencies:** Task 083 (columns already added)
**DB Changes:** None (columns added in 083); add NAICS lookup table `naics_codes (code, title, sector)`
**API Changes:** `/contracts` accepts `naics` and `psc` query params
**Frontend Changes:** Contract detail template, contracts list filter panel
**Testing:** 3 new tests
**Commit:** `feat: add NAICS and PSC code ingestion, filtering, and display`
**Follow-up:** Task 104 (solicitation linking)

---

### Task 104 — Link expiring contracts to open SAM.gov solicitations
**Epic:** E06 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** When a contract is approaching expiration, search SAM.gov for open
solicitations with matching agency, NAICS, or solicitation number.
**Requirements:**
- Celery task `find_related_solicitations(internal_id)` — calls SAM.gov opportunities API
- Search by: solicitation_id, agency + NAICS code, related award number
- Store matches in `contract_solicitations` table
- Contract detail page: "Open Solicitation Found" card with SAM.gov link
- Badge on contract list rows where solicitation is found
**Acceptance Criteria:**
- Matching solicitation shown on contract detail within 30 seconds of background task
- Badge visible on contracts list for matched contracts
- No false positives on unrelated solicitations
**Dependencies:** Tasks 062, 065, sam_lookup.py (existing)
**DB Changes:** New table: `contract_solicitations (id, internal_id, solicitation_num, title, posted_date, response_deadline, sam_url, matched_at)`
**API Changes:** `GET /contract/<id>/solicitations`
**Frontend Changes:** Solicitation card on contract_detail.html; badge on contracts.html
**Testing:** 5 new tests (mock SAM API)
**Commit:** `feat: link expiring contracts to open SAM.gov solicitations`
**Follow-up:** Task 105 (option exercise tracking)

---

### Task 105 — Track contract option exercise history
**Epic:** E06 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Parse FPDS modification history to detect option exercises. Show "Base + 3 Options,
Option 3 currently active" on contract detail.
**Requirements:**
- Create `fpds_service.py` with `get_contract_modifications(piid)` function
- Call FPDS API or USAspending `/api/v2/awards/` endpoint
- Parse modification records: identify option exercises vs. other mods
- Store in `contract_modifications` table
- Contract detail: option period breakdown card ("Option 2 of 4, exercised 2024-01-15")
**Acceptance Criteria:**
- Option exercise history shown for contracts with award_id match in FPDS
- "No modification history available" shown gracefully when FPDS has no record
- Incumbent tenure (years vendor has held contract) computed and displayed
**Dependencies:** Task 062
**DB Changes:** New table: `contract_modifications (id, internal_id, piid, mod_number, mod_type, effective_date, value, description)`
**API Changes:** `GET /contract/<id>/modifications`
**Frontend Changes:** Modification history card on contract_detail.html
**Testing:** 4 new tests (mock FPDS responses)
**Commit:** `feat: add FPDS modification and option exercise history to contract detail`
**Follow-up:** Task 107 (incumbent tenure in scoring)

---

### Task 106 — Add contract notes (inline annotations)
**Epic:** E06 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow capture team members to annotate contracts with notes visible to all org members.
**Requirements:**
- `POST /contract/<id>/notes` — add note (body, user_id, org_id, created_at)
- `GET /contract/<id>/notes` — return JSON list of notes (HTMX target)
- `DELETE /contract/<id>/notes/<note_id>` — note owner or admin can delete
- Notes display on contract detail page below main info
- Max 5,000 chars per note
**Acceptance Criteria:**
- Notes visible to all org members immediately after posting
- Note author name and timestamp shown
- Note deletion requires ownership or admin role
- Viewer role cannot post notes
**Dependencies:** Tasks 062, 069, 071
**DB Changes:** New table: `contract_notes (id, org_id, internal_id, user_id, body, created_at, updated_at)`
**API Changes:** `POST/GET /contract/<id>/notes`, `DELETE /contract/<id>/notes/<nid>`
**Frontend Changes:** Notes panel on contract_detail.html (HTMX partial)
**Testing:** 6 new tests
**Commit:** `feat: add org-scoped contract notes with HTMX inline posting`
**Follow-up:** Task 143 (capture workspace notes)

---

### Task 107 — Add watchlist (bookmark contracts)
**Epic:** E06 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow users to bookmark contracts to a named watchlist for tracking.
**Business Value:** Enables "pipeline" concept — contracts the team is actively watching.
**Requirements:**
- `POST /contract/<id>/watch` — add to user's default watchlist
- `DELETE /contract/<id>/watch` — remove from watchlist
- `GET /watchlist` — show all watched contracts (org-scoped)
- Multiple named watchlists: `POST /watchlist/new`, `GET /watchlist/<wid>`
- Watch/unwatch button on contract detail and contract list rows
- Watchlist count badge in nav
**Acceptance Criteria:**
- Contract appears in watchlist immediately after watching
- Unwatch removes immediately
- Watchlist page sortable by priority, value, expiration
- Org-scoped: all members see shared watchlists
**Dependencies:** Tasks 062, 069
**DB Changes:** New tables: `watchlists (id, org_id, name, created_by, created_at)`, `watchlist_contracts (watchlist_id, internal_id, added_by, added_at)`
**API Changes:** `POST/DELETE /contract/<id>/watch`, `GET/POST /watchlist`, `GET /watchlist/<id>`
**Frontend Changes:** Watch buttons, `templates/watchlist.html`
**Testing:** 7 new tests
**Commit:** `feat: add contract watchlist with org-shared named lists`
**Follow-up:** Task 176 (email alerts for watched contracts)

---

### Task 108 — Add saved searches
**Epic:** E06 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow users to save a named filter configuration and recall it from the
sidebar or header.
**Requirements:**
- `POST /searches/save` — save current filters as named search (name, org_id, user_id, filters_json)
- `GET /searches` — list saved searches for org
- `DELETE /searches/<id>` — delete saved search
- "Save Search" button on `/contracts` filter bar
- Saved searches appear in nav sidebar (top 5)
- Clicking applies all filters and re-runs the search
**Acceptance Criteria:**
- Saved search restores exact filter state on click
- Org members can see and use each other's saved searches
- Saved searches accessible within 1 click from anywhere in app
**Dependencies:** Tasks 062, 069
**DB Changes:** New table: `saved_searches (id, org_id, user_id, name, filters_json, created_at, last_used_at)`
**API Changes:** `GET/POST /searches`, `DELETE /searches/<id>`
**Frontend Changes:** "Save Search" button on contracts.html, sidebar search list
**Testing:** 5 new tests
**Commit:** `feat: add named saved searches with org-shared access`
**Follow-up:** Task 178 (email alerts on saved search changes)

---

### Task 109 — Add CSV export from contract list
**Epic:** E06 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Export the current filtered contract view as a CSV file.
**Requirements:**
- `GET /contracts/export.csv` — applies same filters as `/contracts` view, returns CSV
- Columns: internal_id, award_id, vendor, agency, value, start_date, end_date,
  days_remaining, priority, recompete_score, naics_code, psc_code
- Filename: `recompete-export-YYYY-MM-DD.csv`
- Limited to 1,000 rows per export; show warning if result exceeds limit
**Acceptance Criteria:**
- Download triggers with correct MIME type (`text/csv`)
- All active filters applied to export
- Export button visible on contracts list page
**Dependencies:** Task 062
**DB Changes:** None
**API Changes:** `GET /contracts/export.csv`
**Frontend Changes:** Export button on contracts.html
**Testing:** 2 new tests
**Commit:** `feat: add CSV export from filtered contract list`
**Follow-up:** Task 216 (PDF export)

---

### Task 110 — Add "pipeline" view (contracts actively pursuing)
**Epic:** E06 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** A dedicated view showing all contracts the org has marked as "pursuing."
Distinct from watchlist — pipeline = active capture intent.
**Requirements:**
- `pursuit_status` column on `watchlist_contracts` or new `org_pursuits` table
- `POST /contract/<id>/pursue` sets pursuit status to one of: TRACKING, QUALIFYING, PURSUING, PROPOSING
- `GET /pipeline` — kanban-style list grouped by pursuit status
- Remove from pipeline: `DELETE /contract/<id>/pursue`
**Acceptance Criteria:**
- Pipeline page shows all contracts grouped by status
- Status transitions work without page reload (HTMX)
- Pursuit count shown in nav badge
**Dependencies:** Task 107 (watchlist)
**DB Changes:** New table: `org_pursuits (id, org_id, internal_id, status, owner_id, updated_at)`
**API Changes:** `POST/DELETE /contract/<id>/pursue`, `GET /pipeline`
**Frontend Changes:** `templates/pipeline.html` with HTMX status updates
**Testing:** 5 new tests
**Commit:** `feat: add capture pipeline view with pursuit status tracking`
**Follow-up:** Task 134 (full capture workspace)

---

## EPIC E07 — Vendor Intelligence (Enhanced)

---

### Task 111 — Compute vendor win rate from historical data
**Epic:** E07 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** For each vendor, compute the re-win rate: when their contracts expire, how
often do they appear as the vendor on the successor contract?
**Requirements:**
- Create `vendor_analytics_service.py` with `compute_win_rate(vendor_name)` function
- Compare contracts where vendor appeared on initial award vs. post-recompete
- Use contract modification and snapshot history
- Store in `vendor_stats` table: `win_rate REAL, tenure_avg_years REAL, contracts_tracked INT`
- Display on vendor profile page: "Win Rate: 73% (8 of 11 tracked recompetes)"
**Acceptance Criteria:**
- Win rate displayed on vendor profile when ≥ 3 historical contracts tracked
- "Insufficient history" shown gracefully for new vendors
- Refreshed weekly via Celery
**Dependencies:** Task 062, Task 105 (modification history)
**DB Changes:** New table: `vendor_stats (vendor TEXT PK, win_rate REAL, tenure_avg_years REAL, contracts_tracked INT, computed_at TEXT)`
**API Changes:** None
**Frontend Changes:** Win rate card on `templates/vendor.html`
**Testing:** 4 new tests
**Commit:** `feat: compute and display vendor win rate from historical contract data`
**Follow-up:** Task 112 (incumbent tenure in scoring)

---

### Task 112 — Add incumbent tenure to recompete scoring
**Epic:** E07 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Factor vendor tenure length into the recompete score. Longer incumbency
= higher probability of recompete (agency wants change) or lower (incumbent entrenched).
**Requirements:**
- Update `recompete_score` computation in `recompete_report.py` to include:
  - `tenure_score`: 0–20 pts based on years vendor has held contract
  - `win_rate_inverse`: 0–10 pts: lower win rate → incumbent more vulnerable
- Store `tenure_years` in contracts table
- Recalculate scores on next ingest
**Acceptance Criteria:**
- Contracts with 5+ year incumbents score 10–20 pts higher
- Score breakdown visible on contract detail ("Tenure: +15 pts")
- No contracts lose existing score categories (additive only)
**Dependencies:** Task 111, Task 105
**DB Changes:** `contracts`: add `tenure_years REAL`, `score_breakdown_json TEXT`
**API Changes:** None
**Frontend Changes:** Score breakdown section on contract_detail.html
**Testing:** 4 new tests
**Commit:** `feat: add incumbent tenure factor to recompete scoring algorithm`
**Follow-up:** Task 123 (full scoring engine)

---

### Task 113 — Add vendor competitive set analysis
**Epic:** E07 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Show which vendors compete in the same NAICS/agency space as a given vendor.
**Requirements:**
- `competitive_set(vendor_name, naics_code, agency)` query: find all vendors with contracts
  in same NAICS and agency, ordered by contract value
- Displayed on vendor profile: "Competitors in NAICS 561720 at DHS" list with values
- Link to `/vendor/<name>` for each competitor
**Acceptance Criteria:**
- Competitive set shown on vendor profile for vendors with ≥ 2 contracts
- List limited to top 10 competitors
- Competitor's total value in the same space shown
**Dependencies:** Task 062
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** Competitive set section on vendor.html
**Testing:** 3 new tests
**Commit:** `feat: add vendor competitive set analysis by NAICS and agency`
**Follow-up:** Task 168 (AI competitor research)

---

### Task 114 — Add vendor comparison (two vendors side by side)
**Epic:** E07 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Extend the existing contract comparison page to support vendor comparison.
**Requirements:**
- `GET /compare/vendors?a=<vendor_a>&b=<vendor_b>` — side-by-side vendor stats
- Compare: contract count, total value, agency distribution, NAICS codes, win rate,
  avg contract size, certifications (if SAM entity linked)
- "Compare" button on vendor profile page (links to comparison)
**Acceptance Criteria:**
- Side-by-side comparison renders for any two vendors in the database
- Visual indicator of which vendor "wins" each metric
**Dependencies:** Task 062
**DB Changes:** None
**API Changes:** `GET /compare/vendors`
**Frontend Changes:** `templates/compare_vendors.html`
**Testing:** 3 new tests
**Commit:** `feat: add vendor comparison page for side-by-side analytics`
**Follow-up:** Task 115

---

### Task 115 — Add teaming partner suggestions
**Epic:** E07 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** For a given opportunity, suggest potential teaming partners based on
complementary NAICS codes, certifications, and agency relationships.
**Requirements:**
- `suggest_teaming_partners(internal_id, org_id)` — for a contract, find vendors with:
  - Complementary NAICS codes (not competing head-to-head)
  - Set-aside certifications matching contract set-aside type
  - History with the contracting agency
- Display top 5 suggestions with rationale on contract detail
- Link to `/vendor/<name>` and `/company/<uei>` where available
**Acceptance Criteria:**
- Suggestions shown on contract detail for contracts with set-aside type
- Each suggestion includes a one-line rationale
- "No suggestions available" shown gracefully when data insufficient
**Dependencies:** Tasks 079, 113
**DB Changes:** None
**API Changes:** `GET /contract/<id>/teaming-suggestions`
**Frontend Changes:** Teaming suggestions card on contract_detail.html
**Testing:** 4 new tests (mock vendor data)
**Commit:** `feat: add teaming partner suggestions on contract detail`
**Follow-up:** Task 144 (teaming partners in capture workspace)

---

## EPIC E08 — Agency Intelligence (Enhanced)

---

### Task 116 — Add agency budget trend analysis
**Epic:** E08 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Show year-over-year contract award trends for each agency from historical data.
**Requirements:**
- `agency_budget_trends(agency, years=5)` query: group contracts by year, sum values
- Display on agency profile: bar chart data (JSON for frontend rendering)
- Include YoY growth percentage
- Data sourced from local contracts database + USAspending historical
**Acceptance Criteria:**
- Agency profile shows 5-year spend trend where data available
- YoY growth (+12% in 2025) displayed prominently
- "Limited historical data" shown gracefully for newer agencies in DB
**Dependencies:** Task 062
**DB Changes:** None (derived from existing data + contract_snapshots)
**API Changes:** `GET /agency/<name>/trends` returns JSON
**Frontend Changes:** Trend chart on agency.html (Chart.js via CDN)
**Testing:** 3 new tests
**Commit:** `feat: add agency budget trend analysis with year-over-year view`
**Follow-up:** Task 117 (NAICS concentration)

---

### Task 117 — Add agency NAICS concentration heatmap
**Epic:** E08 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Show which NAICS codes account for the majority of an agency's spend.
**Requirements:**
- `agency_naics_concentration(agency)`: group by NAICS, sum value, compute % of total
- Display: ranked list of NAICS codes with percentage bars
- Click NAICS → filter contracts to agency + NAICS
**Acceptance Criteria:**
- Top 10 NAICS codes shown with spend percentage
- Click navigates to `/contracts?agency=<name>&naics=<code>`
**Dependencies:** Task 103 (NAICS codes on contracts)
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** NAICS concentration section on agency.html
**Testing:** 2 new tests
**Commit:** `feat: add NAICS concentration analysis to agency profile`
**Follow-up:** Task 118 (agency spend forecast)

---

### Task 118 — Add agency spend forecast (next 12 months)
**Epic:** E08 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Forecast how much an agency is likely to award in the next 12 months
based on historical trends and upcoming contract expirations.
**Requirements:**
- `agency_spend_forecast(agency)`: sum value of contracts expiring in next 12 months
  (proxy for re-award volume) + historical average new awards
- Show as "$X.XM forecast contract activity in next 12 months"
- Breakdown by quarter
**Acceptance Criteria:**
- Forecast shown on agency profile
- Quarterly breakdown accurate to within 10% of manually calculated value
- "Low confidence" label when < 5 contracts in the forecast window
**Dependencies:** Tasks 116, 117
**DB Changes:** None
**API Changes:** `GET /agency/<name>/forecast` returns JSON
**Frontend Changes:** Forecast card on agency.html
**Testing:** 3 new tests
**Commit:** `feat: add 12-month spend forecast to agency intelligence profile`
**Follow-up:** Task 119 (agency opportunity heatmap)

---

### Task 119 — Add opportunity heatmap (agencies × NAICS)
**Epic:** E08 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** A dedicated heatmap page showing expiring contract volume across
agencies (rows) × NAICS codes (columns), filterable by days_remaining window.
**Requirements:**
- `GET /heatmap` route: query for contracts expiring in next 180 days
- Group by agency × NAICS, count contracts and sum value
- Render as HTML table with value-intensity color coding
- Filter: days window (30/60/90/180), min value, NAICS sector
- Link cells to `/contracts?agency=<x>&naics=<y>&days=<d>`
**Acceptance Criteria:**
- Heatmap loads in < 3 seconds for typical dataset
- Color intensity proportional to contract value
- Empty cells shown clearly (no data)
**Dependencies:** Task 117
**DB Changes:** None
**API Changes:** `GET /heatmap`
**Frontend Changes:** `templates/heatmap.html`
**Testing:** 3 new tests
**Commit:** `feat: add agency × NAICS opportunity heatmap with expiration filter`
**Follow-up:** Task 120 (AI agency brief)

---

### Task 120 — Add AI agency intelligence brief
**Epic:** E08 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Generate a plain-English agency brief using Claude: spending patterns,
key vendors, top NAICS categories, open solicitations, and opportunity outlook.
**Requirements:**
- Celery task `generate_agency_brief(agency_name, org_id)` calls Claude
- Input: agency analytics JSON from existing queries
- Output: 3–5 paragraph narrative brief
- Store in `ai_analyses` table
- Display on agency profile: "AI Brief" collapsible section
- Regenerate on user request
**Acceptance Criteria:**
- Brief generated within 30 seconds of request
- Narrative is accurate to the analytics data in the prompt
- "Refresh" button visible to org members with admin+
**Dependencies:** Task 102 (ai_analyses table), Task 118, Task 119
**DB Changes:** None (reuses ai_analyses)
**API Changes:** `POST /agency/<name>/generate-brief`
**Frontend Changes:** AI brief section on agency.html
**Testing:** 3 new tests (mock Claude)
**Commit:** `feat: add AI-generated agency intelligence brief`
**Follow-up:** Task 165 (AI opportunity analysis uses agency brief)

---

## EPIC E09 — Opportunity Intelligence & Scoring

---

### Task 121 — Build multi-factor recompete scoring engine
**Epic:** E09 | **Milestone:** M3 | **Complexity:** XL | **Sessions:** 3
**Objective:** Replace the existing single-factor recompete score with a multi-factor
model that incorporates expiration, value, incumbent tenure, competition type, NAICS,
and historical recompete rate for this agency/NAICS pair.
**Requirements:**
- Create `scoring_engine.py` with `ScoreEngine` class
- Factors and weights:
  - `days_remaining_score`: 0–25 pts (< 30 days = 25, < 90 = 20, < 180 = 15, < 365 = 10)
  - `value_score`: 0–20 pts (logarithmic scale from $100K to $100M)
  - `competition_type_score`: 0–15 pts (competitive = 15, full+open = 12, sole source = 0)
  - `tenure_score`: 0–20 pts (> 5 years = 20, 3–5 = 15, 1–3 = 10, < 1 = 0)
  - `naics_recompete_rate_score`: 0–10 pts (historical rate for this NAICS in this agency)
  - `agency_budget_trend_score`: 0–10 pts (growing agencies score higher)
- Store breakdown in `score_breakdown_json` column
- Recalculate on every ingest
**Acceptance Criteria:**
- All scores 0–100 (clipped)
- Existing test suite still passes
- Score breakdown shown on contract detail
- Scores recalculate in < 5 seconds for 10,000 contracts
**Dependencies:** Tasks 111, 112, 116
**DB Changes:** `contracts`: add `score_breakdown_json TEXT`
**API Changes:** None
**Frontend Changes:** Score breakdown accordion on contract_detail.html
**Testing:** 10 new tests covering each factor and edge cases
**Commit:** `feat: replace single-factor recompete score with 6-factor scoring engine`
**Follow-up:** Task 122 (score explainer), Task 126 (ML enhancement)

---

### Task 122 — Add score explainability to contract detail
**Epic:** E09 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Show a human-readable explanation of why a contract received its score.
**Requirements:**
- Parse `score_breakdown_json` and generate bullet-point explanation
- "This contract scores 87 because: contract ends in 45 days (+25), value $2.4M (+15),
  incumbent held for 6 years (+20), competitive type: full+open (+12), ..."
- Display on contract detail in a collapsible "Why this score?" section
**Acceptance Criteria:**
- Explanation accurate to score factors
- Plain English (no jargon)
- Visible to all authenticated users
**Dependencies:** Task 121
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** Explainability card on contract_detail.html
**Testing:** 2 new tests
**Commit:** `feat: add score explainability breakdown to contract detail page`
**Follow-up:** Task 166 (AI explanation of pursuit decision)

---

### Task 123 — Build AI-powered opportunity recommendation engine
**Epic:** E09 | **Milestone:** M3 | **Complexity:** XL | **Sessions:** 3
**Objective:** Replace the rule-based `opportunity_recommendations()` in analytics.py
with an AI-driven recommendation engine that accounts for org profile, NAICS codes,
certifications, win history, and opportunity signals.
**Requirements:**
- Create `recommendation_engine.py` with `get_recommendations(org_id, limit=10)`
- Input factors: org NAICS codes, org certifications, org contract history,
  current recompete scores, recent changes, saved search history
- Use multi-stage approach:
  1. Filter: contracts in org's NAICS codes with score > 50
  2. Score: weight by org profile fit (SAM certifications match set-aside type)
  3. Rank: combine recompete score × org fit score
  4. Explain: generate per-recommendation rationale
- Store results in `org_recommendations` table (refreshed every 6h)
**Acceptance Criteria:**
- Top 10 recommendations include at least one in each of org's top 3 NAICS codes
- Each recommendation has a one-sentence rationale
- Recommendations refresh in < 10 seconds
- Dashboard shows these instead of generic recommendations
**Dependencies:** Tasks 082, 083, 121
**DB Changes:** New table: `org_recommendations (org_id, internal_id, rank, score, rationale, computed_at)`
**API Changes:** `GET /api/recommendations` returns JSON
**Frontend Changes:** Replace generic recs on dashboard
**Testing:** 6 new tests
**Commit:** `feat: replace rule-based recommendations with AI-scored recommendation engine`
**Follow-up:** Task 124 (forecasted opportunities)

---

### Task 124 — Add forecasted opportunities (pre-solicitation intel)
**Epic:** E09 | **Milestone:** M4 | **Complexity:** XL | **Sessions:** 3
**Objective:** Surface opportunities that haven't been solicited yet by predicting when
incumbents will recompete based on historical option exercise patterns.
**Requirements:**
- `predict_recompete_date(internal_id)`: analyze modification history to estimate
  next recompete date (base period + option periods duration)
- Create `forecasted_opportunities` table: contracts with predicted_recompete_date
- `GET /forecast` — dedicated forecast page showing predicted recompetes by quarter
- Confidence level: HIGH (≥ 3 option periods observed), MEDIUM (1–2), LOW (estimated)
**Acceptance Criteria:**
- Forecast page shows contracts sorted by predicted recompete date
- Confidence level displayed on each forecast
- "Next 90 Days" / "Next 180 Days" / "Next Year" filter tabs
- Integration with recommendation engine (forecasts scored and ranked)
**Dependencies:** Tasks 105, 121, 123
**DB Changes:** New table: `forecasted_opportunities (id, internal_id, predicted_recompete_date, confidence, model_version, computed_at)`
**API Changes:** `GET /forecast`
**Frontend Changes:** `templates/forecast.html`
**Testing:** 4 new tests
**Commit:** `feat: add recompete date forecasting with confidence levels`
**Follow-up:** Task 125 (forecast alerting)

---

### Task 125 — Alert when forecasted recompetes enter alert window
**Epic:** E09 | **Milestone:** M4 | **Complexity:** S | **Sessions:** 1
**Objective:** When a forecasted recompete date enters the org's alert window (90/180 days),
send an alert email.
**Requirements:**
- Celery daily task: check `forecasted_opportunities` vs. `org_alert_settings`
- When `predicted_recompete_date - today <= alert_days`, create alert
- Send email if not already alerted for this contract+threshold
- Track in `forecast_alerts_sent` table to avoid duplicates
**Acceptance Criteria:**
- Alert sent exactly once per contract per threshold crossing
- Email includes contract name, agency, predicted date, confidence
**Dependencies:** Tasks 074, 124, Task 176 (email delivery)
**DB Changes:** New table: `forecast_alerts_sent (org_id, internal_id, alert_days, sent_at)`
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests
**Commit:** `feat: send alerts when forecasted recompetes enter org alert windows`
**Follow-up:** None

---

### Task 126 — Add NAICS opportunity heatmap to dashboard
**Epic:** E09 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Add a dashboard widget showing opportunity density in the org's NAICS codes.
**Requirements:**
- Dashboard widget: "Opportunities in Your NAICS Codes" — count by NAICS, expiring next 180 days
- Color coded: green (low volume), yellow (medium), red (high volume = competitive)
- Click NAICS → `/contracts?naics=<code>&days=180`
**Acceptance Criteria:**
- Widget shows org's NAICS codes (from onboarding)
- Each code shows count and total value
- Widget loads in < 500ms (cached query)
**Dependencies:** Tasks 082, 103
**DB Changes:** None
**API Changes:** None
**Frontend Changes:** New widget in dashboard.html
**Testing:** 2 new tests
**Commit:** `feat: add NAICS opportunity density widget to dashboard`
**Follow-up:** None

---

## EPIC E13 — Notifications & Alerts (Partial — continues in 05_TASKS_151_200)

---

### Task 127 — Integrate transactional email service
**Epic:** E13 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 2
**Objective:** Add a transactional email service (SendGrid or Postmark) for all
outbound emails (verification, password reset, alerts, digests).
**Requirements:**
- Create `email_service.py` with `send_email(to, subject, html_body, text_body)` function
- Support SendGrid (`SENDGRID_API_KEY`) and Postmark (`POSTMARK_API_KEY`) via config
- Fall back to Python `smtplib` if neither is configured (dev/test only)
- Create email template base: `templates/email/base.html` with branding
- All emails use HTML template with plain-text fallback
- Log every send to `email_log` table
**Acceptance Criteria:**
- Email delivered in < 5 seconds in production
- HTML and plain-text versions sent
- Send logged regardless of success/failure
- Dev fallback prints to console
**Dependencies:** Task 064 (Celery for async send)
**DB Changes:** New table: `email_log (id, org_id, to_email, subject, template, status, error, sent_at)`
**API Changes:** None (internal service)
**Testing:** 4 new tests (mock HTTP client)
**Commit:** `feat: add transactional email service with SendGrid/Postmark support`
**Follow-up:** Task 128 (verification emails), Task 176 (alert emails)

---

### Task 128 — Send contract expiration alerts for watched contracts
**Epic:** E13 | **Milestone:** M1 | **Complexity:** M | **Sessions:** 2
**Objective:** When a watched contract's expiration crosses an alert threshold, send
an email to all org members who have alerts enabled.
**Requirements:**
- Celery daily task: scan watchlists, check days_remaining against `org_alert_settings.alert_days`
- Send email when `days_remaining` first crosses 180, 90, 60, or 30 day threshold
- Track sent alerts in `expiration_alerts_sent` (prevent duplicate sends)
- Email format: contract name, agency, value, days remaining, link to contract detail
**Acceptance Criteria:**
- Alert sent within 24 hours of crossing threshold
- No duplicate alerts for same contract+threshold+org
- User can unsubscribe from alerts (link in email footer)
**Dependencies:** Tasks 107 (watchlist), 127 (email service), 074 (alert settings)
**DB Changes:** New table: `expiration_alerts_sent (org_id, internal_id, alert_days, sent_at)`
**API Changes:** `GET /settings/alerts` (manage preferences)
**Frontend Changes:** Alert preferences on settings page
**Testing:** 5 new tests
**Commit:** `feat: add contract expiration alerts for watched contracts`
**Follow-up:** Task 129 (change detection alerts)

---

### Task 129 — Send alerts on contract status changes
**Epic:** E13 | **Milestone:** M2 | **Complexity:** S | **Sessions:** 1
**Objective:** Alert org when a watched contract receives a NEW, UPGRADE, or REMOVED
change detection event.
**Requirements:**
- Extend Celery ingest task: after `detect_changes()`, check if any changed contracts
  are in org watchlists
- Send email: "A contract you're watching changed status" with change details
- Separate alert type from expiration alerts
**Acceptance Criteria:**
- Alert sent on same day as change detection
- Alert email includes old status, new status, and contract details
**Dependencies:** Tasks 107, 127, 128
**DB Changes:** None (reuses existing changes table)
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests
**Commit:** `feat: send alerts when watched contracts receive status change events`
**Follow-up:** Task 130 (new opportunity alerts)

---

### Task 130 — Send new opportunity alerts matching saved searches
**Epic:** E13 | **Milestone:** M2 | **Complexity:** M | **Sessions:** 1–2
**Objective:** When a nightly ingest adds new contracts matching any org's saved search
filters, send an alert email.
**Requirements:**
- After nightly ingest: for each org's saved searches, re-run the query
- Compare results to `saved_search_last_results` snapshot
- New matches → send "New opportunities matching your search 'NAICS 561720'" email
- Update snapshot after alert sent
**Acceptance Criteria:**
- Alert sent for new matches only (no re-alerting on unchanged results)
- Email lists up to 5 new matches with contract names and values
**Dependencies:** Tasks 108 (saved searches), 127, 065 (nightly ingest)
**DB Changes:** `saved_searches`: add `last_results_json TEXT`, `last_checked_at TEXT`
**API Changes:** None
**Frontend Changes:** None
**Testing:** 4 new tests
**Commit:** `feat: send new opportunity alerts for saved search matches after nightly ingest`
**Follow-up:** Task 179 (weekly digest includes these)
