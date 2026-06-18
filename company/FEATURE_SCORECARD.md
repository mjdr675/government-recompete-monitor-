# FEATURE_SCORECARD.md — Feature Prioritization

Score each candidate feature before adding it to the backlog. This prevents
building things that feel important but don't move the mission.

## Scoring Rubric

Score each dimension 1–5. Higher is better.

| Dimension | 1 | 5 |
|---|---|---|
| **Customer value** | Nice-to-have, no one asked | Multiple customers blocked without it |
| **Revenue impact** | No effect on conversion/retention | Directly drives signup or renewal |
| **Effort** | Months of work | Hours of work |
| **Risk** | High chance of breakage or scope creep | Well-understood, contained change |
| **Strategic fit** | Off-mission | Core to recompete intelligence |

**Priority score** = (Customer value + Revenue impact + Strategic fit) × (Effort + Risk) / 2

---

## Scored Features

| Feature | Cust. Value | Revenue | Effort | Risk | Strategic | Score | Decision |
|---|---|---|---|---|---|---|---|
| Session auth | 5 | 5 | 3 | 4 | 5 | 34.0 | SHIP |
| Contract comparison | 4 | 3 | 4 | 5 | 4 | 31.5 | SHIP |
| Saved searches | 4 | 4 | 3 | 4 | 4 | 27.5 | NEXT |
| Email alerts | 5 | 5 | 2 | 3 | 5 | 37.5 | NEXT |
| CSV export | 3 | 3 | 4 | 5 | 3 | 27.0 | BACKLOG |
| Min-value filter | 3 | 2 | 5 | 5 | 3 | 25.0 | BACKLOG |
| PostgreSQL migration | 2 | 3 | 1 | 2 | 4 | 13.5 | PHASE 2 |
| ML recompete model | 3 | 4 | 1 | 2 | 5 | 18.0 | PHASE 3 |

---

## Graveyard

Features evaluated and rejected. Keep this so we don't re-score the same idea.

| Feature | Score | Why Rejected |
|---|---|---|
| Proposal generation | 2 | Off-mission; removes human judgment |
| Bid/no-bid automation | 1 | Off-mission by explicit policy (see company/VISION.md) |
