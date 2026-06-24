"""
apply_window.py

Logic for assessing whether a contract is realistically applyable by a small
business, and where it falls in the federal contracting preparation timeline.

Federal contracting reality:
  - The agency posts the recompete solicitation 3-12 months before the current
    contract expires.
  - Proposal deadlines are typically 30-60 days after the solicitation drops.
  - Awards are usually made weeks before the incumbent contract ends.

So a contract is only worth pursuing if there is enough runway left to (a) wait
for/find the solicitation, and (b) prepare and submit a competitive proposal.
A contract expiring in 20 days is effectively un-winnable for a new bidder —
the solicitation has already closed.

This module turns days_remaining into a plain-language "stage" and a boolean
"applyable" flag the rest of the app can filter and display on.
"""

# Minimum runway (in days) for a contract to be realistically applyable.
# Below this, the solicitation has almost certainly already closed.
MIN_APPLY_DAYS = 60

# The outer edge of the useful preparation window. Beyond this the recompete is
# real but very early — worth watching, not yet actionable.
MAX_PREP_DAYS = 540  # ~18 months

# The "sweet spot" — enough time to prepare a strong proposal, close enough that
# the solicitation is likely to drop soon. This is the window we want MOST
# contracts shown to the user to fall into.
SWEET_SPOT_MIN = 90
SWEET_SPOT_MAX = 365


def _coerce_days(days_remaining):
    try:
        return int(days_remaining)
    except (TypeError, ValueError):
        return None


def apply_stage(days_remaining):
    """Return a (stage_key, label, detail) tuple describing where a contract
    sits in the preparation timeline, based on days remaining on the incumbent
    contract.

    Stages:
      too_late    — < MIN_APPLY_DAYS: solicitation has closed; can't bid
      submit_now  — 60-90 days: solicitation likely open; submit your proposal
      prepare     — 90-365 days: sweet spot; build your proposal
      research    — 365-540 days: early; research and build relationships
      watch       — > 540 days: very early; monitor for now
      unknown     — no/invalid days value
    """
    d = _coerce_days(days_remaining)
    if d is None:
        return ("unknown", "Timing unknown", "No expiration date on file for this contract.")
    if d < MIN_APPLY_DAYS:
        return (
            "too_late",
            "Likely closed",
            "This contract expires too soon to realistically prepare and submit a "
            "competitive proposal. The solicitation has probably already closed.",
        )
    if d < SWEET_SPOT_MIN:
        return (
            "submit_now",
            "Submit now",
            "The recompete solicitation is likely open now. If you want this one, "
            "you need to be preparing and submitting your proposal immediately.",
        )
    if d <= SWEET_SPOT_MAX:
        return (
            "prepare",
            "Prepare your bid",
            "This is the sweet spot. The solicitation will likely drop in the coming "
            "months. Now is the time to build your proposal, line up past performance, "
            "and get your pricing ready.",
        )
    if d <= MAX_PREP_DAYS:
        return (
            "research",
            "Research & position",
            "Plenty of runway. Use this time to research the agency, attend industry "
            "days, build relationships with the contracting office, and get your SAM.gov "
            "registration and certifications in order.",
        )
    return (
        "watch",
        "Watch",
        "Very early. Keep an eye on this one — the recompete solicitation is still a "
        "long way off.",
    )


def is_applyable(days_remaining):
    """True when a contract has enough runway left to realistically bid on."""
    d = _coerce_days(days_remaining)
    if d is None:
        return False
    return MIN_APPLY_DAYS <= d <= MAX_PREP_DAYS


def in_sweet_spot(days_remaining):
    """True when a contract falls in the ideal preparation window."""
    d = _coerce_days(days_remaining)
    if d is None:
        return False
    return SWEET_SPOT_MIN <= d <= SWEET_SPOT_MAX
