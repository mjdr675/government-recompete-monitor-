"""Customer-facing contract summary helpers (Main product lane).

Presentation logic for the contract detail page — kept OUT of recompete_report.py
(Data lane: ingest/scoring) so the two lanes don't co-edit the same module. Pure
functions over already-stored fields only: no DB, no external/AI calls.
"""

from domain.policies.contract_ranking import rank_contracts


# ---------------------------------------------------------------------------
# Per-contract recompete score breakdown (Contract Intelligence lane)
#
# Mirrors the formula in recompete_report.py without importing it — that
# module is owned by the data-pipeline lane and may be unavailable at
# import time in test environments. Keeping a parallel read-only copy here
# lets the intelligence layer explain scores without coupling to ingest code.
# ---------------------------------------------------------------------------

_COMPETITION_SCORES = {
    "FULL AND OPEN COMPETITION": (40, "Full & Open Competition — any vendor may bid"),
    "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES": (35, "Full & Open after exclusion of sources"),
    "COMPETED UNDER SAP": (30, "Competed under Simplified Acquisition Procedures"),
}


def _competition_component(competition_type: str) -> dict:
    ct = (competition_type or "").upper().strip()
    pts, label = _COMPETITION_SCORES.get(ct, (0, "Limited / no competition"))
    return {
        "name": "Competition type",
        "earned": pts,
        "max": 40,
        "detail": label or competition_type or "Not specified",
    }


def _value_component(value) -> dict:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0

    if v >= 10_000_000:
        pts, label = 35, f"${v:,.0f} — very high value"
    elif v >= 5_000_000:
        pts, label = 25, f"${v:,.0f} — high value"
    elif v >= 2_000_000:
        pts, label = 15, f"${v:,.0f} — mid-range value"
    elif v >= 1_000_000:
        pts, label = 10, f"${v:,.0f} — above $1M threshold"
    else:
        pts, label = 0, f"${v:,.0f} — below $1M scoring threshold" if v > 0 else "Value not recorded"

    return {"name": "Contract value", "earned": pts, "max": 35, "detail": label}


def _timing_component(days_remaining) -> dict:
    """Mirror the _days_score thresholds from recompete_report for the explainer.

    Maximum points (25) are earned at 365–540 days — the best pursuit window.
    Imminent expiry earns 0 because a new challenger cannot realistically bid.
    """
    try:
        d = int(days_remaining) if days_remaining is not None else None
    except (TypeError, ValueError):
        d = None

    if d is None:
        return {"name": "Time remaining", "earned": 0, "max": 25, "detail": "End date not recorded"}
    if d <= 0:
        return {"name": "Time remaining", "earned": 0, "max": 25, "detail": "Expired — follow-on may already be posted"}
    if d < 30:
        return {"name": "Time remaining", "earned": 0, "max": 25, "detail": f"{d} days — too late for new challengers (solicitation likely closed)"}
    if d < 90:
        return {"name": "Time remaining", "earned": 5, "max": 25, "detail": f"{d} days — urgent/late-stage; limited time to engage"}
    if d < 180:
        return {"name": "Time remaining", "earned": 10, "max": 25, "detail": f"{d} days — active pursuit window"}
    if d < 270:
        return {"name": "Time remaining", "earned": 15, "max": 25, "detail": f"{d} days — proposal and team preparation window"}
    if d < 365:
        return {"name": "Time remaining", "earned": 20, "max": 25, "detail": f"{d} days — opportunity shaping window"}
    if d <= 540:
        return {"name": "Time remaining", "earned": 25, "max": 25, "detail": f"{d} days — best pursuit window (maximum points)"}
    return {"name": "Time remaining", "earned": 5, "max": 25, "detail": f"{d} days — early monitoring stage; revisit as it approaches"}


def _bonus_components(row) -> list[dict]:
    bonuses = []

    agency = (row.get("agency") or "").upper()
    if "DEFENSE" in agency:
        bonuses.append({"name": "Agency bonus", "earned": 5, "max": 5, "detail": "Department of Defense — priority agency"})
    elif "VETERANS AFFAIRS" in agency:
        bonuses.append({"name": "Agency bonus", "earned": 4, "max": 5, "detail": "Department of Veterans Affairs — priority agency"})
    elif "HOMELAND SECURITY" in agency:
        bonuses.append({"name": "Agency bonus", "earned": 3, "max": 5, "detail": "Department of Homeland Security — priority agency"})
    else:
        bonuses.append({"name": "Agency bonus", "earned": 0, "max": 5, "detail": "Agency not in priority list"})

    if row.get("solicitation_id"):
        bonuses.append({"name": "Solicitation on file", "earned": 5, "max": 5, "detail": f"Solicitation ID: {row['solicitation_id']}"})
    else:
        bonuses.append({"name": "Solicitation on file", "earned": 0, "max": 5, "detail": "No solicitation ID recorded"})

    office = (row.get("awarding_office") or "").upper()
    _priority_offices = ["697DCK", "NETWORK CONTRACT OFFICE", "DEFENSE HEALTH AGENCY", "NAVFAC", "W40M"]
    matched_office = next((o for o in _priority_offices if o in office), None)
    if matched_office:
        bonuses.append({"name": "Office signal", "earned": 5, "max": 5, "detail": f"Priority contracting office: {row.get('awarding_office')}"})
    else:
        bonuses.append({"name": "Office signal", "earned": 0, "max": 5, "detail": "Awarding office not in priority list"})

    return bonuses


def recompete_score_breakdown(row) -> dict | None:
    """Return a per-contract breakdown of the recompete score components.

    Pure function over the stored contract row dict — no DB, no external/AI calls.
    Returns None when no row is provided. Otherwise returns:

        {
          "total": int,               # sum of all component earned points
          "components": [             # ordered list, largest-weight first
            {"name": str, "earned": int, "max": int, "detail": str},
            ...
          ],
        }

    The components mirror the formula in recompete_report.recompete_score() exactly.
    Bonus components (agency, solicitation, office) are grouped last.
    """
    if row is None:
        return None

    primary = [
        _competition_component(row.get("competition_type")),
        _value_component(row.get("value")),
        _timing_component(row.get("days_remaining")),
    ]
    bonuses = _bonus_components(row)
    components = primary + bonuses

    total = sum(c["earned"] for c in components)
    return {"total": total, "components": components}


# ---------------------------------------------------------------------------
# Dashboard row enrichment helpers (Contract Intelligence lane)
#
# Pure functions over a contract row dict — no DB, no external/AI calls.
# Used by analytics.personalized_for_business() to attach richer display
# fields to each matched opportunity before the dashboard template renders.
# ---------------------------------------------------------------------------

def work_label(row) -> str:
    """Plain-English description of the work this contract covers.

    Prefers the stored ``category`` field (already human-readable), falls back
    to a truncated ``description``, and finally returns "Contract services" so
    there is always a non-empty label.
    """
    cat = (row.get("category") or "").strip()
    if cat and cat.lower() not in ("other", "unknown", ""):
        return cat

    desc = (row.get("description") or "").strip()
    if desc:
        if len(desc) <= 55:
            return desc
        truncated = desc[:55]
        last_space = truncated.rfind(" ")
        return (truncated[:last_space] if last_space > 20 else truncated) + "…"

    return "Contract services"


def location_label(row) -> str:
    """City + state, state alone, or honest fallback.

    Checks ``performance_city`` / ``place_of_performance_city`` (raw-json
    derived fields) first, then ``place_of_performance_state`` (direct column).
    Returns "Location not listed" rather than empty string when no data exists.
    """
    city = (
        row.get("performance_city")
        or row.get("place_of_performance_city")
        or ""
    ).strip()
    state = (row.get("place_of_performance_state") or "").strip()

    if city and state:
        return f"{city}, {state}"
    if state:
        return state
    return "Location not listed"


def contract_length_label(row) -> str:
    """Human-readable contract period derived from start and end dates.

    Returns month/year ranges when both dates are available and parseable.
    Falls back to the end-year alone, then "Length not listed".
    """
    from datetime import date as _date
    start_raw = (row.get("start_date") or "").strip()
    end_raw = (row.get("end_date") or "").strip()

    if not start_raw and not end_raw:
        return "Length not listed"

    try:
        if start_raw and end_raw:
            s = _date.fromisoformat(start_raw[:10])
            e = _date.fromisoformat(end_raw[:10])
            months = (e.year - s.year) * 12 + (e.month - s.month)
            if months <= 0:
                return f"{s.year}–{e.year}" if s.year != e.year else str(s.year)
            if months == 12:
                return "1 year"
            if months < 12:
                return f"{months} months"
            years = months // 12
            rem = months % 12
            if rem == 0:
                return f"{years} year{'s' if years > 1 else ''}"
            return f"{s.year}–{e.year}"
        if end_raw:
            return _date.fromisoformat(end_raw[:10]).strftime("%b %Y")
    except (ValueError, TypeError):
        pass

    return "Length not listed"


def action_signal(row) -> str:
    """Short pass/click signal for a dashboard row.

    Returns a concise imperative label that helps users decide whether to open
    the contract page. Based only on stored fields — no profile dependency.
    """
    try:
        days = int(row["days_remaining"]) if row.get("days_remaining") is not None else None
    except (TypeError, ValueError):
        days = None

    try:
        score = int(row["recompete_score"]) if row.get("recompete_score") is not None else None
    except (TypeError, ValueError):
        score = None

    priority = (row.get("priority") or "").upper()

    if days is not None and days <= 30:
        return "Review: urgent expiry"
    if score is not None and score >= 75:
        return "Click: high fit"
    if priority in ("CRITICAL", "HIGH"):
        return "Click: high priority"
    return "Review"


def match_summary(row, reasons: list[str]) -> str:
    """Rich one-line match context for the dashboard "Why it matches" cell.

    Takes the existing ``reasons`` list built by ``personalized_for_business``
    (e.g. ``["Work in TX", "IT category"]``) and formats it alongside the
    work label so the user sees something meaningful instead of a bare
    "Department of Defense contract" agency string.

    The work label is prepended only when it adds context beyond what the
    reasons already describe.  Bare "Agency contract" reasons are reformatted
    to "Preferred agency" so the agency name does not become the headline.
    """
    wl = work_label(row)

    formatted = []
    for r in reasons:
        if r.endswith(" contract"):
            formatted.append("Preferred agency")
        else:
            formatted.append(r)

    if not formatted:
        return wl if wl != "Contract services" else "Matches your profile"

    reason_text = " · ".join(formatted)
    if wl and wl != "Contract services" and wl.lower() not in reason_text.lower():
        return f"{wl} · {reason_text}"
    return reason_text


def _safe_int(v):
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def pursuit_stage(days_remaining) -> dict:
    """Classify a contract's actionability stage for a new challenger.

    Returns a dict with keys: stage_key (str), label (str), description (str),
    actionable (bool — True when there is realistic time to pursue).

    Stages mirror the _days_score thresholds so that score and stage labels are
    always consistent. Maximum scoring window (365–540 days) maps to "best_window".
    """
    try:
        d = int(days_remaining) if days_remaining is not None else None
    except (TypeError, ValueError):
        d = None

    if d is None:
        return {
            "stage_key": "unknown",
            "label": "Timing Unknown",
            "description": "No expiration date on file. Confirm on SAM.gov before pursuing.",
            "actionable": False,
        }
    if d <= 0:
        return {
            "stage_key": "expired",
            "label": "Expired",
            "description": "This contract has ended. Research whether the follow-on has been awarded or solicited.",
            "actionable": False,
        }
    if d < 30:
        return {
            "stage_key": "too_late",
            "label": "Too Late / Monitor Only",
            "description": (
                "Under 30 days remaining — the solicitation has almost certainly closed "
                "for new challengers. Track the follow-on award instead."
            ),
            "actionable": False,
        }
    if d < 90:
        return {
            "stage_key": "urgent",
            "label": "Urgent / Late Stage",
            "description": (
                "Under 90 days remaining — too late to start a new pursuit unless you are "
                "already engaged. Begin researching the follow-on solicitation."
            ),
            "actionable": False,
        }
    if d < 180:
        return {
            "stage_key": "active_pursuit",
            "label": "Active Pursuit",
            "description": (
                "90–180 days remaining — proposal preparation should be underway. "
                "Confirm solicitation status on SAM.gov and begin writing."
            ),
            "actionable": True,
        }
    if d < 270:
        return {
            "stage_key": "prepare",
            "label": "Prepare Proposal & Team",
            "description": (
                "180–270 days remaining — proposal and teaming window. "
                "Line up partners, finalize past performance, and get pricing ready."
            ),
            "actionable": True,
        }
    if d < 365:
        return {
            "stage_key": "shape",
            "label": "Shape Opportunity",
            "description": (
                "270–365 days remaining — engage the agency now to help shape requirements "
                "before the solicitation drops. Attend industry days."
            ),
            "actionable": True,
        }
    if d <= 540:
        return {
            "stage_key": "best_window",
            "label": "Best Pursuit Window",
            "description": (
                "365–540 days remaining — ideal capture window. Enough runway to build "
                "relationships, position your capabilities, and prepare a strong proposal."
            ),
            "actionable": True,
        }
    return {
        "stage_key": "watch",
        "label": "Watch / Early Stage",
        "description": (
            "More than 18 months out — keep an eye on this one. "
            "Revisit when it enters the best pursuit window (under 540 days)."
        ),
        "actionable": False,
    }


def next_step(days_remaining, priority=None):
    """Plain-English recompete timing + recommended next action.

    Uses the pursuit_stage framework so timing labels are consistent across the
    app. Returns a dict with keys ``timing``, ``detail`` and ``action``.
    """
    stage = pursuit_stage(days_remaining)

    timing_map = {
        "unknown":      "Timing unknown",
        "expired":      "Expired",
        "too_late":     "Too Late / Monitor Only",
        "urgent":       "Urgent / Late Stage",
        "active_pursuit": "Expiring within ~6 months",
        "prepare":      "Prepare Proposal & Team",
        "shape":        "Shape Opportunity",
        "best_window":  "Best Pursuit Window",
        "watch":        "More than a year out",
    }
    action_map = {
        "unknown":      "Confirm the contract's end date on SAM.gov, then set a reminder to track the recompete.",
        "expired":      "Search SAM.gov for the recompete/follow-on and confirm whether it is still open.",
        "too_late":     "Monitor SAM.gov for the follow-on award. Do not invest pursuit resources in this cycle.",
        "urgent":       "Check SAM.gov for the active solicitation immediately. Only proceed if already engaged.",
        "active_pursuit": "Confirm the active solicitation now and prepare your proposal — this is a near-term bid.",
        "prepare":      "Begin writing your proposal, finalize teaming partners, and watch for the solicitation drop.",
        "shape":        "Engage the agency, line up teaming/past-performance, and watch for the draft RFP.",
        "best_window":  "This is the ideal time to start capture — engage the agency and position your capabilities.",
        "watch":        "Track it and build relevant past performance; revisit when it enters the best pursuit window.",
    }

    timing = timing_map.get(stage["stage_key"], stage["label"])
    detail = stage["description"]
    action = action_map.get(stage["stage_key"], stage["description"])

    try:
        d = int(days_remaining) if days_remaining is not None else None
    except (ValueError, TypeError):
        d = None

    if d is not None and d > 0 and (priority or "").upper() in ("CRITICAL", "HIGH"):
        action = "High-priority opportunity — " + action

    return {"timing": timing, "detail": detail, "action": action}


def recommended_action(row):
    """Deterministic next-best-action for a contract row dict.

    Returns {"action": short imperative, "explanation": 1-2 sentence rationale,
             "too_late": bool}.
    Uses only already-stored fields — no DB, no external/AI calls.

    Actions are stage-aware: near-expiry alone is not treated as the most urgent
    signal — a contract expiring in 10 days is less actionable for a new challenger
    than one expiring in 400 days.
    """
    days = _safe_int(row.get("days_remaining"))
    score = _safe_int(row.get("recompete_score"))
    priority = (row.get("priority") or "").upper()
    sol_id = (row.get("solicitation_id") or "").strip()
    value = float(row.get("value") or 0)
    comp_type = (row.get("competition_type") or "").upper()

    stage = pursuit_stage(days)
    stage_key = stage["stage_key"]

    if stage_key == "expired":
        return {
            "action": "Search for the follow-on award",
            "explanation": "This contract's period of performance has ended. The follow-on procurement may already be posted on SAM.gov.",
            "too_late": True,
        }

    if stage_key == "too_late":
        return {
            "action": "Monitor for the follow-on solicitation",
            "explanation": (
                "With under 30 days remaining the solicitation window has almost certainly "
                "closed for new challengers. Track SAM.gov for the follow-on award."
            ),
            "too_late": True,
        }

    if stage_key == "urgent":
        if sol_id:
            return {
                "action": "Review the active solicitation immediately",
                "explanation": "A solicitation is on file and the contract expires within 90 days — confirm the deadline on SAM.gov and submit now.",
                "too_late": False,
            }
        return {
            "action": "Check SAM.gov for the active solicitation",
            "explanation": (
                "This contract expires within 90 days. Only proceed if you are already "
                "engaged — starting a new pursuit at this stage is very late."
            ),
            "too_late": False,
        }

    if sol_id:
        return {
            "action": "Review the active solicitation and prepare your proposal",
            "explanation": "A solicitation is already on file for this contract. Confirm the due date on SAM.gov and begin your response.",
            "too_late": False,
        }

    if stage_key == "active_pursuit":
        return {
            "action": "Begin proposal preparation",
            "explanation": "The recompete window is open (90–180 days remaining). Draft your proposal, line up past performance, and watch for the solicitation.",
            "too_late": False,
        }

    if stage_key == "prepare":
        return {
            "action": "Build your proposal and teaming strategy",
            "explanation": "You are in the proposal preparation window (180–270 days). Identify teaming partners and begin pricing.",
            "too_late": False,
        }

    if stage_key == "shape":
        return {
            "action": "Engage the agency to shape requirements",
            "explanation": "With 270–365 days remaining you can still influence the solicitation. Attend industry days and introduce your capabilities.",
            "too_late": False,
        }

    if stage_key == "best_window":
        return {
            "action": "Start capture planning now",
            "explanation": (
                "This contract is in the best pursuit window (365–540 days remaining) — "
                "ideal timing to build relationships, develop win themes, and position your team."
            ),
            "too_late": False,
        }

    if "FULL AND OPEN" in comp_type:
        return {
            "action": "Research the incumbent contractor",
            "explanation": "This contract was awarded under full and open competition, making it a strong recompete target. Studying the incumbent strengthens your long-range bid strategy.",
            "too_late": False,
        }

    if value >= 1_000_000:
        return {
            "action": "Review similar historical awards",
            "explanation": "This is a significant-value contract more than 18 months out. Research how similar awards were structured to inform your bid strategy.",
            "too_late": False,
        }

    return {
        "action": "Continue monitoring",
        "explanation": "This opportunity is not yet actionable. Set a reminder to revisit when it approaches the best pursuit window.",
        "too_late": False,
    }


def why_it_matters(row):
    """Return a list of concise bullet strings explaining why this contract is valuable.

    Uses only already-stored fields — no DB, no external/AI calls. Always returns
    at least one bullet. Timing bullets reflect pursuit quality, not urgency:
    being in the best pursuit window is a positive signal; imminent expiry is not.
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
        bullets.append("Critical priority — high-fit opportunity with actionable timing")
    elif priority == "HIGH":
        bullets.append("High priority opportunity")

    stage = pursuit_stage(days)
    stage_key = stage["stage_key"]

    if stage_key == "best_window":
        bullets.append(f"Best pursuit window — {days} days remaining, ideal time to engage")
    elif stage_key == "shape":
        bullets.append(f"Opportunity shaping window — {days} days to position before solicitation")
    elif stage_key == "prepare":
        bullets.append(f"Proposal preparation window — {days} days remaining")
    elif stage_key == "active_pursuit":
        bullets.append(f"Active pursuit window — {days} days remaining, proposal should be underway")
    elif stage_key in ("too_late", "urgent"):
        bullets.append(f"Late stage — {days} days remaining; limited runway for new challengers")
    elif stage_key == "expired":
        bullets.append("Expired — research the follow-on award on SAM.gov")

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

    naics_desc = (row.get("naics_description") or "").strip()
    naics_code = (row.get("naics_code") or "").strip()
    if naics_desc and naics_code:
        bullets.append(f"Industry sector: {naics_desc} (NAICS {naics_code})")
    elif naics_desc:
        bullets.append(f"Industry sector: {naics_desc}")

    psc_desc = (row.get("psc_description") or "").strip()
    if psc_desc:
        bullets.append(f"Product/service classification: {psc_desc}")

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


# ---------------------------------------------------------------------------
# Multi-contract comparison insights (Contract Intelligence Tools lane)
#
# Pure analytical synthesis over a set of already-fetched contract rows — no DB,
# no external/AI calls. Turns the raw side-by-side compare table into a
# decision aid: which contract to pursue first, and which leads on value,
# score, and recompete timing.
# ---------------------------------------------------------------------------

def _contract_label(row):
    return row.get("award_id") or row.get("internal_id")


def compare_insights(rows):
    """Return deterministic analytical highlights across compared contracts.

    ``rows`` is a list of contract row dicts. Returns None for fewer than two
    rows (insights need something to compare). Otherwise returns a dict:

        {
          "recommended": {label, internal_id, reason},
          "highlights": [ {title, label, internal_id, detail}, ... ],
        }

    The recommended pick maximises recompete score, breaking ties by the
    soonest active recompete, then by highest value — all from stored fields.
    """
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return None

    def score_of(r):
        return _safe_int(r.get("recompete_score")) or 0

    def value_of(r):
        try:
            return float(r.get("value") or 0)
        except (TypeError, ValueError):
            return 0.0

    def active_days(r):
        d = _safe_int(r.get("days_remaining"))
        return d if (d is not None and d > 0) else None

    highlights = []

    # Highest value
    top_value = max(rows, key=value_of)
    if value_of(top_value) > 0:
        highlights.append({
            "title": "Highest value",
            "label": _contract_label(top_value),
            "internal_id": top_value.get("internal_id"),
            "detail": "${:,.0f}".format(value_of(top_value)),
        })

    # Best recompete score
    top_score = max(rows, key=score_of)
    if score_of(top_score) > 0:
        highlights.append({
            "title": "Best recompete score",
            "label": _contract_label(top_score),
            "internal_id": top_score.get("internal_id"),
            "detail": "{}/100".format(score_of(top_score)),
        })

    # Soonest active recompete (smallest positive days_remaining)
    active = [r for r in rows if active_days(r) is not None]
    if active:
        soonest = min(active, key=active_days)
        highlights.append({
            "title": "Soonest recompete",
            "label": _contract_label(soonest),
            "internal_id": soonest.get("internal_id"),
            "detail": "{} days remaining".format(active_days(soonest)),
        })

    # Recommended pick: highest score, then soonest active expiry, then value.
    # Ordering policy lives in the shared domain module so pipeline/search/
    # recommendation ranking can reuse the exact same rule.
    best = rank_contracts(rows)[0]
    reason_parts = []
    if score_of(best) > 0:
        reason_parts.append("highest recompete score ({}/100)".format(score_of(best)))
    bd = active_days(best)
    if bd is not None:
        reason_parts.append("recompete in {} days".format(bd))
    if value_of(best) > 0:
        reason_parts.append("${:,.0f} value".format(value_of(best)))
    reason = "Strongest opportunity by " + ", ".join(reason_parts) + "." if reason_parts \
        else "Best available option among the compared contracts."

    return {
        "recommended": {
            "label": _contract_label(best),
            "internal_id": best.get("internal_id"),
            "reason": reason,
        },
        "highlights": highlights,
    }


# ---------------------------------------------------------------------------
# Recent Updates feed (Auto Contract Updates lane)
#
# Pure presentation over a contract_field_changes row dict (no DB / AI). Turns a
# stored field-level change into a compact, human-readable dashboard feed item.
# Part of the authoritative (internal_id) contract_field_changes read path.
# ---------------------------------------------------------------------------

_UPDATE_FIELD_LABELS = {
    "value": "Value",
    "end_date": "Recompete date",
    "days_remaining": "Days remaining",
    "vendor": "Vendor",
    "competition_type": "Competition type",
    "recompete_score": "Recompete score",
    "priority": "Priority",
}


def _format_update_value(field, raw):
    """Render a stored old/new value for display ('—' when blank)."""
    if raw is None or raw == "":
        return "—"
    if field == "value":
        try:
            return "${:,.0f}".format(float(raw))
        except (TypeError, ValueError):
            return str(raw)
    return str(raw)


def format_contract_update(row):
    """Turn a contract_field_changes row into a display dict for the feed.

    Input keys used: field_name, change_kind, old_value, new_value, run_date,
    created_at, award_id, internal_id. Returns a dict with a human-readable
    ``headline`` plus the contract label, formatted old/new values, and the
    timestamp — everything the dashboard card needs, no template logic required.
    """
    field = row.get("field_name") or ""
    kind = (row.get("change_kind") or "").upper()
    label = _UPDATE_FIELD_LABELS.get(field, field.replace("_", " ").title() or "Field")

    if kind == "INCREASE":
        headline = f"{label} increased"
    elif kind == "DECREASE":
        headline = f"{label} decreased"
    elif kind == "SET":
        headline = f"{label} set"
    elif kind == "CLEARED":
        headline = f"{label} cleared"
    else:
        headline = f"{label} changed"

    return {
        "internal_id": row.get("internal_id"),
        "contract": row.get("award_id") or row.get("internal_id"),
        "headline": headline,
        "field_name": field,
        "change_kind": kind,
        "old_value": _format_update_value(field, row.get("old_value")),
        "new_value": _format_update_value(field, row.get("new_value")),
        "run_date": row.get("run_date"),
        "created_at": row.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Capture Brief — top-level intelligence for the contract detail page
#
# Pure functions: no DB, no external/AI calls. Uses only stored fields.
# ---------------------------------------------------------------------------

def score_data_confidence(row) -> dict:
    """How complete is the data backing the recompete score?

    Returns {level: HIGH|MEDIUM|LOW, missing: [field labels], note: str}.
    HIGH when all six key fields are present; MEDIUM for 1–2 absent;
    LOW for 3 or more missing (score/recommendation reliability is reduced).
    """
    key_fields = [
        ("description", "work description"),
        ("competition_type", "competition type"),
        ("value", "contract value"),
        ("days_remaining", "expiration date"),
        ("naics_code", "NAICS code"),
        ("vendor", "incumbent vendor"),
    ]
    missing = [label for field, label in key_fields if not row.get(field)]

    if not missing:
        return {"level": "HIGH", "missing": [], "note": "All key data fields are present."}
    if len(missing) <= 2:
        return {
            "level": "MEDIUM",
            "missing": missing,
            "note": f"Missing: {', '.join(missing)}. Score may be slightly understated.",
        }
    return {
        "level": "LOW",
        "missing": missing,
        "note": f"Incomplete record ({len(missing)} fields absent). Verify on SAM.gov before committing pursuit resources.",
    }


def capture_recommendation(row, biz_match_score=None) -> dict:
    """Top-level Pursue / Monitor / Pass verdict for a single contract.

    Combines recompete score, timing stage, competition type, value, and (when
    a business profile exists) the business match score into a single verdict.
    Every signal is returned so the UI can show the reasoning — no black box.

    Returns:
        verdict:    "PURSUE" | "MONITOR" | "PASS"
        confidence: "HIGH" | "MEDIUM" | "LOW"
        headline:   one-line rationale
        signals:    [{label, value, positive: True|False|None}]
        caution:    [str]  — counter-signals or caveats
    """
    score = _safe_int(row.get("recompete_score"))
    days = _safe_int(row.get("days_remaining"))
    comp_type = (row.get("competition_type") or "").upper()
    value = float(row.get("value") or 0)
    sol_id = (row.get("solicitation_id") or "").strip()

    stage = pursuit_stage(days)
    stage_key = stage["stage_key"]
    stage_actionable = stage["actionable"]

    signals = []
    caution = []

    # Signal: recompete score
    if score is not None:
        if score >= 75:
            signals.append({"label": "Opportunity score", "value": f"{score}/100", "positive": True})
        elif score >= 50:
            signals.append({"label": "Opportunity score", "value": f"{score}/100", "positive": None})
        else:
            signals.append({"label": "Opportunity score", "value": f"{score}/100", "positive": False})
            caution.append(f"Score {score}/100 is below the standard pursuit threshold (75)")

    # Signal: timing
    _timing_labels = {
        "best_window":    "Best pursuit window (12–18 months)",
        "shape":          "Opportunity shaping window",
        "prepare":        "Proposal preparation window",
        "active_pursuit": "Active pursuit window",
        "watch":          "Early monitoring — more than 18 months out",
        "urgent":         "Late stage — under 90 days",
        "too_late":       "Too late for new challengers",
        "expired":        "Contract expired",
        "unknown":        "Timing unknown",
    }
    timing_label = _timing_labels.get(stage_key, stage["label"])
    if stage_key in ("best_window", "shape", "prepare", "active_pursuit"):
        signals.append({"label": "Timing", "value": timing_label, "positive": True})
    elif stage_key in ("expired", "too_late"):
        signals.append({"label": "Timing", "value": timing_label, "positive": False})
        caution.append(stage["description"])
    else:
        signals.append({"label": "Timing", "value": timing_label, "positive": None})

    # Signal: competition type
    if "FULL AND OPEN" in comp_type:
        signals.append({"label": "Competition", "value": "Full & Open — any vendor may bid", "positive": True})
    elif "SAP" in comp_type or "SIMPLIFIED" in comp_type:
        signals.append({"label": "Competition", "value": "Simplified Acquisition", "positive": None})
    elif comp_type:
        signals.append({"label": "Competition", "value": comp_type.title(), "positive": None})
    else:
        signals.append({"label": "Competition", "value": "Not recorded", "positive": None})

    # Signal: contract value
    if value >= 1_000_000:
        signals.append({"label": "Contract value", "value": f"${value:,.0f}", "positive": True})
    elif value > 0:
        signals.append({"label": "Contract value", "value": f"${value:,.0f} (below $1M threshold)", "positive": None})
    else:
        signals.append({"label": "Contract value", "value": "Not recorded", "positive": None})
        caution.append("Contract value is missing — return-on-investment cannot be assessed")

    # Signal: business match (only when profile exists)
    if biz_match_score is not None:
        if biz_match_score >= 60:
            signals.append({"label": "Business match", "value": f"{biz_match_score}% match", "positive": True})
        elif biz_match_score >= 30:
            signals.append({"label": "Business match", "value": f"{biz_match_score}% match", "positive": None})
        else:
            signals.append({"label": "Business match", "value": f"{biz_match_score}% match", "positive": False})
            caution.append(f"Low business profile match ({biz_match_score}%) — verify capability alignment before investing pursuit time")

    # Signal: solicitation on file
    if sol_id:
        signals.append({"label": "Solicitation on file", "value": sol_id, "positive": True})

    # --- Verdict ---
    pos_count = sum(1 for s in signals if s["positive"] is True)
    neg_count = sum(1 for s in signals if s["positive"] is False)

    score_ok = score is not None and score >= 75
    biz_ok = biz_match_score is None or biz_match_score >= 40

    if stage_key in ("expired", "too_late"):
        verdict = "PASS"
        confidence = "HIGH"
        headline = "Too late for this pursuit cycle — watch for the follow-on solicitation"

    elif score is not None and score < 40:
        verdict = "PASS"
        confidence = "HIGH" if neg_count >= 2 else "MEDIUM"
        headline = f"Low opportunity score ({score}/100) — limited pursuit value"

    elif biz_match_score is not None and biz_match_score < 20:
        verdict = "PASS"
        confidence = "MEDIUM"
        headline = f"Poor business fit ({biz_match_score}% match) — focus resources on better-aligned opportunities"

    elif score_ok and stage_actionable and biz_ok:
        verdict = "PURSUE"
        if pos_count >= 3 and neg_count == 0:
            confidence = "HIGH"
        elif pos_count >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        if "FULL AND OPEN" in comp_type and score >= 75:
            headline = f"Strong recompete candidate — open competition, score {score}/100"
        elif value >= 5_000_000:
            headline = f"High-value opportunity — ${value:,.0f} in the active pursuit window"
        else:
            headline = f"Pursue now — score {score}/100 with {stage['label'].lower()} timing"

    else:
        verdict = "MONITOR"
        if neg_count > pos_count:
            confidence = "LOW"
        else:
            confidence = "MEDIUM"
        if stage_key == "watch":
            headline = "Too early to pursue — track and revisit in 6–12 months"
        elif score_ok and not stage_actionable:
            headline = f"Strong score ({score}/100) but timing not yet optimal — track closely"
        elif score is not None and 50 <= score < 75:
            headline = "Moderate opportunity — monitor until score or timing improves"
        else:
            headline = "Track this contract — not yet ready for active pursuit"

    # --- Confidence rationale (plain English) ---
    pos_labels = [s["label"].lower() for s in signals if s["positive"] is True]
    neg_labels = [s["label"].lower() for s in signals if s["positive"] is False]

    if confidence == "HIGH":
        if not neg_labels and pos_labels:
            cr = f"Confidence is HIGH: {', '.join(pos_labels[:3])} all point toward {verdict} with no counter-signals."
        elif neg_labels:
            cr = f"Confidence is HIGH: strong positive signals ({', '.join(pos_labels[:2])}) outweigh the {neg_labels[0]} concern."
        else:
            cr = f"Confidence is HIGH based on available data."
    elif confidence == "MEDIUM":
        if neg_labels and pos_labels:
            cr = f"Confidence is MEDIUM: {pos_labels[0]} supports {verdict}, but {neg_labels[0]} is a concern."
        elif neg_labels:
            cr = f"Confidence is MEDIUM: some signals are negative ({', '.join(neg_labels[:2])})."
        else:
            cr = "Confidence is MEDIUM: supporting signals exist but data is incomplete."
    else:
        cr = "Confidence is LOW: signals are mixed or incomplete. Verify on SAM.gov before committing pursuit resources."

    return {
        "verdict": verdict,
        "confidence": confidence,
        "confidence_rationale": cr,
        "headline": headline,
        "signals": signals,
        "caution": caution,
    }


def incumbent_intelligence(row) -> dict:
    """Analyze the incumbent contractor from stored contract fields.

    Returns a dict with hold duration, displacement difficulty, and UEI/CAGE
    identifiers. Displacement signal is derived from contract length and
    competition type — no external lookups.

    displacement_signal: "easy" | "medium" | "hard" | "unknown"
    """
    from datetime import date as _date

    name = (row.get("vendor") or "").strip() or None
    uei = (row.get("recipient_uei") or "").strip() or None
    cage_code = (row.get("cage_code") or "").strip() or None
    comp_type = (row.get("competition_type") or "").upper()

    # Hold duration from contract dates
    hold_months = None
    hold_label = "Unknown duration"
    start_raw = (row.get("start_date") or "").strip()
    end_raw = (row.get("end_date") or "").strip()
    if start_raw and end_raw:
        try:
            s = _date.fromisoformat(start_raw[:10])
            e = _date.fromisoformat(end_raw[:10])
            months = (e.year - s.year) * 12 + (e.month - s.month)
            if months > 0:
                hold_months = months
                if months < 12:
                    hold_label = f"{months} months"
                elif months == 12:
                    hold_label = "1 year"
                else:
                    years = months // 12
                    rem = months % 12
                    hold_label = f"{years} year{'s' if years > 1 else ''}" + (
                        f", {rem} month{'s' if rem > 1 else ''}" if rem else ""
                    )
        except (ValueError, TypeError):
            pass

    is_open = "FULL AND OPEN" in comp_type

    if not name:
        return {
            "name": None,
            "has_name": False,
            "uei": uei,
            "cage_code": cage_code,
            "hold_months": hold_months,
            "hold_label": hold_label,
            "displacement_signal": "unknown",
            "displacement_label": "Incumbent unknown",
            "displacement_note": "No incumbent vendor on file. Search SAM.gov to identify the current award holder.",
        }

    # Displacement logic
    if hold_months is not None and hold_months > 48:
        signal = "hard"
        label = "Strongly entrenched"
        note = (
            f"{name} has held this contract for {hold_label}. "
            "Deep agency relationships and incumbent past performance make displacement difficult."
        )
    elif hold_months is not None and hold_months > 36 and not is_open:
        signal = "hard"
        label = "Entrenched"
        note = (
            f"{name} has held this contract for {hold_label} under limited competition. "
            "Expect a strong recompete defense — differentiation and agency relationships are critical."
        )
    elif is_open and (hold_months is None or hold_months <= 24):
        signal = "easy"
        label = "Displaceable — open competition"
        note = (
            f"Awarded under full & open competition"
            f"{' for ' + hold_label if hold_months else ''}. "
            "A well-prepared challenger with comparable past performance can compete on merit."
        )
    else:
        signal = "medium"
        label = "Moderately entrenched"
        note = (
            f"{name} holds this contract for {hold_label}. " if hold_months else f"{name} holds this contract. "
        ) + "Research their agency performance history and any vulnerabilities before committing to a bid."

    return {
        "name": name,
        "has_name": True,
        "uei": uei,
        "cage_code": cage_code,
        "hold_months": hold_months,
        "hold_label": hold_label,
        "displacement_signal": signal,
        "displacement_label": label,
        "displacement_note": note,
    }


def contract_plain_summary(row) -> str:
    """Two-to-three sentence plain-English capture brief from stored fields.

    Action-oriented framing for the contract detail page header. Pure
    function — no AI calls. Falls back gracefully for sparse records.
    """
    from datetime import date as _date

    agency = (row.get("agency") or "").strip()
    vendor = (row.get("vendor") or "").strip()
    value = float(row.get("value") or 0)
    category = (row.get("category") or "").strip()
    description = (row.get("description") or "").strip()
    end_raw = (row.get("end_date") or "").strip()
    days = _safe_int(row.get("days_remaining"))
    comp_type = (row.get("competition_type") or "").strip()
    sol_id = (row.get("solicitation_id") or "").strip()
    sam_type = (row.get("sam_type") or "").strip()

    # Work label
    work = category if (category and category.lower() not in ("other", "unknown")) else ""
    if not work and description:
        work = (description[:75].rsplit(" ", 1)[0] if len(description) > 75 else description)

    # Sentence 1: holder + agency + work + value
    val_str = f"${value:,.0f}" if value else ""
    parts = []
    if agency and vendor:
        s1 = f"{agency} has a contract with {vendor}"
        s1 += f" for {work.lower()}" if work else ""
        s1 += f", valued at {val_str}" if val_str else ""
        s1 += "."
    elif agency:
        s1 = f"{agency} holds an active government contract"
        s1 += f" for {work.lower()}" if work else ""
        s1 += f" valued at {val_str}" if val_str else ""
        s1 += "."
    else:
        s1 = f"Active government contract valued at {val_str}." if val_str else "Active government contract."
    parts.append(s1)

    # Sentence 2: timing + competition
    timing_parts = []
    if end_raw:
        try:
            e = _date.fromisoformat(end_raw[:10])
            timing_parts.append(f"runs through {e.strftime('%B %Y')}")
        except (ValueError, TypeError):
            timing_parts.append(f"runs through {end_raw}")
    if days is not None and days > 0:
        timing_parts.append(f"{days} days remaining")
    if comp_type:
        timing_parts.append(f"awarded via {comp_type.lower()}")

    if timing_parts:
        s2 = f"The contract {timing_parts[0]}"
        if len(timing_parts) == 2:
            s2 += f" ({timing_parts[1]})"
        elif len(timing_parts) == 3:
            s2 += f" ({timing_parts[1]}), {timing_parts[2]}"
        s2 += "."
        parts.append(s2)

    # Sentence 3: solicitation status
    if sol_id and sam_type:
        parts.append(f"SAM.gov shows a {sam_type.lower()} record (solicitation {sol_id}).")
    elif sol_id:
        parts.append(f"Solicitation {sol_id} is on file.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Time-anchored urgency and solicitation window estimation
# ---------------------------------------------------------------------------

def why_now(row) -> str:
    """One sentence answering: why should I act on this contract today?

    Time-anchors urgency to THIS contract's specific solicitation cycle.
    Not a generic stage label — a concrete sentence with dates and numbers.
    Pure function: no DB, no AI calls.
    """
    import datetime as _dt
    from datetime import date as _date, timedelta as _td

    days = _safe_int(row.get("days_remaining"))
    sam_type = (row.get("sam_type") or "").lower().strip()
    sam_due_raw = (row.get("sam_due_date") or "").strip()

    due_date = None
    if sam_due_raw:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
            try:
                due_date = _dt.datetime.strptime(sam_due_raw[:19], fmt[:len(sam_due_raw[:19])]).date()
                break
            except ValueError:
                continue

    due_future = due_date is not None and due_date >= _date.today()
    days_to_due = (due_date - _date.today()).days if due_future else None

    # Open solicitation with a live deadline — most urgent case
    if sam_type in _OPEN_SAM_TYPES and due_future and days_to_due is not None:
        if days_to_due <= 7:
            return (
                f"A solicitation is live and closes in {days_to_due} day{'s' if days_to_due != 1 else ''} "
                "— respond now or the window closes."
            )
        return (
            f"A solicitation is open and closes {due_date.strftime('%B %-d, %Y')} ({days_to_due} days) "
            "— this is the active bid window."
        )

    if sam_type in _PRESOL_SAM_TYPES:
        return (
            "A pre-solicitation is posted — the formal RFP could drop any time. "
            "Submit a capability statement now to get on the agency's radar."
        )

    if days is None:
        return "Timing is unknown — verify the contract end date on SAM.gov before allocating pursuit resources."

    if days <= 0:
        return "This contract has expired — search SAM.gov for the follow-on award or recompete solicitation."

    if days < 30:
        return (
            f"With only {days} day{'s' if days != 1 else ''} remaining, "
            "the solicitation has almost certainly closed. Shift focus to the follow-on award."
        )

    if days < 90:
        return (
            f"Only {days} days remain — the solicitation may already be live on SAM.gov. "
            "Check immediately if you are already engaged with this agency."
        )

    if days < 180:
        return (
            f"With {days} days until expiry, the solicitation is likely to appear within "
            "the next 30–60 days. Prepare your proposal and teaming now."
        )

    if days < 270:
        return (
            f"At {days} days out, teaming and pricing discussions must begin now — "
            "most competitive proposals take 90+ days to build properly."
        )

    if days < 365:
        return (
            f"With {days} days remaining, requirements are being drafted by the agency now. "
            "Engaging today can still influence the solicitation language."
        )

    if days <= 540:
        try:
            solicit_estimate = _date.today() + _td(days=days - 150)
            return (
                f"The {days}-day pursuit window is open now — solicitation expected around "
                f"{solicit_estimate.strftime('%B %Y')}. "
                "Start building agency relationships and shaping your position before that window closes."
            )
        except Exception:
            pass
        return "You are in the ideal 12–18 month pursuit window — act now to build agency relationships before the solicitation drops."

    try:
        revisit = _date.today() + _td(days=180)
        return (
            f"At {days} days out, active pursuit is premature. "
            f"Set a reminder to revisit around {revisit.strftime('%B %Y')} when the window opens."
        )
    except Exception:
        return "More than 18 months out — watch and revisit when it enters the 12–18 month pursuit window."


def estimated_solicitation_window(row) -> dict:
    """Estimate when this contract will open for competitive bids.

    Returns:
        status:  "open" | "presolicitation" | "awarded" | "near" | "expected" | "early" | "too_late" | "expired" | "unknown"
        label:   short display string (e.g. "Open now — closes Aug 15, 2026")
        detail:  one sentence of context
        urgency: "critical" | "high" | "medium" | "low" | "none"
    """
    import datetime as _dt
    from datetime import date as _date, timedelta as _td

    days = _safe_int(row.get("days_remaining"))
    sam_type = (row.get("sam_type") or "").lower().strip()
    sam_due_raw = (row.get("sam_due_date") or "").strip()

    due_date = None
    if sam_due_raw:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
            try:
                due_date = _dt.datetime.strptime(sam_due_raw[:19], fmt[:len(sam_due_raw[:19])]).date()
                break
            except ValueError:
                continue

    due_future = due_date is not None and due_date >= _date.today()

    if sam_type in _OPEN_SAM_TYPES:
        if due_future:
            days_left = (due_date - _date.today()).days
            return {
                "status": "open",
                "label": f"Open now — closes {due_date.strftime('%b %-d, %Y')}",
                "detail": f"Active solicitation with {days_left} day{'s' if days_left != 1 else ''} to respond.",
                "urgency": "critical" if days_left <= 14 else "high",
            }
        return {
            "status": "open",
            "label": "Solicitation on file — verify deadline",
            "detail": "A SAM.gov solicitation record exists. Confirm the response deadline before starting your proposal.",
            "urgency": "high",
        }

    if sam_type in _PRESOL_SAM_TYPES:
        return {
            "status": "presolicitation",
            "label": f"Pre-solicitation posted ({sam_type})",
            "detail": "Agency is gathering market information. Formal RFP expected to follow — submit a capability statement now.",
            "urgency": "high",
        }

    if sam_type in _AWARD_SAM_TYPES:
        urgency = "low" if (days or 0) > 180 else "medium"
        return {
            "status": "awarded",
            "label": "Awarded — not open for bids",
            "detail": "SAM.gov shows an award notice. The recompete solicitation will open closer to contract expiry.",
            "urgency": urgency,
        }

    if days is None:
        return {
            "status": "unknown",
            "label": "Solicitation date unknown",
            "detail": "No SAM.gov record found. Search by contract number or vendor name to find current status.",
            "urgency": "none",
        }

    if days <= 0:
        return {
            "status": "expired",
            "label": "Expired — search for follow-on",
            "detail": "This contract has ended. The follow-on procurement may already be posted on SAM.gov.",
            "urgency": "medium",
        }

    if days < 30:
        return {
            "status": "too_late",
            "label": "Solicitation window likely closed",
            "detail": f"Only {days} day{'s' if days != 1 else ''} remain — too late for most challengers to prepare a competitive bid.",
            "urgency": "none",
        }

    if days < 90:
        return {
            "status": "near",
            "label": "Solicitation may be live now",
            "detail": f"Contract expires in {days} days — check SAM.gov immediately for an active solicitation.",
            "urgency": "critical",
        }

    if days < 180:
        return {
            "status": "near",
            "label": "Solicitation expected within 1–3 months",
            "detail": f"Based on the {days}-day runway, a solicitation is likely to appear soon.",
            "urgency": "high",
        }

    try:
        if days < 270:
            est = _date.today() + _td(days=days - 90)
        else:
            est = _date.today() + _td(days=max(30, days - 150))
        est_label = est.strftime("%B %Y")
    except Exception:
        est_label = "unknown"

    if days < 540:
        return {
            "status": "expected",
            "label": f"Solicitation expected ~{est_label}",
            "detail": f"Typically appears 3–6 months before contract expiry; roughly {est_label} based on the {days}-day runway.",
            "urgency": "medium" if days < 400 else "low",
        }

    return {
        "status": "early",
        "label": f"Solicitation not expected until ~{est_label}",
        "detail": "More than 18 months out. Watch for pre-solicitation notices as the pursuit window approaches.",
        "urgency": "low",
    }


def next_action_steps(row, incumbent_intel=None) -> list[dict]:
    """Return 2–4 ordered, contract-specific next steps.

    Steps name the incumbent, agency, and timeframe — not generic stage text.
    Each step: {action: str, detail: str, timeframe: str, priority: str}
    priority: "now" | "soon" | "later"
    """
    from datetime import date as _date, timedelta as _td

    days = _safe_int(row.get("days_remaining"))
    stage = pursuit_stage(days)
    stage_key = stage["stage_key"]

    agency = (row.get("agency") or "").strip()
    sub_agency = (row.get("sub_agency") or "").strip()
    sol_id = (row.get("solicitation_id") or "").strip()
    sam_url = (row.get("sam_url") or "").strip()
    sam_type = (row.get("sam_type") or "").lower().strip()
    value = float(row.get("value") or 0)
    val_str = f"${value:,.0f}" if value else ""

    vendor = None
    if incumbent_intel and incumbent_intel.get("has_name"):
        vendor = incumbent_intel["name"]
    else:
        vendor = (row.get("vendor") or "").strip() or None

    agency_label = sub_agency or agency or "the agency"

    steps = []

    if stage_key in ("expired", "too_late"):
        steps.append({
            "action": "Search SAM.gov for the follow-on solicitation",
            "detail": f"Search {agency_label} on SAM.gov by award ID or vendor name to find the next procurement.",
            "timeframe": "This week",
            "priority": "now",
        })
        if vendor:
            steps.append({
                "action": f"Check {vendor}'s recent award history",
                "detail": "If the incumbent was re-awarded, note the contract structure for the next recompete cycle.",
                "timeframe": "This week",
                "priority": "soon",
            })
        return steps

    if stage_key == "urgent":
        steps.append({
            "action": "Check SAM.gov for the active solicitation immediately",
            "detail": (
                f"Search {agency_label} opportunities — solicitation {sol_id} may be active." if sol_id
                else f"Search {agency_label} opportunities by NAICS or contract value."
            ),
            "timeframe": "Today",
            "priority": "now",
        })
        steps.append({
            "action": "Only proceed if already engaged with this agency",
            "detail": "Starting from scratch at 30–90 days is very late. Allocate resources here only if you have an existing agency relationship.",
            "timeframe": "Decision today",
            "priority": "now",
        })
        return steps

    if stage_key == "active_pursuit":
        if sol_id or sam_url:
            steps.append({
                "action": "Download and review the solicitation package",
                "detail": (
                    f"Solicitation {sol_id} is on file — pull the full requirements and evaluation criteria from SAM.gov." if sol_id
                    else "A SAM.gov record exists — download requirements and review evaluation criteria now."
                ),
                "timeframe": "Today",
                "priority": "now",
            })
        else:
            steps.append({
                "action": "Search SAM.gov for the active solicitation",
                "detail": f"Contract expires in {days} days — the solicitation may already be posted. Search {agency_label} on SAM.gov now.",
                "timeframe": "Today",
                "priority": "now",
            })
        steps.append({
            "action": "Finalize teaming partners and past performance citations",
            "detail": "Lock in subcontractors, confirm past performance references, and have pricing ready for a short proposal timeline.",
            "timeframe": "This week",
            "priority": "now",
        })
        if vendor:
            steps.append({
                "action": f"Analyze {vendor}'s performance on this contract",
                "detail": "Research any past performance gaps, agency feedback, or protest history that could weaken their recompete position.",
                "timeframe": "This week",
                "priority": "soon",
            })
        return steps

    if stage_key == "prepare":
        steps.append({
            "action": "Begin writing your proposal and pricing model",
            "detail": (
                f"The solicitation for this {val_str} contract is expected soon — "
                f"{agency_label} typically issues 3–6 months before expiry."
            ),
            "timeframe": "This week",
            "priority": "now",
        })
        steps.append({
            "action": "Finalize teaming arrangements",
            "detail": "Lock in subcontractors now — late teaming discussions compress proposal quality and negotiating leverage.",
            "timeframe": "Within 30 days",
            "priority": "now",
        })
        if vendor:
            steps.append({
                "action": f"Build a competitive analysis of {vendor}",
                "detail": "Identify their strengths, weaknesses, and any agency relationship gaps your team can exploit in the proposal.",
                "timeframe": "Within 2 weeks",
                "priority": "soon",
            })
        return steps

    if stage_key == "shape":
        steps.append({
            "action": f"Request a capability briefing with {agency_label}",
            "detail": "At this stage you can still influence solicitation requirements. A briefing introduces your team and can shape evaluation criteria.",
            "timeframe": "Within 2 weeks",
            "priority": "now",
        })
        steps.append({
            "action": "Set a SAM.gov alert for draft RFP or sources-sought",
            "detail": f"Create an email alert for {agency_label} on SAM.gov so you catch any presolicitation notices immediately.",
            "timeframe": "Set up today",
            "priority": "now",
        })
        if vendor:
            steps.append({
                "action": f"Research {vendor}'s agency relationships and past performance",
                "detail": "Understanding their strengths helps you position your differentiators before the solicitation drops.",
                "timeframe": "Within 30 days",
                "priority": "soon",
            })
        steps.append({
            "action": "Begin identifying and vetting teaming partners",
            "detail": "Preliminary teaming discussions take 30–60 days — start now even before the solicitation is finalized.",
            "timeframe": "Within 30 days",
            "priority": "soon",
        })
        return steps

    if stage_key == "best_window":
        steps.append({
            "action": f"Initiate agency engagement with {agency_label}",
            "detail": "Schedule a capability briefing or attend an upcoming industry day. Early engagement is the highest-leverage investment in a recompete win.",
            "timeframe": "Within 30 days",
            "priority": "now",
        })
        if vendor:
            steps.append({
                "action": f"Study {vendor}'s contract history and performance",
                "detail": "Research their award, any modifications, and public performance data. Identify capability gaps your proposal can address.",
                "timeframe": "Within 2 weeks",
                "priority": "now",
            })
        else:
            steps.append({
                "action": "Identify the current incumbent on SAM.gov",
                "detail": "Search the award ID or contract number to find the current awardee. Knowing the incumbent is critical for a competitive strategy.",
                "timeframe": "This week",
                "priority": "now",
            })
        try:
            solicit_est = _date.today() + _td(days=max(0, (days or 0) - 150))
            solicit_str = solicit_est.strftime("%B %Y")
        except Exception:
            solicit_str = "in 6–12 months"
        steps.append({
            "action": "Build your win theme and key discriminators",
            "detail": f"Define what makes your team the best choice before the solicitation drops (~{solicit_str}). Specific past performance and pricing strategy should be ready.",
            "timeframe": "Within 60 days",
            "priority": "soon",
        })
        return steps

    if stage_key == "watch":
        try:
            revisit = _date.today() + _td(days=180)
            revisit_str = revisit.strftime("%B %Y")
        except Exception:
            revisit_str = "in 6 months"
        steps.append({
            "action": "Add to your watch list and set a follow-up reminder",
            "detail": f"This contract is more than 18 months out. Revisit around {revisit_str} when it enters the active pursuit window.",
            "timeframe": f"Revisit ~{revisit_str}",
            "priority": "later",
        })
        if vendor:
            steps.append({
                "action": f"Track {vendor} for news and agency relationship changes",
                "detail": "Leadership changes, past performance issues, or agency dissatisfaction create openings as the recompete approaches.",
                "timeframe": "Ongoing",
                "priority": "later",
            })
        return steps

    # Unknown timing
    steps.append({
        "action": "Verify the contract end date on SAM.gov",
        "detail": "No expiration date is on file. Confirm the timeline before committing pursuit resources.",
        "timeframe": "This week",
        "priority": "now",
    })
    return steps


# ---------------------------------------------------------------------------
# Opportunity status / actionability classification
# ---------------------------------------------------------------------------

# SAM.gov notice types that represent open solicitations (bids accepted now).
_OPEN_SAM_TYPES = frozenset({
    "solicitation",
    "combined synopsis/solicitation",
    "rfq",
    "sale of surplus property",
})

# SAM.gov types for market-research / presolicitation stages (not accepting bids yet).
_PRESOL_SAM_TYPES = frozenset({
    "presolicitation",
    "sources sought",
    "special notice",
})

# SAM.gov types that are award notices / informational — contract already awarded.
_AWARD_SAM_TYPES = frozenset({
    "award notice",
    "justification",
    "intent to bundle requirements",
    "fair opportunity / limited sources justification",
    "modification/amendment",
})

# Days-remaining thresholds (already defined in apply_window.py; redefined
# here to keep contract_summary.py free of data-pipeline imports).
_TOO_LATE_DAYS = 30     # under 30d: too late for most small-biz prep
_WATCH_DAYS = 540       # over 540d: watch only, not yet actionable


def opportunity_status(row) -> dict:
    """Classify a contract row into an actionability bucket.

    Returns a dict with:
      status      — machine-readable key
      label       — short display label
      can_bid     — True / False / None (unknown)
      reason      — one-sentence explanation for the user
      next_action — what to do next
    """
    from datetime import date as _date

    days = row.get("days_remaining")
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = None

    sam_type_raw = (row.get("sam_type") or "").strip()
    sam_type = sam_type_raw.lower()
    sam_url = (row.get("sam_url") or "").strip()
    sam_due_raw = (row.get("sam_due_date") or "").strip()

    # Parse response deadline if present.
    due_date = None
    if sam_due_raw:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
            try:
                import datetime as _dt
                due_date = _dt.datetime.strptime(sam_due_raw[:19], fmt[:len(sam_due_raw[:19])]).date()
                break
            except ValueError:
                continue

    due_future = due_date is not None and due_date >= _date.today()

    # --- Expired ---
    if days is not None and days <= 0:
        return {
            "status": "expired",
            "label": "Expired",
            "can_bid": False,
            "reason": "This contract has already expired.",
            "next_action": "Search SAM.gov for any follow-on solicitation.",
        }

    # --- Open solicitation with future due date ---
    if sam_url and sam_type in _OPEN_SAM_TYPES and due_future:
        return {
            "status": "open_now",
            "label": "Open now",
            "can_bid": True,
            "reason": (
                f"Active {sam_type_raw or 'solicitation'} with response deadline"
                f" {due_date.strftime('%b %-d, %Y')}."
            ),
            "next_action": "Download the solicitation package and prepare your bid.",
        }

    # --- SAM solicitation on file but we can't confirm due date ---
    if sam_url and sam_type in _OPEN_SAM_TYPES:
        return {
            "status": "solicitation_unconfirmed",
            "label": "Solicitation on file",
            "can_bid": None,
            "reason": (
                "A solicitation was found on SAM.gov — "
                "verify the response deadline before investing bid resources."
            ),
            "next_action": "Check the SAM.gov link to confirm the response deadline.",
        }

    # --- Pre-solicitation / sources sought (market research stage) ---
    if sam_url and sam_type in _PRESOL_SAM_TYPES:
        return {
            "status": "presolicitation",
            "label": "Pre-solicitation",
            "can_bid": False,
            "reason": (
                f"{sam_type_raw or 'Pre-solicitation'} posted — the agency is gathering "
                "market information. A formal solicitation may follow."
            ),
            "next_action": "Submit capability statement or sources-sought response to get on agency radar.",
        }

    # --- Award notice (contract already awarded, not open for bids) ---
    if sam_url and sam_type in _AWARD_SAM_TYPES:
        return {
            "status": "awarded",
            "label": "Awarded — not open",
            "can_bid": False,
            "reason": (
                "The SAM.gov record is an award notice, not an open solicitation. "
                "This contract has been awarded to the current incumbent."
            ),
            "next_action": "Watch for the recompete solicitation as the contract approaches expiry.",
        }

    # --- Has a SAM URL but type is unknown or empty ---
    if sam_url:
        return {
            "status": "solicitation_on_file",
            "label": "SAM record on file",
            "can_bid": None,
            "reason": "A SAM.gov record was found — check the link to see if it is open for bids.",
            "next_action": "Review the SAM.gov record to confirm current status.",
        }

    # --- Days-remaining fallback (no SAM data) ---
    if days is None:
        return {
            "status": "unknown",
            "label": "Status unknown",
            "can_bid": None,
            "reason": "Contract end date is not available.",
            "next_action": "Search SAM.gov for the solicitation number or vendor name.",
        }

    if days < _TOO_LATE_DAYS:
        return {
            "status": "too_late",
            "label": "Too late",
            "can_bid": False,
            "reason": (
                f"Expires in {days} day{'s' if days != 1 else ''} — "
                "too late for most small businesses to realistically prepare a bid."
            ),
            "next_action": "Monitor for the follow-on recompete and engage early next cycle.",
        }

    if days > _WATCH_DAYS:
        return {
            "status": "watch",
            "label": "Watch — early stage",
            "can_bid": False,
            "reason": f"Expires in {days} days — more than 18 months out, no solicitation yet.",
            "next_action": "Set a reminder to revisit in 6–12 months when the procurement window opens.",
        }

    # Default: awarded contract within recompete preparation window
    return {
        "status": "prepare_recompete",
        "label": "Prepare for recompete",
        "can_bid": False,
        "reason": (
            "This is an awarded contract — not an open solicitation. "
            "The incumbent is currently performing; the recompete window is approaching."
        ),
        "next_action": "Begin capture planning: research the incumbent, agency contacts, and requirements.",
    }
