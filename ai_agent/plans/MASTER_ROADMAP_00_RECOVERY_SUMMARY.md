# MASTER_ROADMAP — Recovery Summary
# Created: 2026-06-20

---

## Files Inspected

### Root-level application files
- app.py — Flask routes, Stripe/HubSpot integration, auth wiring
- db.py — SQLite schema (contracts, users, snapshots, changes, demo_requests, early_access)
- analytics.py — dashboard_analytics, opportunity_recommendations, vendor_profile_analytics, agency_profile
- auth.py — Flask Blueprint, login/register/logout, session management
- users.py — create_user, get_user_by_id, verify_password (scrypt via Werkzeug)
- change_detector.py — NEW/REMOVED/UPGRADE/DOWNGRADE detection across snapshots
- hubspot_service.py — upsert_contact, create_deal, add_note, handle_demo_request, handle_stripe_checkout
- sam_lookup.py — solicitation lookup via SAM.gov opportunities API
- report_builder.py, views.py, recompete_report.py, daily_report.py
- requirements.txt — Flask, SQLite, Stripe, HubSpot, Anthropic, Werkzeug, gunicorn

### AI agent system
- ai_agent/ARCHITECTURE.md, CURRENT_STATE.md, DECISIONS.md, README.md
- ai_agent/done/: 041-agency-intelligence, 042-customer-dashboard, 043-opportunity-recommendations, 044-ai-engineering-manager
- ai_agent/queue/: 048 through 055 (AI Reviewer, PR Builder, Issues Sync, Observability, Daemon Mode, Human Escalation, Cost Budgeting, AI CTO)

### Company/product documents
- company/VISION.md — product vision, pricing philosophy, AI philosophy
- company/ROADMAP.md — Phases 1-4 (MVP through Market Leader)
- company/COMPETITORS.md — GovWin, GovTribe, Bloomberg Gov, SAM.gov, USAspending, FPDS
- company/RELEASE_PLAN.md — Release 1.0 (done), 1.1, 1.2, 2.0
- docs/ARCHITECTURE.md — full system architecture reference

### Backlog files
- backlog/critical.md — 2 items, both DONE
- backlog/bugs.md — 2 items, both DONE
- backlog/high.md — 3 OPEN items (min_value filter, /health test, ingest logging)
- backlog/medium.md — 3 OPEN items (views labels, pagination, route docs)

### Test suite
- tests/: test_app.py, test_auth.py, test_analytics.py, test_db.py, test_eng_memory.py,
  test_hubspot_service.py, test_loop.py, test_memory.py, test_patcher.py,
  test_queue_manager.py, test_recovery.py — 84 tests passing

---

## Key Conclusions

### What Already Exists
- Production Flask app on Railway (gunicorn + SQLite)
- Session-based auth (email/password, scrypt hashing)
- Contract ingestion: CSV upload + SAM.gov API pull
- FTS5 full-text search across vendor/agency/award_id
- Priority scoring (CRITICAL/HIGH/MEDIUM/LOW) + recompete score (0-100)
- Vendor intelligence page (full analytics profile)
- Agency intelligence page (full analytics profile)
- Customer dashboard with recommendations
- Contract comparison (side-by-side)
- Change detection across snapshots
- Stripe checkout + webhook + success/cancel
- HubSpot: contacts, deals, notes for demo/early-access/stripe events
- AI agent system: queue-based task execution with specialist agents
- 84-test suite, all passing

### What Is NOT Built Yet (critical gaps)
- No saved searches or watchlists
- No email notifications or alerts
- No per-user or per-organization data isolation
- No PostgreSQL migration (SQLite is ephemeral on Railway)
- No background job queue (Celery/Redis)
- No nightly automated data refresh
- No UEI/CAGE company lookup or company profiles
- No capture management workspace
- No proposal workspace
- No multi-tenant organization model
- No billing portal or plan enforcement
- No NAICS/PSC intelligence
- No ML-based recompete prediction
- No REST API
- No CSV/PDF export
- No onboarding wizard
- No enterprise features (SSO, audit logs, etc.)

### Architecture Constraints
- SQLite → must migrate to PostgreSQL before multi-user concurrent writes
- Railway deployment is solid foundation
- AI agent system (048-055) builds the engineering automation layer
- Next task number: 056

---

## Planned Roadmap Structure

### Milestones
| Milestone | Timeframe | Focus |
|---|---|---|
| M1: Internal Alpha | Days 0-60 | Stabilize, backlog items, watchlist, email alerts |
| M2: Private Beta | Days 60-150 | Multi-tenant orgs, PostgreSQL, UEI/company lookup, billing portal |
| M3: Public Beta | Days 150-240 | Capture management, AI recommendations, notifications, SAM live API |
| M4: Version 1.0 | Days 240-365 | Proposal workspace, ML scoring, REST API, enterprise security |
| M5: AI Capture Manager | Year 2 | Autonomous company discovery, AI capture plans, teaming |
| M6: Autonomous Platform | Year 2-3 | Self-improving models, NLU interface, full automation |

### Epics (24 total)
| # | Epic | Task Range |
|---|---|---|
| E01 | Immediate Backlog (carry-forward) | 056-060 |
| E02 | Platform Foundation (PostgreSQL, Redis, Celery) | 061-070 |
| E03 | Authentication & User Management | 071-078 |
| E04 | Customer Onboarding | 079-086 |
| E05 | Company Intelligence (UEI/CAGE/SAM entity) | 087-096 |
| E06 | Contract Intelligence (data depth) | 097-108 |
| E07 | Vendor Intelligence (enhanced) | 109-115 |
| E08 | Agency Intelligence (enhanced) | 116-122 |
| E09 | Opportunity Intelligence & Scoring | 123-133 |
| E10 | Capture Management | 134-148 |
| E11 | Proposal Management | 149-160 |
| E12 | AI Workflows & Agents | 161-173 |
| E13 | Notifications & Alerts | 174-183 |
| E14 | CRM & Billing | 184-192 |
| E15 | Analytics & Reporting | 193-202 |
| E16 | Security & Compliance | 203-210 |
| E17 | Performance & Scalability | 211-218 |
| E18 | Operations & Monitoring | 219-228 |
| E19 | Testing & Quality | 229-235 |
| E20 | Documentation | 236-241 |
| E21 | Enterprise Readiness | 242-251 |
| E22 | AI Agents (autonomous engineering) | 252-260 |
| E23 | Data Integrations | 261-270 |
| E24 | Demo, Sample Data & Import/Export | 271-278 |

---

## First 25 Planned Task Titles

| # | Title | Epic | Milestone |
|---|---|---|---|
| 056 | Add min_value filter to get_contracts() and /contracts route | E01 | M1 |
| 057 | Add /health unit test | E01 | M1 |
| 058 | Add ingest logging and /ingest/status route | E01 | M1 |
| 059 | Fix human-readable labels in views.html | E01 | M1 |
| 060 | Add first/last page buttons to contracts.html pagination | E01 | M1 |
| 061 | Provision PostgreSQL on Railway and add DB_URL config | E02 | M2 |
| 062 | Migrate schema from SQLite to PostgreSQL with SQLAlchemy | E02 | M2 |
| 063 | Add Redis service to Railway deployment | E02 | M2 |
| 064 | Integrate Celery with Redis for background task queue | E02 | M2 |
| 065 | Move SAM.gov API pull to Celery background task | E02 | M2 |
| 066 | Add email verification on registration | E03 | M2 |
| 067 | Add password reset via email token | E03 | M2 |
| 068 | Add user profile page (name, company, NAICS codes) | E03 | M2 |
| 069 | Add organization model (org, memberships, invitations) | E03 | M2 |
| 070 | Add team invitation flow via email | E03 | M2 |
| 071 | Add role-based permissions (admin, member, viewer) within org | E03 | M2 |
| 072 | Build onboarding wizard (step 1: company name/UEI/website) | E04 | M2 |
| 073 | Build onboarding wizard (step 2: select NAICS codes) | E04 | M2 |
| 074 | Build onboarding wizard (step 3: set alert thresholds) | E04 | M2 |
| 075 | Add demo mode with sample data (no login required) | E04 | M2 |
| 076 | SAM.gov entity search by UEI | E05 | M2 |
| 077 | SAM.gov entity search by CAGE code | E05 | M2 |
| 078 | SAM.gov entity search by company name | E05 | M2 |
| 079 | Build company profile page (certifications, NAICS, registration) | E05 | M3 |
| 080 | Link user organization to SAM entity for auto-discovery | E05 | M3 |
