# VISION.md — Product Vision

Read this before writing a single line of code. It explains who we are building
for, why they need us, and where this product is going.

---

## Why This Product Exists

The U.S. federal government awards roughly $700 billion in contracts every year.
A large fraction of that spend renews — it recompetes. When an incumbent
contract expires, the agency must solicit new bids. That is an opportunity.

Small and mid-sized government contractors — companies with 50 to 500 employees
— know this. Their business development teams spend hours every week manually
combing through SAM.gov, building spreadsheets, and chasing contract expiration
dates. They miss opportunities because they simply did not see them in time, or
because they saw them too late to build a competitive proposal.

The large contractors use GovWin or GovTribe. Those products cost thousands of
dollars per seat per year and are designed for enterprise procurement teams with
dedicated analysts. A 60-person company with two business development staff
cannot afford them, cannot use them efficiently, and does not need 80% of their
features.

This product exists to close that gap.

---

## Target Customers

**Primary:** Capture managers and business development directors at small and
mid-sized U.S. government contractors (50–500 employees) pursuing federal
prime contracts between $1M and $50M.

**Secondary:** Sole proprietors and boutique firms (under 50 employees) who
do government contracting as part of a mixed business. They need the same
intelligence but have even less time and smaller budgets.

**Not targeted (yet):** Large defense contractors, staffing firms pursuing
high-volume low-value contracts, state and local procurement.

### What our customers look like

- A capture manager at a 120-person IT services firm who tracks 40 contracts
  manually in a spreadsheet and wants to know when something is about to expire
- A BD director at a professional services company who needs to understand which
  agencies are buying what, and which incumbents are vulnerable
- A small business owner who bids on 8(a) set-asides and wants to find contracts
  expiring in her NAICS codes before her competitors do

---

## Problems Being Solved

**1. Discovery is too slow.**
SAM.gov is the authoritative source but it is not a research tool. Finding
expiring contracts requires multiple searches, manual date math, and no scoring
or prioritization. Capture managers either miss opportunities or spend hours they
do not have.

**2. No prioritization.**
Even when a contractor finds an expiring contract, they have no good way to
decide whether to pursue it. Is this agency a good fit? Has this vendor held it
for three terms? Is the value worth the bid cost? Those answers require cross-
referencing multiple sources manually.

**3. Competitive intelligence is locked behind price.**
Understanding who holds what contracts — and how long they have held them — is
the core of competitive intelligence in govcon. That data exists in FPDS, but
extracting and interpreting it takes analyst hours that small firms do not have.

**4. Alerts do not exist where they need to.**
Contractors know a contract is about to expire only when it is already too late
to build a strong proposal. Early warning — 180 days, 90 days, 60 days — is the
difference between a competitive bid and a protest.

---

## Competitive Advantages

**Affordable.**
We target $99–$299/month per company, not per seat. GovWin runs $800–$1,500/seat/
year for larger tiers. Our entire annual subscription costs less than one month of
a competitor's enterprise license.

**Focused.**
We do one thing: recompete intelligence. We do not try to be a full govcon
platform. This makes us faster to learn, faster to search, and more useful for
the specific workflow of finding and qualifying expiration opportunities.

**Scored and prioritized.**
Every contract gets a recompete score. Capture managers see the highest-value,
most-likely-to-recompete opportunities first instead of scrolling through thousands
of unranked results.

**Modern UX.**
The product is a fast, simple web application. No training required. No 40-tab
spreadsheets. No annual enterprise rollout. A new user is productive in five
minutes.

**AI-assisted but human-controlled.**
AI helps find patterns, surfaces intelligence, and assists with analysis. Humans
make every capture decision. We will never auto-generate proposals or replace
human judgment on bid/no-bid decisions.

---

## Long-Term Roadmap

See `company/ROADMAP.md` for phased details. The directional arc is:

1. **Data access** — ingest, normalize, and score federal contract data
2. **Intelligence** — surface patterns, score opportunities, alert on changes
3. **Workflow** — integrate into the capture team's actual process
4. **Network** — become the platform small contractors use to collaborate

---

## Product Philosophy

**Every screen saves a capture manager time.**
If a feature does not directly help a user find an opportunity faster, qualify it
more accurately, or track it with less effort, it does not belong in the product.

**Complexity is our enemy.**
Our users have 20 tabs open, three deadlines, and a proposal due Friday. Every
interaction must be obvious. No onboarding decks. No configuration. No jargon.

**Accuracy over coverage.**
A smaller dataset that is correct and well-scored is more useful than a massive
dataset full of noise. We surface the right contracts, not all contracts.

**Speed matters.**
Pages must load fast. Searches must return instantly. If a feature makes the app
slow, it ships with a cache or does not ship at all.

---

## UX Philosophy

- One primary action per page
- Search is always visible
- Prioritized by default — most important thing first
- Progressive disclosure — simple view first, detail on demand
- Never require login to see if the product is useful (demo mode)
- Mobile-readable even if not mobile-optimized
- Error messages name the problem and suggest a fix

---

## Pricing Philosophy

**Per-company, not per-seat.**
A BD team of two should not pay twice what a team of one pays. We charge the
company, not the headcount.

**Monthly, cancel anytime.**
No annual lock-in at launch. Annual discounts come after product-market fit is
established.

**Transparent tiers:**

| Tier | Price | For |
|---|---|---|
| Starter | $99/mo | 1–3 users, core search + alerts |
| Professional | $199/mo | Up to 10 users, analytics + comparison |
| Team | $299/mo | Unlimited users, API access + exports |

**Free trial, no card required.**
Users must experience the value before they pay. A 14-day trial with full feature
access converts better than a freemium tier with crippled functionality.

---

## Data Philosophy

**Public data, private insight.**
Our underlying data comes from public sources: SAM.gov, FPDS, USAspending.gov.
Our value is the scoring, normalization, and intelligence layer on top of that
data — not the data itself.

**We do not own the customer's data.**
Saved searches, notes, watchlists, and capture workflows belong to the customer.
We make it easy to export everything.

**Freshness over completeness.**
A contract that expired yesterday matters. One that expired five years ago usually
does not. We prioritize recent, actionable data over historical depth.

**Transparency about sources.**
Every data point links to its source. Users should always be able to verify what
they see against the official record.

---

## AI Philosophy

**AI is a force multiplier, not a replacement.**
AI helps capture managers find opportunities faster and understand them more
deeply. It does not make bid/no-bid decisions. It does not write proposals.

**AI builds the product.**
The AI agent system in this repository builds and maintains the software. This
keeps development costs low and allows continuous improvement without a large
engineering team.

**AI must be auditable.**
Every AI-generated patch is saved in `patches/`, logged in `HANDOFF.md`, and
committed with a message that identifies it as AI-generated. Nothing is applied
silently.

**AI must be safe.**
The agent cannot push to GitHub. It cannot delete files. It cannot run arbitrary
shell commands. Every patch goes through a safety reviewer before it touches the
filesystem.

**Trust is earned incrementally.**
The AI agent starts with `DRY_RUN=true` by default. Apply permissions are granted
explicitly. The human is always in the loop on what goes to production.
