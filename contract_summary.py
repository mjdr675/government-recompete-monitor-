"""Customer-facing contract summary helpers (Main product lane).

Presentation logic for the contract detail page — kept OUT of recompete_report.py
(Data lane: ingest/scoring) so the two lanes don't co-edit the same module. Pure
functions over already-stored fields only: no DB, no external/AI calls.
"""


def _safe_int(v):
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


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


def recommended_action(row):
    """Deterministic next-best-action for a contract row dict.

    Returns {"action": short imperative, "explanation": 1-2 sentence rationale}.
    Uses only already-stored fields — no DB, no external/AI calls.
    """
    days = _safe_int(row.get("days_remaining"))
    score = _safe_int(row.get("recompete_score"))
    priority = (row.get("priority") or "").upper()
    sol_id = (row.get("solicitation_id") or "").strip()
    value = float(row.get("value") or 0)
    comp_type = (row.get("competition_type") or "").upper()

    if days is not None and days <= 0:
        return {
            "action": "Search for the follow-on award",
            "explanation": "This contract's period of performance has ended. The follow-on procurement may already be posted on SAM.gov.",
        }

    if sol_id:
        return {
            "action": "Review the active solicitation and prepare your proposal",
            "explanation": "A solicitation is already on file for this contract. Confirm the due date on SAM.gov and begin your response.",
        }

    if days is not None and days <= 30:
        return {
            "action": "Begin capture planning immediately",
            "explanation": "This contract expires within 30 days. A solicitation is likely imminent — check SAM.gov now for the active posting.",
        }

    if days is not None and days <= 90:
        return {
            "action": "Contact the contracting office",
            "explanation": "The recompete window is opening. Reaching out now lets you shape requirements before the solicitation is released.",
        }

    if days is not None and days <= 180 and score is not None and score >= 75:
        return {
            "action": "Begin capture planning",
            "explanation": "This high-scoring opportunity expires within 6 months. Start positioning now — solicitations often post before contract end.",
        }

    if days is not None and days <= 365:
        return {
            "action": "Build a teaming strategy",
            "explanation": "The recompete is within 12 months. Identify teaming partners, build past performance, and begin engaging the agency.",
        }

    if priority in ("CRITICAL", "HIGH"):
        return {
            "action": "Monitor for solicitation release",
            "explanation": "This is a high-priority contract. Set up SAM.gov alerts and check regularly for the recompete solicitation.",
        }

    if "FULL AND OPEN" in comp_type:
        return {
            "action": "Research the incumbent contractor",
            "explanation": "This contract was awarded under full and open competition, making it a strong recompete target. Studying the incumbent strengthens your bid.",
        }

    if value >= 1_000_000:
        return {
            "action": "Review similar historical awards",
            "explanation": "This is a significant-value contract. Research how similar awards were structured to inform your long-range bid strategy.",
        }

    return {
        "action": "Continue monitoring",
        "explanation": "This opportunity is not yet actionable. Set a reminder to revisit as the contract expiration approaches.",
    }


def why_it_matters(row):
    """Return a list of concise bullet strings explaining why this contract is valuable.

    Uses only already-stored fields — no DB, no external/AI calls. Always returns
    at least one bullet.
    """
    bullets = []
    value = float(row.get("value") or 0)
    days = _safe_int(row.get("days_remaining"))
    score = _safe_int(row.get("recompete_score"))
    priority = (row.get("priority") or "").upper()
    sol_id = (row.get("solicitation_id") or "").strip()
    agency = (row.get("agency") or "").upper()
    comp_type = (row.get("competition_type") or "").upper()

    if value >= 10_000_000:
        bullets.append(f"Very high contract value (${value:,.0f})")
    elif value >= 1_000_000:
        bullets.append(f"High estimated contract value (${value:,.0f})")

    if score is not None and score >= 90:
        bullets.append(f"Very high opportunity score ({score}/100)")
    elif score is not None and score >= 75:
        bullets.append(f"High opportunity score ({score}/100)")

    if priority == "CRITICAL":
        bullets.append("Critical priority — immediate action required")
    elif priority == "HIGH":
        bullets.append("High priority opportunity")

    if days is not None and 0 < days <= 90:
        bullets.append(f"Recompete expected very soon ({days} days remaining)")
    elif days is not None and 0 < days <= 365:
        bullets.append(f"Recompete expected within the year ({days} days remaining)")

    if sol_id:
        bullets.append("Solicitation information already on file")

    if any(k in agency for k in ("DEFENSE", "ARMY", "NAVY", "AIR FORCE", "MARINE")):
        bullets.append("Department of Defense — strategic agency")
    elif "VETERANS AFFAIRS" in agency:
        bullets.append("Department of Veterans Affairs — high-value contracting office")
    elif "HOMELAND SECURITY" in agency:
        bullets.append("Department of Homeland Security — strategic agency")

    if "FULL AND OPEN" in comp_type:
        bullets.append("Full and open competition — strong recompete target")

    if not bullets:
        bullets.append("Active government contract")

    return bullets


def contract_timeline(row):
    """Build a chronological list of known events from already-stored contract fields.

    Returns a list of dicts: {"date": "YYYY-MM-DD", "event": label, "type": kind}.
    Only includes entries with non-null dates. Sorted oldest-first.
    """
    events = []

    start = (row.get("start_date") or "").strip()
    if start:
        events.append({"date": start, "event": "Contract awarded", "type": "start"})

    updated = (row.get("updated_at") or "").strip()
    if updated:
        date_str = str(updated)[:10]
        if date_str != start:
            events.append({"date": date_str, "event": "Last updated in database", "type": "update"})

    end = (row.get("end_date") or "").strip()
    days = _safe_int(row.get("days_remaining"))
    if end:
        label = "Contract expired" if (days is not None and days <= 0) else "Contract expires"
        events.append({"date": end, "event": label, "type": "end"})

    events.sort(key=lambda e: e["date"])
    return events
