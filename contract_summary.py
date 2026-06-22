"""Customer-facing contract summary helpers (Main product lane).

Presentation logic for the contract detail page — kept OUT of recompete_report.py
(Data lane: ingest/scoring) so the two lanes don't co-edit the same module. Pure
functions over already-stored fields only: no DB, no external/AI calls.
"""


def next_step(days_remaining, priority=None):
    """Plain-English recompete timing + recommended next action.

    Pure function using existing fields only (no DB, no external/AI calls). Turns
    ``days_remaining`` into actionable guidance for a contractor; ``priority`` (the
    CRITICAL/HIGH/… tier) adds a short urgency nudge. Returns a dict with keys
    ``timing``, ``detail`` and ``action``.
    """
    try:
        d = int(days_remaining) if days_remaining is not None else None
    except (ValueError, TypeError):
        d = None

    if d is None:
        timing = "Timing unknown"
        detail = ("No period-of-performance end date is on file for this contract, so the "
                  "recompete window can't be estimated.")
        action = "Confirm the contract's end date on SAM.gov, then set a reminder to track the recompete."
    elif d <= 0:
        timing = "Expired"
        detail = ("This contract's period of performance has ended — the follow-on may already "
                  "be solicited or awarded.")
        action = "Search SAM.gov for the recompete/follow-on and confirm whether it is still open."
    elif d <= 180:
        timing = "Expiring within ~6 months"
        detail = ("Recompete solicitations usually post before the incumbent contract ends, so "
                  "the RFP is likely imminent or already out.")
        action = "Confirm the active solicitation now and prepare your proposal — this is a near-term bid."
    elif d <= 365:
        timing = "Expiring within a year"
        detail = ("This is the positioning window: agencies shape requirements months before "
                  "the solicitation is released.")
        action = "Engage the agency, line up teaming/past-performance, and watch for the draft RFP."
    else:
        timing = "More than a year out"
        detail = "Early stage — there is plenty of runway before this contract is recompeted."
        action = "Track it and build relevant past performance; revisit as the end date approaches."

    if d is not None and 0 < d and (priority or "").upper() in ("CRITICAL", "HIGH"):
        action = "High-priority opportunity — " + action

    return {"timing": timing, "detail": detail, "action": action}
