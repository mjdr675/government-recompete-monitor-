# PRODUCT_BACKLOG.md — Long-Term Backlog

This file captures features and improvements that are not yet in `backlog/` (the
agent's active work queue). Items here are reviewed at the start of each sprint
and promoted to `backlog/high.md` or `backlog/medium.md` as needed.

The agent does NOT read this file automatically. Promote items manually.

---

## Phase 2 — Early Customer Features

These are the next items in priority order after the active sprint.

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Saved searches (per user) | HIGH | M | Store query params + label in DB |
| Watchlist / bookmarks | HIGH | S | `user_watchlist` table, `/watchlist` route |
| Email alerts on expiration | HIGH | L | Needs background job + email service |
| Contract notes (annotations) | HIGH | M | Freetext notes per contract per user |
| CSV export from any view | MED | S | Stream CSV from `/contracts` query |
| Pipeline view (active pursuits) | MED | M | Tag contracts as "in pursuit" |
| Mobile-readable layout | MED | M | CSS pass; no JS framework |

---

## Phase 3 — Growth Features

Do not start these until Phase 2 customer goal is met (one paying, renewing company).

| Feature | Value | Effort | Notes |
|---|---|---|---|
| Team workspace | HIGH | L | Org-level data isolation, shared watchlists |
| Advanced recompete scoring | HIGH | L | Multi-factor: history, type, tenure |
| SAM.gov live integration | HIGH | L | Real-time pull, no manual CSV |
| Solicitation → contract linking | HIGH | XL | Match open solicitations to expiring awards |
| REST API | MED | L | Rate-limited, API key auth |
| PDF capture briefs | MED | M | Export comparison + notes as formatted PDF |
| Onboarding flow | MED | M | Demo data + guided first search |

---

## Ideas (Never Auto-Picked)

Log ideas here. They need scoring before any commitment.

- Teaming partner recommendations
- NAICS code navigator
- Slack/Teams integration for alerts
- Vendor win-rate profiles (how often does this vendor re-win?)
- Industry spend benchmarks by agency and PSC code
- White-label for resellers
