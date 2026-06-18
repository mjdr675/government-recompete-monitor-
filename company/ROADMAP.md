# ROADMAP.md — Product Roadmap

Phases are sequential. A phase is not "done" until its customer goal is met —
not when its features ship. Technical and revenue goals are checkpoints, not
definitions of success.

---

## Phase 1 — MVP

**Status: Complete**

### Features
- Contract ingestion from SAM.gov CSV and API
- Full-text search across vendor, agency, and award ID
- Priority scoring (CRITICAL / HIGH / MEDIUM / LOW) based on expiration and value
- Recompete score (0–100) per contract
- Filtering by agency, priority, days remaining, and value
- Sortable contract list with pagination
- Contract detail page
- Vendor intelligence page (all contracts by vendor, win history)
- Agency intelligence page (spend profile, active vendors)
- Saved views (High Value, Expiring Soon, Critical, etc.)
- CSV import and API pull from the ingest page
- Basic HTTP auth for access control
- `/health` route for Railway uptime checks
- Railway deployment with gunicorn
- AI agent scaffold: task backlog, specialist agents, dry-run mode

### Technical Goals
- Flask app deployed and stable on Railway
- SQLite database with FTS5 full-text search
- Automated test suite (57+ passing tests)
- AI agent runs safely with DRY_RUN=true as default
- Repository memory index for AI context

### Customer Goal
One person can use the product to find three contracts worth pursuing in under
ten minutes, starting from zero.

### Revenue Goal
$0. This phase validates the product, not the business model.

---

## Phase 2 — Early Customers

**Status: Active development**

The goal of this phase is to acquire the first paying customer and establish
product-market fit within a single company's BD workflow.

### Features
- User accounts with email/password authentication ✓
- Per-user saved searches and watchlists
- Email alerts when watched contracts change status or approach expiration
- Contract comparison page (select 2 contracts, compare side by side) ✓
- Min-value filter on contract search
- Ingest status endpoint (`/ingest/status`) with log tail
- `/health` authentication bypass hardened
- Export to CSV from any filtered view
- Contract notes (capture team can annotate a contract)
- "Pipeline" view — contracts the team is actively pursuing
- Mobile-readable layout pass

### Technical Goals
- Replace SQLite with PostgreSQL for multi-user concurrent access
- Session management (Flask-Login or equivalent) ✓
- Email delivery (transactional email service)
- Background job queue for alert delivery
- Automated nightly SAM.gov data refresh
- Test coverage above 80%

### Customer Goal
At least one paying company uses the platform as part of their weekly BD
process and renews after month one.

### Revenue Goal
$99–$299/month from first customer. Target: $500 MRR by end of phase.

---

## Phase 3 — Growth

The goal of this phase is repeatable customer acquisition and expanding depth
for customers who are already using the product daily.

### Features
- Team workspace with shared watchlists and pipeline
- Advanced scoring: multi-factor model (recompete history, competition type,
  agency budget trends, incumbent tenure)
- Agency budget intelligence: trending spend by NAICS code and PSC
- Vendor win-rate profiles: how often does this vendor re-win its contracts?
- Opportunity heatmap: agencies buying in your categories right now
- SAM.gov live integration (real-time data, no manual CSV upload)
- Solicitation tracking: link contract expirations to open solicitations on SAM
- REST API for customers who want to integrate data into their own tools
- White-label reports: export a capture brief as a formatted PDF
- Onboarding flow and in-app demo with sample data

### Technical Goals
- Multi-tenant data model with organization-level isolation
- PostgreSQL full-text search replacing SQLite FTS5
- API rate limiting and authentication (API keys)
- Observability: structured logging, error tracking, uptime monitoring
- Staging environment separate from production
- CI/CD pipeline that runs tests on every PR

### Customer Goal
Ten paying companies. At least three have been customers for more than 90 days.
Net Promoter Score above 50 from active users.

### Revenue Goal
$5,000 MRR. One customer on the Team tier.

---

## Phase 4 — Market Leader

The goal of this phase is to become the default tool for small and mid-sized
government contractors pursuing federal prime contracts.

### Features
- ML-based recompete probability model trained on historical FPDS outcomes
- Competitive intelligence: who else is likely bidding on this contract?
- Teaming recommendations: find potential partners for specific opportunities
- Proposal intelligence: link expiring contracts to past proposal data
- Slack and Teams integration: alerts and opportunity summaries delivered
  where the team already works
- SAM.gov entity registration integration: verify vendor eligibility
- NAICS code navigator: help users identify the right codes for their business
- Industry benchmarks: how does this agency's spending compare to the market?
- Partner marketplace: connect small businesses looking to team

### Technical Goals
- Machine learning pipeline for recompete probability scoring
- Data warehouse (separate from transactional DB) for analytics queries
- Public API with SDK (Python, Go)
- SOC 2 Type II compliance
- 99.9% uptime SLA
- Sub-200ms p95 API response time

### Customer Goal
One hundred paying companies. Category recognition: when a govcon professional
thinks "where do I find recompetes," this product is the first answer.

### Revenue Goal
$50,000 MRR. Multiple customers on annual plans.

---

## What Is Never on the Roadmap

- Proposal writing automation
- Bid/no-bid recommendations without human review
- Automatic contract submissions to SAM.gov
- Anything that removes human judgment from the capture process

The product is an intelligence tool, not an autonomous agent for the customer's
business. See `company/VISION.md — AI Philosophy` for the reasoning.
