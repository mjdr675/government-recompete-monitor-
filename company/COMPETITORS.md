# COMPETITORS.md — Market Landscape

This document describes the competitive landscape as understood from project
knowledge and public information. Do not treat any figure here as authoritative —
verify pricing and features before using in sales or marketing materials.

Our target customer is a capture manager or BD director at a small to mid-sized
U.S. government contractor. We evaluate competitors through that lens.

---

## GovWin IQ (Deltek)

**What it is:**
The largest and most comprehensive federal business intelligence platform.
Owned by Deltek, which also makes ERP software for government contractors.
GovWin aggregates contract data, forecast data, agency contacts, and competitive
intelligence into a single platform used primarily by large contractors and
consulting firms.

**Strengths:**
- Massive data coverage: contracts, forecasts, budgets, agency relationships, and
  procurement history going back decades
- Forecasted opportunities: GovWin tracks pre-solicitation activity and agency
  intentions, not just awarded contracts
- Agency and program office contacts: human-curated intelligence that goes beyond
  what is available in public databases
- Deep integration with Deltek's ERP products (CostPoint, Vision) for large contractors
- Established brand recognition in the govcon market

**Weaknesses:**
- Price: Enterprise licenses run $800–$1,500+ per seat per year. A five-person BD
  team at a small contractor cannot justify this cost
- Complexity: The platform requires training, onboarding, and a dedicated analyst to
  extract value. It is not a tool a capture manager picks up in an afternoon
- Overbuilt for small contractors: Features designed for 10,000-person defense prime
  contractors are noise for a 75-person IT services firm
- Data freshness: Some forecast data is curated by human analysts and can lag behind
  actual procurement activity
- UI: Dated interface with a steep learning curve

**Opportunities for differentiation:**
- Price is the most obvious: we can deliver 20% of GovWin's value (the 20% that
  small contractors actually use) for 5% of the cost
- Simplicity: A capture manager at a small firm should be productive in under an hour
- Focus on recompetes: GovWin covers forecasts broadly; we go deep on expiring
  incumbent contracts, which is the highest-value opportunity type for small contractors

---

## GovTribe

**What it is:**
A more modern, API-first federal market intelligence platform. Covers contract
awards, agency spending, vendor profiles, and solicitation tracking. Often
described as a more accessible alternative to GovWin, with better search UX
and more transparent pricing.

**Strengths:**
- Better UX than GovWin: clean interface, fast search, easier to get started
- Strong API: developers and analysts can pull data programmatically
- Transparent pricing: plans start lower than GovWin and are visible on their website
- Vendor and agency profiles are well-structured and easy to navigate
- SAM.gov integration for solicitation tracking
- More accessible for smaller firms than GovWin

**Weaknesses:**
- Still expensive for very small firms ($200–$500+/month depending on tier)
- Forecast data is less deep than GovWin
- Recompete scoring is not a first-class concept — users must infer it from
  expiration dates and award histories themselves
- No specific focus on the small contractor workflow
- Limited collaborative features for teams

**Opportunities for differentiation:**
- Recompete score as a first-class concept: we make the prioritization explicit
  so a capture manager does not have to compute it manually
- Lower price point for the same core workflow
- Simpler product: we do not try to match GovTribe's breadth — we go deeper
  on the one workflow that matters most to small contractors

---

## Bloomberg Government (BGOV)

**What it is:**
A premium government intelligence platform from Bloomberg LP, aimed at lobbyists,
policy analysts, law firms, and large defense contractors. Combines legislative,
regulatory, and procurement intelligence into one subscription.

**Strengths:**
- Broadest coverage: legislative tracking, regulatory monitoring, and federal
  contracting data in a single subscription
- Premium brand and credibility in the Washington policy community
- Deep budget and appropriations analysis
- Excellent for tracking legislative and regulatory changes that affect procurement
- Used by organizations where a $10,000+ annual subscription is a rounding error

**Weaknesses:**
- Price: Starts at several thousand dollars per user per year; total cost often
  exceeds $20,000 for a small team
- Not built for capture managers: the primary audience is policy and legal, not BD
- Overkill: most of the product's value is irrelevant to a government contractor
  who just needs to find expiring contracts
- UI complexity: navigating the combined policy/contracting data requires training

**Opportunities for differentiation:**
- We are not competing with BGOV for its core audience (policy/legal)
- We offer something Bloomberg does not: a focused, affordable tool for the BD team
  at a company too small to budget five figures for market intelligence

---

## SAM.gov

**What it is:**
The official U.S. government procurement system maintained by the General Services
Administration. SAM.gov is the authoritative source for contract opportunities,
entity registration, exclusions, and award data. It is free and public.

**Strengths:**
- The authoritative source: all solicitations and awards originate here
- Free: no cost for basic search and data access
- Bulk data downloads: full FPDS data is available as CSV and via API
- Widely known and trusted by all procurement professionals
- Required reading: every contractor must monitor it regardless of what other
  tools they use

**Weaknesses:**
- Not a research tool: SAM.gov is designed for compliance and publication, not
  competitive intelligence
- Search is limited: full-text search works, but filtering by expiration date,
  value range, incumbent, or recompete likelihood requires significant manual effort
- No scoring or prioritization: results are unranked; users must decide what matters
- No historical context: understanding whether a contract has been re-competed
  before, or how long the incumbent has held it, requires external tools
- UI is government-grade: functional but not fast or pleasant to use
- No alerts: users must actively check rather than being notified of changes

**Opportunities for differentiation:**
- SAM.gov is a data source, not a competitor: we build on top of its public data
- We add the intelligence layer that SAM.gov deliberately does not provide:
  scoring, prioritization, alerts, and historical context
- We compete with the behavior of checking SAM.gov manually — and we win by being faster

---

## USAspending.gov

**What it is:**
The federal government's public database of spending data, maintained by the
Bureau of the Fiscal Service. Covers awards, sub-awards, and grants going back
many years. Provides transparency into how federal dollars are spent.

**Strengths:**
- Free and public
- Comprehensive historical depth — spending data going back to 2000+
- Good for understanding agency budget patterns and spending trends
- Visualizations of spending by agency, recipient, program, and geography
- API-accessible with well-documented endpoints
- Useful for market sizing and historical research

**Weaknesses:**
- Designed for transparency and accountability, not opportunity identification
- Data lags: award data can be 30–90 days behind actual transactions
- No recompete or solicitation tracking
- No forecasting: shows what was spent, not what will be spent
- UI is not designed for rapid contract discovery
- No prioritization: same problem as SAM.gov — volume without intelligence

**Opportunities for differentiation:**
- USAspending is a data enrichment source, not a competitor: agency spend history
  from USAspending can inform our recompete scores and agency intelligence profiles
- We can surface USAspending-derived insights (vendor win rate, agency spending
  trends) in a way that is actionable for a capture manager

---

## Federal Procurement Data System (FPDS)

**What it is:**
The primary federal procurement data repository maintained by the GSA. FPDS
contains detailed records of all federal contract actions — awards, modifications,
terminations, and options. It is the source of record that most federal market
intelligence tools, including SAM.gov and USAspending, draw from.

**Strengths:**
- Most detailed and comprehensive contract action data available
- Direct access to raw award records including modification history
- Free via API and bulk download
- The authoritative source for contract-level detail (NAICS codes, PSC codes,
  competition type, set-aside type, etc.)
- Data is very granular — modification records show option exercises and extensions

**Weaknesses:**
- Extremely technical: designed for procurement officials and data analysts,
  not BD teams
- UI is essentially unusable for discovery or research
- No scoring, alerting, or intelligence layer
- Requires significant data engineering to extract actionable insights
- Field names and codes require procurement expertise to interpret correctly

**Opportunities for differentiation:**
- FPDS is a foundational data source, not a competitor
- The opportunity is in interpretation: turning raw FPDS modification records into
  signals like "this contract has been extended 3 times — recompete is likely soon"
- We already ingest FPDS-derived data via SAM.gov's API; richer FPDS integration
  (direct modification history, option exercise tracking) is a Phase 3 feature

---

## Competitive Summary

| Product | Audience | Price/yr | Recompete focus | Our advantage |
|---|---|---|---|---|
| GovWin IQ | Large contractors | $800–$1,500+/seat | No | Price + simplicity |
| GovTribe | Mid-size contractors | $2,400–$6,000+/co | No | Price + recompete score |
| Bloomberg Gov | Policy/legal | $10,000+/seat | No | Not competing |
| SAM.gov | Everyone | Free | No | Speed + intelligence layer |
| USAspending | Researchers | Free | No | Not competing |
| FPDS | Data analysts | Free | No | Not competing |
| **This product** | Small contractors | **$1,200–$3,600/co** | **Yes** | |

**The white space:**
No product on the market is built specifically for small government contractors
with recompete intelligence as the primary use case at an affordable price point.
GovWin and GovTribe serve the use case but are priced for larger organizations.
The free government tools (SAM.gov, FPDS, USAspending) provide the data but
none of the intelligence. That gap is our market.
