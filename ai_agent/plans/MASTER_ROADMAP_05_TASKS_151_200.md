# MASTER ROADMAP — 05: Tasks 151–200
# Epics: E10 (Capture Management), E11 (Proposal Management),
#         E12 (AI Workflows), E13 (Notifications, continued)

---

## EPIC E10 — Capture Management

---

### Task 151 — Build capture workspace (opportunity-level)
**Epic:** E10 | **Milestone:** M3 | **Complexity:** XL | **Sessions:** 3
**Objective:** Create a dedicated workspace for each opportunity the org is actively pursuing.
The capture workspace is the central place for all capture team activity on a given contract.
**Requirements:**
- `capture_opportunities` table: linked to `internal_id`, has `status`, `go_nogo_decision`,
  `capture_manager`, `pwin_estimate`, `bid_decision_date`, `proposal_due_date`
- `GET /capture` — list all capture opportunities for org, sorted by proposal due date
- `GET /capture/<opp_id>` — workspace: contract summary, team, tasks, notes, docs, timeline
- Create capture opportunity from pipeline (`POST /pipeline/<id>/capture`)
- Status workflow: QUALIFYING → PURSUING → BID/NO-BID → PROPOSING → SUBMITTED → WON/LOST
**Acceptance Criteria:**
- Capture workspace loads in < 1 second
- All capture activity visible in one place
- Status transitions logged with timestamp and user
- Org members see all capture opportunities
**Dependencies:** Tasks 069, 071, 110 (pipeline view)
**DB Changes:** New table: `capture_opportunities (id, org_id, internal_id, status, capture_manager_id, pwin_estimate REAL, bid_decision_date TEXT, proposal_due_date TEXT, created_at TEXT, updated_at TEXT)`
**API Changes:** `GET/POST /capture`, `GET /capture/<id>`, status transition endpoints
**Frontend Changes:** `templates/capture/list.html`, `templates/capture/workspace.html`
**Testing:** 8 new tests
**Commit:** `feat: add capture workspace with status workflow and opportunity tracking`
**Follow-up:** Task 152 (capture tasks)

---

### Task 152 — Add capture tasks with assignments and due dates
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Within a capture workspace, manage a task list with assignments, due dates,
and completion tracking.
**Requirements:**
- `capture_tasks` table: `id, opp_id, org_id, title, description, assignee_id,
  due_date, status (OPEN/IN_PROGRESS/DONE/BLOCKED), priority, created_by, created_at`
- `POST /capture/<opp_id>/tasks` — create task
- `PATCH /capture/<opp_id>/tasks/<tid>` — update status/assignee/due date (HTMX)
- `DELETE /capture/<opp_id>/tasks/<tid>` — delete task
- Task list visible on capture workspace
- Overdue tasks highlighted in red
**Acceptance Criteria:**
- Task status updates without full page reload (HTMX)
- Assignee can be any org member
- Overdue tasks (past due_date and not DONE) shown with red indicator
- Viewer role cannot create or update tasks
**Dependencies:** Task 151
**DB Changes:** New table: `capture_tasks`
**API Changes:** CRUD endpoints under `/capture/<opp_id>/tasks`
**Frontend Changes:** Task list panel on capture workspace (HTMX)
**Testing:** 6 new tests
**Commit:** `feat: add capture task management with assignments and HTMX updates`
**Follow-up:** Task 153 (capture notes)

---

### Task 153 — Add capture notes and activity log
**Epic:** E10 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Capture-level notes visible to all org members, with an activity timeline
showing all status changes, task completions, and note additions.
**Requirements:**
- Reuse `contract_notes` pattern for `capture_notes` (scoped to capture_opp_id)
- Activity log: auto-generated entries for status changes, task adds/completes, note posts
- Display as combined chronological timeline on capture workspace
**Acceptance Criteria:**
- Notes post inline without page reload
- Activity log shows all events in chronological order
- Timestamps accurate to minute
**Dependencies:** Task 151, 106 (contract notes pattern)
**DB Changes:** New table: `capture_notes (id, opp_id, org_id, user_id, body, created_at)`; new table: `capture_activity (id, opp_id, org_id, user_id, event_type, payload_json, created_at)`
**API Changes:** `POST/GET /capture/<opp_id>/notes`
**Frontend Changes:** Notes + activity timeline on workspace
**Testing:** 4 new tests
**Commit:** `feat: add capture notes and activity log timeline`
**Follow-up:** Task 154 (milestones)

---

### Task 154 — Add capture milestones and calendar
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Track key capture milestones (Bid Decision, Proposal Due, Award Expected)
on a timeline view with calendar integration.
**Requirements:**
- `capture_milestones` table: predefined types (BID_DECISION, RFP_RELEASE, PROPOSAL_DUE, ORAL_PRESENTATION, AWARD_EXPECTED) + custom
- Set milestones on capture workspace
- Timeline view: horizontal bar from today → milestones
- `GET /capture/<opp_id>/calendar.ics` — iCal feed of milestones
- Upcoming milestones shown on capture list page (next 30 days)
**Acceptance Criteria:**
- iCal download works in Google Calendar and Apple Calendar
- Timeline renders correctly when milestones span 6–18 months
- Overdue milestones shown with alert icon
**Dependencies:** Task 151
**DB Changes:** New table: `capture_milestones (id, opp_id, org_id, type, label, due_date, completed_at)`
**API Changes:** `GET/POST /capture/<opp_id>/milestones`, `GET /capture/<opp_id>/calendar.ics`
**Frontend Changes:** Milestone timeline on workspace
**Testing:** 4 new tests
**Commit:** `feat: add capture milestones with timeline view and iCal export`
**Follow-up:** Task 155 (milestone alerts)

---

### Task 155 — Milestone due-date alerts
**Epic:** E10 | **Milestone:** M3 | **Complexity:** S | **Sessions:** 1
**Objective:** Alert capture team when a milestone is 14 and 3 days away.
**Requirements:**
- Celery daily task: check all uncompleted milestones with due_date within 14 or 3 days
- Send email to capture_manager and all org members with alerts enabled
- Alert includes: milestone type, due date, opportunity name, link to workspace
- Track in `milestone_alerts_sent` to prevent duplicates
**Acceptance Criteria:**
- Alert sent at exactly 14-day and 3-day thresholds
- No duplicate sends
- Completed milestones not alerted
**Dependencies:** Tasks 154, 127 (email)
**DB Changes:** New table: `milestone_alerts_sent (opp_id, milestone_id, alert_days, sent_at)`
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests
**Commit:** `feat: add milestone due-date alert emails at 14 and 3 days`
**Follow-up:** None

---

### Task 156 — Add go/no-go decision tracker
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Structured go/no-go evaluation form on the capture workspace. Records the
decision, factors, and rationale before committing to a bid.
**Requirements:**
- `capture_go_nogo` table: `opp_id, decision (GO/NOGO/CONDITIONAL), decision_by, decision_at, factors_json, notes`
- Factors checklist: customer relationship, past performance, teaming, price to win, key personnel available
- Each factor: YES/NO/UNKNOWN + weight (1–3)
- Score displayed: "Go Confidence: 78%"
- Decision recorded in activity log
**Acceptance Criteria:**
- Go/no-go form accessible from capture workspace
- Confidence score computed from factor weights
- Decision immutable once made (new entry required to change)
**Dependencies:** Task 151
**DB Changes:** New table: `capture_go_nogo`
**API Changes:** `GET/POST /capture/<opp_id>/gonogo`
**Frontend Changes:** Go/no-go panel on workspace
**Testing:** 4 new tests
**Commit:** `feat: add go/no-go decision tracker with weighted factor scoring`
**Follow-up:** Task 163 (AI generates go/no-go recommendation)

---

### Task 157 — Add teaming partner management in capture workspace
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Track potential and confirmed teaming partners for a given capture opportunity.
**Requirements:**
- `capture_teaming` table: `opp_id, org_id, partner_name, partner_uei, role (PRIME/SUB/JV), status (EXPLORING/LOI_SIGNED/CONFIRMED/DECLINED), contact_name, notes`
- Add/update/remove teaming partners from capture workspace
- Link to company profile if UEI provided
- Pre-populate from teaming suggestions (Task 115)
**Acceptance Criteria:**
- Partners added with role and status tracking
- Status change logged in activity log
- Link to company profile functional when UEI set
**Dependencies:** Tasks 115, 151
**DB Changes:** New table: `capture_teaming`
**API Changes:** CRUD under `/capture/<opp_id>/teaming`
**Frontend Changes:** Teaming panel on capture workspace
**Testing:** 4 new tests
**Commit:** `feat: add teaming partner management to capture workspace`
**Follow-up:** Task 158 (competitive analysis in workspace)

---

### Task 158 — Add competitive intelligence panel to capture workspace
**Epic:** E10 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Show competitor analysis inside the capture workspace: known incumbents,
likely bidders, and competitive threat assessment.
**Requirements:**
- Pull from vendor competitive set (Task 113) for the contract's agency/NAICS
- User can add known competitors manually with threat level (HIGH/MEDIUM/LOW)
- Threat assessment form: price competitiveness, past performance, incumbency advantage
- Store in `capture_competitors` table
**Acceptance Criteria:**
- Auto-populated from competitive set on workspace creation
- Manual competitors addable with notes
- Competitive threat summary shown on go/no-go form
**Dependencies:** Tasks 113, 151
**DB Changes:** New table: `capture_competitors (id, opp_id, vendor_name, threat_level, notes, is_incumbent)`
**API Changes:** CRUD under `/capture/<opp_id>/competitors`
**Frontend Changes:** Competitors panel on capture workspace
**Testing:** 3 new tests
**Commit:** `feat: add competitive intelligence panel to capture workspace`
**Follow-up:** Task 168 (AI competitor research)

---

## EPIC E11 — Proposal Management

---

### Task 159 — Build proposal workspace
**Epic:** E11 | **Milestone:** M4 | **Complexity:** XL | **Sessions:** 3
**Objective:** Create a proposal workspace linked to a capture opportunity. Tracks
proposal sections, due dates, volume leads, and submission.
**Requirements:**
- `proposals` table: `id, opp_id, org_id, title, rfp_number, solicitation_url, due_date, page_limit, status, volume_structure_json`
- `GET /proposals` — list org's proposals
- `GET /proposals/<id>` — workspace: sections, assignments, compliance matrix, timeline
- Create proposal from capture workspace (`POST /capture/<opp_id>/create-proposal`)
- Volume structure: configurable sections (Technical, Past Performance, Price, Management)
**Acceptance Criteria:**
- Proposal workspace loads with all sections visible
- Section assignments working (owner per section)
- Proposal status: PLANNING → DRAFTING → REVIEW → SUBMITTED → AWARDED/LOST
**Dependencies:** Task 151 (capture workspace)
**DB Changes:** New table: `proposals (id, opp_id, org_id, title, rfp_number, solicitation_url, due_date, page_limit, status, volume_structure_json, created_at)`, new table: `proposal_sections (id, proposal_id, volume, section_num, title, page_limit, owner_id, status, body, updated_at)`
**API Changes:** `GET/POST /proposals`, `GET /proposals/<id>`, section CRUD
**Frontend Changes:** `templates/proposals/list.html`, `templates/proposals/workspace.html`
**Testing:** 8 new tests
**Commit:** `feat: add proposal workspace with section tracking and volume structure`
**Follow-up:** Task 160 (compliance matrix)

---

### Task 160 — Add compliance matrix
**Epic:** E11 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** A requirement-by-requirement compliance checklist extracted from the RFP.
Each requirement mapped to a proposal section and marked as addressed.
**Requirements:**
- `proposal_requirements` table: `id, proposal_id, section_ref (L.4.1 etc.), requirement_text, response_section_id, status (ADDRESSED/PARTIAL/MISSING), notes`
- Manual entry or paste from RFP text
- AI extraction option: paste RFP text → Claude extracts L-requirements automatically
- Compliance matrix report: downloadable HTML table
**Acceptance Criteria:**
- Requirements addable manually or via AI extraction
- Coverage percentage shown: "87% of requirements addressed"
- Export as HTML table
**Dependencies:** Task 159
**DB Changes:** New table: `proposal_requirements`
**API Changes:** `POST /proposals/<id>/extract-requirements` (AI), CRUD for requirements
**Frontend Changes:** Compliance matrix tab on proposal workspace
**Testing:** 4 new tests
**Commit:** `feat: add proposal compliance matrix with AI RFP requirement extraction`
**Follow-up:** Task 161 (AI win themes)

---

### Task 161 — Add proposal win theme generation via AI
**Epic:** E11 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Use Claude to generate 3–5 win themes for a proposal based on the
opportunity, the org's capabilities, and the competitive landscape.
**Requirements:**
- Button "Generate Win Themes" on proposal workspace
- Prompt to Claude: opportunity summary, org's SAM certifications + NAICS, competitive intel
- Output: 3–5 win themes, each with a headline and 2-sentence rationale
- Store in `proposal_win_themes` table
- Display in a section of the proposal workspace
**Acceptance Criteria:**
- Win themes generated in < 30 seconds
- Each theme addresses a specific differentiator
- User can edit, delete, or add themes
**Dependencies:** Task 159, Task 102 (ai_analyses pattern)
**DB Changes:** New table: `proposal_win_themes (id, proposal_id, headline, rationale, order_num)`
**API Changes:** `POST /proposals/<id>/generate-themes`
**Frontend Changes:** Win themes panel on proposal workspace
**Testing:** 3 new tests (mock Claude)
**Commit:** `feat: add AI win theme generation for proposal workspace`
**Follow-up:** Task 162 (proposal section drafting)

---

### Task 162 — Add AI proposal section drafting assistance
**Epic:** E11 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** For each proposal section, provide AI-assisted drafting: generates an
outline and starter text based on the section requirements and win themes.
**Requirements:**
- "AI Draft" button on each proposal section
- Prompt: section requirements, win themes, org capabilities, page limit
- Output: structured outline + starter paragraph per outline point
- Does NOT generate a submission-ready proposal — AI assists, human writes
- Content stored in `proposal_sections.body` (editable plain text)
- Clearly labelled "AI Draft — Review and Edit Before Use"
**Acceptance Criteria:**
- Draft generated in < 60 seconds
- Outline follows standard GovCon structure (Approach, Understanding, Staffing, etc.)
- Human edits to the text are preserved across AI regenerations
**Dependencies:** Task 159, 161
**DB Changes:** None
**API Changes:** `POST /proposals/<id>/sections/<sid>/draft`
**Frontend Changes:** "AI Draft" button on section editor, warning banner on AI-drafted content
**Testing:** 3 new tests (mock Claude)
**Commit:** `feat: add AI-assisted proposal section drafting with human-edit preservation`
**Follow-up:** Task 159/160 follow-up (compliance matrix links to sections)

---

## EPIC E12 — AI Workflows

---

### Task 163 — AI capture plan generation
**Epic:** E12 | **Milestone:** M3 | **Complexity:** XL | **Sessions:** 3
**Objective:** For any opportunity in the capture workspace, generate a structured
AI capture plan: situation assessment, recommended actions, timeline, and resource needs.
**Requirements:**
- Button "Generate Capture Plan" on capture workspace
- Input to Claude: contract details, agency intel brief, org profile, competitive set,
  teaming partners identified, go/no-go factors
- Output: structured markdown capture plan with sections:
  1. Opportunity Assessment (score, why pursue)
  2. Customer Intelligence (agency buying patterns, key contacts to research)
  3. Competitive Assessment (known threats, recommended positioning)
  4. Teaming Strategy (recommendation with rationale)
  5. Win Strategy (top 3 win themes)
  6. 90-Day Action Plan (concrete tasks with owners)
  7. Resource Requirements (staffing, BD cost estimate)
- Store in `ai_analyses` table
- Render as formatted HTML on capture workspace
**Acceptance Criteria:**
- Plan generated in < 90 seconds
- All 7 sections present and coherent
- Action plan items can be imported as capture tasks (one click)
- Clearly marked "AI-generated — Review before use"
**Dependencies:** Tasks 120, 151, 156, 157, 158
**DB Changes:** None (reuses ai_analyses)
**API Changes:** `POST /capture/<opp_id>/generate-plan`
**Frontend Changes:** Capture plan tab on workspace, "Import Tasks" button
**Testing:** 4 new tests (mock Claude, test task import)
**Commit:** `feat: add AI capture plan generation with 7-section structured output`
**Follow-up:** Task 164 (opportunity analysis), Task 165 (daily briefing)

---

### Task 164 — AI opportunity analysis on contract detail
**Epic:** E12 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Add an "AI Analysis" panel to every contract detail page that explains
the opportunity in plain English: incumbency situation, competitive landscape, recommendation.
**Requirements:**
- "Analyze" button on contract detail (generates on demand, cached 24h)
- Prompt: contract data, vendor analytics, agency analytics, org NAICS match
- Output: 3–4 paragraphs:
  1. Opportunity summary (what is this contract, who holds it, when does it expire)
  2. Competitive situation (incumbent strength, set-aside type, likely bidders)
  3. Relevance to your org (NAICS match, certification fit, size match)
  4. Recommendation (pursue / investigate / skip — with one-sentence rationale)
- Store in ai_analyses (entity_type='contract', analysis_type='opportunity_brief')
**Acceptance Criteria:**
- Analysis generated in < 45 seconds
- Recommendation label (PURSUE/INVESTIGATE/SKIP) is prominent
- Cached for 24h; user can force refresh
**Dependencies:** Task 102 (ai_analyses table), Task 121 (scoring engine data)
**DB Changes:** None
**API Changes:** `POST /contract/<id>/analyze`
**Frontend Changes:** AI Analysis panel on contract_detail.html
**Testing:** 3 new tests
**Commit:** `feat: add AI opportunity analysis panel to contract detail page`
**Follow-up:** Task 165 (daily briefing)

---

### Task 165 — Daily AI opportunity briefing
**Epic:** E12 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** Each morning, generate and send a personalized AI briefing for each org:
new opportunities matching their profile, status changes on watched contracts,
and a 1–3 sentence market observation.
**Requirements:**
- Celery beat task at 06:00 UTC daily: `send_daily_briefing(org_id)`
- Content:
  1. Top 3 new opportunities in org's NAICS codes from last 24h
  2. Status changes on watched contracts
  3. Upcoming expirations (next 14 days)
  4. One AI-generated market observation (based on yesterday's new awards)
- Email format: HTML digest with links to contract detail pages
- User opt-in/out from `/settings/alerts`
**Acceptance Criteria:**
- Email delivered by 07:00 UTC
- Content accurate to prior 24h data
- Users who opt out receive no emails
- No briefing sent if no new data (quiet day)
**Dependencies:** Tasks 107, 123, 127, 164
**DB Changes:** `org_alert_settings`: add `daily_briefing_enabled BOOLEAN DEFAULT TRUE`
**API Changes:** None
**Frontend Changes:** Toggle on alerts settings page
**Testing:** 4 new tests (mock email, mock data)
**Commit:** `feat: add daily AI opportunity briefing email at 06:00 UTC`
**Follow-up:** Task 166 (weekly digest)

---

### Task 166 — Weekly AI market digest
**Epic:** E12 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Send a weekly PDF-style email digest summarizing the week's contract
activity in the org's NAICS codes, notable agency spend shifts, and top opportunities.
**Requirements:**
- Celery beat task on Monday 07:00 UTC: `send_weekly_digest(org_id)`
- Content:
  1. Weekly summary stats (new contracts, total value added, top agency)
  2. Top 5 opportunities in NAICS codes (from recommendation engine)
  3. Notable incumbents at risk this week
  4. Upcoming milestones for org's capture opportunities
  5. AI-written market observation (1 paragraph)
- HTML email with clean formatting
- Opt-in (default: off for new orgs)
**Acceptance Criteria:**
- Digest delivered Monday morning
- Content covers the full prior week (Mon-Sun)
- Capture milestone section only appears if org has active captures
**Dependencies:** Task 165
**DB Changes:** `org_alert_settings`: add `weekly_digest_enabled BOOLEAN DEFAULT FALSE`
**API Changes:** None
**Frontend Changes:** None
**Testing:** 3 new tests
**Commit:** `feat: add weekly AI market digest email with opportunity summary`
**Follow-up:** None

---

### Task 167 — AI competitive research on demand
**Epic:** E12 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** On-demand AI research report on a specific competitor — their contract
history, strengths, weaknesses, likely bidding pattern, and recommended counter-strategy.
**Requirements:**
- `GET /vendor/<name>/ai-research` — generate competitive research report
- Input to Claude: vendor analytics (from vendor_profile_analytics), agency relationships,
  NAICS concentration, win rate, estimated revenue, certifications (if available)
- Output: 4-section report:
  1. Company overview (estimated revenue, headcount hint, primary services)
  2. Contract portfolio (strengths, preferred agencies, typical contract size)
  3. Competitive threats (where they consistently win)
  4. Counter-strategy (how your org can compete)
- Cache 48h per vendor
**Acceptance Criteria:**
- Report generated in < 60 seconds
- All 4 sections present and sourced from actual data
- Cache shown as "Last updated X hours ago"
**Dependencies:** Tasks 113, 102 (ai_analyses pattern)
**DB Changes:** None
**API Changes:** `POST /vendor/<name>/ai-research`
**Frontend Changes:** "AI Research" button on vendor.html
**Testing:** 3 new tests
**Commit:** `feat: add AI competitive research report for vendor profiles`
**Follow-up:** Task 158 (feeds into capture competitive panel)

---

### Task 168 — AI price-to-win range estimation
**Epic:** E12 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Estimate a price-to-win range for a contract opportunity using historical
award data for similar contracts (same agency, NAICS, value range).
**Requirements:**
- `POST /contract/<id>/price-to-win` — generate PTW estimate
- Query: historical contracts in same NAICS, same agency, similar value range
- Compute: median, P25, P75 values; YoY inflation adjustment (3%)
- Prompt to Claude: historical data + current contract metadata
- Output: estimated range (low/midpoint/high) with rationale
- Store in capture_opportunities
**Acceptance Criteria:**
- PTW range shown in capture workspace when at least 5 comparable contracts found
- "Insufficient comparable data" shown gracefully when < 5 comparables
- Range includes inflation-adjusted values
**Dependencies:** Tasks 151, 121
**DB Changes:** `capture_opportunities`: add `ptw_low REAL`, `ptw_mid REAL`, `ptw_high REAL`, `ptw_notes TEXT`
**API Changes:** `POST /contract/<id>/price-to-win`
**Frontend Changes:** PTW section on capture workspace
**Testing:** 4 new tests
**Commit:** `feat: add AI price-to-win range estimation using comparable contract history`
**Follow-up:** None

---

## EPIC E13 — Notifications (continued)

---

### Task 169 — Build notification center (in-app)
**Epic:** E13 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 2
**Objective:** In-app notification center accessible from the nav header. Shows recent
alerts, contract changes, milestone reminders, and team activity.
**Requirements:**
- `notifications` table: `id, org_id, user_id, type, title, body, entity_type, entity_id, read_at, created_at`
- Bell icon in nav with unread count badge
- Dropdown (HTMX): last 10 notifications
- `GET /notifications` — full notification list
- `POST /notifications/<id>/read` — mark as read
- `POST /notifications/read-all`
- Notification types: CONTRACT_ALERT, CAPTURE_UPDATE, MILESTONE_DUE, TEAM_INVITE, SYSTEM
**Acceptance Criteria:**
- Unread count updates without page refresh (polling every 60s via HTMX)
- All existing email alerts also create in-app notifications
- Notifications older than 30 days archived automatically
**Dependencies:** Tasks 069, 128, 155
**DB Changes:** New table: `notifications`
**API Changes:** `GET /notifications`, `POST /notifications/<id>/read`
**Frontend Changes:** Nav bell icon, notification dropdown
**Testing:** 5 new tests
**Commit:** `feat: add in-app notification center with unread count badge`
**Follow-up:** Task 170 (webhook delivery)

---

### Task 170 — Add webhook delivery for contract events
**Epic:** E13 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow orgs to register webhook URLs that receive JSON payloads when
contract events occur (new contract, status change, milestone due, etc.).
**Requirements:**
- `org_webhooks` table: `id, org_id, url, secret, events_json (list of subscribed events), created_at, is_active`
- `GET/POST/DELETE /settings/webhooks`
- On event: async Celery task sends POST with HMAC-signed payload
- Retry 3x with exponential backoff on 4xx/5xx
- Log delivery attempts in `webhook_deliveries` table
**Acceptance Criteria:**
- Webhook payload delivered within 30 seconds of event
- HMAC signature header `X-Signature` on every request
- Failed deliveries logged with response code and body
- Test delivery button on webhook settings
**Dependencies:** Tasks 069, 064 (Celery), 069
**DB Changes:** New tables: `org_webhooks`, `webhook_deliveries`
**API Changes:** Webhook settings CRUD, `POST /settings/webhooks/test`
**Frontend Changes:** `templates/settings/webhooks.html`
**Testing:** 5 new tests
**Commit:** `feat: add webhook delivery with HMAC signing and retry logic`
**Follow-up:** None

---

### Task 171 — Add Slack notification integration
**Epic:** E13 | **Milestone:** M4 | **Complexity:** M | **Sessions:** 2
**Objective:** Allow orgs to connect a Slack workspace and receive contract alerts
and daily briefings in a Slack channel.
**Requirements:**
- Slack OAuth app (Bot Token Scopes: `chat:write`, `incoming-webhook`)
- `GET /integrations/slack/connect` — OAuth flow
- `GET /integrations/slack/callback` — save access_token and channel_id to `org_integrations`
- Send alerts to Slack via `chat.postMessage` when email alerts fire
- Slack message format: rich attachment with contract name, value, days remaining, link
- Test message button on integration settings
**Acceptance Criteria:**
- OAuth flow completes in < 30 seconds
- Slack message arrives within 60 seconds of triggering event
- Disconnecting integration removes token from storage
**Dependencies:** Tasks 127, 128, 065
**DB Changes:** New table: `org_integrations (id, org_id, type, access_token_enc, config_json, connected_at)`
**API Changes:** `/integrations/slack/connect`, `/integrations/slack/callback`, `/integrations/slack/disconnect`
**Frontend Changes:** `templates/settings/integrations.html`
**Testing:** 4 new tests (mock Slack API)
**Commit:** `feat: add Slack integration for contract alerts and daily briefings`
**Follow-up:** Task 172 (Microsoft Teams)

---

### Task 172 — Add Microsoft Teams notification integration
**Epic:** E13 | **Milestone:** M4 | **Complexity:** S | **Sessions:** 1
**Objective:** Allow orgs to configure a Teams webhook URL for contract alerts.
**Requirements:**
- Teams Incoming Webhook URL (no OAuth needed — user pastes URL)
- `POST /integrations/teams/configure` — save webhook URL to `org_integrations`
- Send Teams-formatted adaptive card on alerts
- Test message button
**Acceptance Criteria:**
- Adaptive card renders correctly in Teams
- Test message confirms the webhook URL is valid
**Dependencies:** Task 171 (org_integrations table)
**DB Changes:** None (reuses org_integrations)
**API Changes:** Teams configure/disconnect endpoints
**Frontend Changes:** Teams section on integrations settings
**Testing:** 2 new tests
**Commit:** `feat: add Microsoft Teams notification integration via incoming webhook`
**Follow-up:** None

---

### Task 173 — Add email unsubscribe and notification preference center
**Epic:** E13 | **Milestone:** M3 | **Complexity:** M | **Sessions:** 1–2
**Objective:** Allow users to manage all notification preferences (email frequency,
types, Slack) from a single preference center.
**Requirements:**
- `GET /settings/notifications` — comprehensive preferences page
- Per-type opt-in/out: expiration alerts, change alerts, milestone alerts, daily briefing, weekly digest
- Global unsubscribe link in every email footer (one-click, no login required)
- `GET /unsubscribe?token=<tok>` — token-based unsubscribe for email link
- Unsubscribed flag on per-user basis (not org-wide)
**Acceptance Criteria:**
- Unsubscribe link in every outgoing email
- Clicking link unsubscribes without requiring login
- Re-subscribing available from `/settings/notifications`
- Org admin can see aggregate opt-out rates (not per-user)
**Dependencies:** Task 127
**DB Changes:** `users`: add `notification_prefs_json TEXT`, `global_unsubscribe BOOLEAN DEFAULT FALSE`, `unsubscribe_token TEXT`
**API Changes:** `GET/POST /settings/notifications`, `GET /unsubscribe`
**Frontend Changes:** `templates/settings/notifications.html`, footer in all emails
**Testing:** 4 new tests
**Commit:** `feat: add notification preference center with one-click email unsubscribe`
**Follow-up:** None
