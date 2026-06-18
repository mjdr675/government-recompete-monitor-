# SPRINT.md — Current Sprint

This file tracks the active development sprint. Update it at the start of each
sprint and mark items done as they complete. Archive completed sprints at the
bottom.

---

## Active Sprint — Phase 2: Early Customers

**Goal:** Build the foundation for the first paying customer.

**Sprint items:**

| Status | Item | Owner |
|---|---|---|
| DONE | Contract comparison page | frontend |
| DONE | Session-based authentication | backend |
| DONE | User registration and login | backend |
| DONE | Password hashing (scrypt) | backend |
| DONE | Route protection | backend |
| OPEN | Per-user saved searches | backend |
| OPEN | Watchlist (bookmark contracts) | backend |
| OPEN | Email alerts on contract changes | backend |
| OPEN | Export to CSV from filtered view | backend |
| OPEN | Min-value filter on contract search | backend |
| OPEN | Nightly SAM.gov data refresh | devops |

**Done when:** One external person can register, find three relevant contracts,
and bookmark them — without asking for help.

---

## Archived Sprints

### Sprint 0 — MVP (Complete)

Delivered a working Flask app on Railway with contract search, scoring, vendor
and agency intelligence pages, CSV ingest, and a basic AI agent scaffold.

### Sprint 1 — AI Engineering Platform (Complete)

Delivered the multi-agent system with repository memory, patch pipeline, safety
reviewer, and automatic rollback. 84 tests passing.
