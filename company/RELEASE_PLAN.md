# RELEASE_PLAN.md — Release Schedule

This file maps features to release milestones. A release is not a date — it is
a customer outcome. We ship when a milestone is met, not on a calendar.

---

## Release 1.0 — "First Login"

**Status:** Complete  
**Customer outcome:** A new user can register, search contracts, and find three
relevant opportunities in under ten minutes.

**Shipped:**
- Contract search with FTS5 full-text search
- Priority scoring and recompete score
- Vendor and agency intelligence pages
- Saved views
- Railway deployment
- Session-based authentication
- User registration and login

---

## Release 1.1 — "Daily Driver"

**Status:** Planned  
**Customer outcome:** A capture manager uses the product every working day as
part of their BD workflow.

**Requires:**
- Saved searches (persist filter state with a name)
- Watchlist (bookmark contracts to track)
- Email alert when a watched contract's status changes
- Contract comparison (shipped in 1.0 early)

---

## Release 1.2 — "First Payment"

**Status:** Planned  
**Customer outcome:** At least one company has entered payment details and
renewed after month one.

**Requires:**
- Stripe or payment processor integration
- Billing portal (upgrade/downgrade/cancel)
- Usage limits per plan tier
- 14-day trial with no card required

---

## Release 2.0 — "Team Product"

**Status:** Roadmap  
**Customer outcome:** Multiple people at the same company use the product
collaboratively with shared data.

**Requires:**
- Organization model (shared workspace)
- PostgreSQL (replaces SQLite for concurrent writes)
- Team invitations
- Shared watchlists and pipeline

See `company/ROADMAP.md — Phase 3` for full scope.

---

## Release Policy

- Releases deploy to Railway automatically when the main branch is updated
- All tests must pass before merge to main
- No hotfixes without a corresponding test
- Version numbers are not used — releases are named by customer outcome
