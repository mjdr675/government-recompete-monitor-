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
    try:
        d = int(days_remaining) if days_remaining is not None else None
    except (TypeError, ValueError):
        d = None

    if d is None:
        return {"name": "Time remaining", "earned": 0, "max": 25, "detail": "End date not recorded"}
    if d <= 0:
        return {"name": "Time remaining", "earned": 25, "max": 25, "detail": "Expired — follow-on may already be posted"}
    if d <= 30:
        return {"name": "Time remaining", "earned": 25, "max": 25, "detail": f"{d} days — solicitation likely imminent"}
    if d <= 60:
        return {"name": "Time remaining", "earned": 20, "max": 25, "detail": f"{d} days — recompete window opening"}
    if d <= 90:
        return {"name": "Time remaining", "earned": 15, "max": 25, "detail": f"{d} days — begin positioning now"}
    if d <= 180:
        return {"name": "Time remaining", "earned": 10, "max": 25, "detail": f"{d} days — within 6-month window"}
    return {"name": "Time remaining", "earned": 0, "max": 25, "detail": f"{d} days — more than 6 months out"}


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


def format_contract_update(row):
    """Format a field-change row for compact dashboard display."""
    field = row.get("field_name", "")
    kind = (row.get("change_kind") or "MODIFIED").upper()
    old = row.get("old_value")
    new = row.get("new_value")
    award_id = row.get("award_id")
    internal_id = row.get("internal_id", "")

    _labels = {
        "value": "Value",
        "end_date": "Recompete date",
        "days_remaining": "Days remaining",
        "vendor": "Vendor",
        "competition_type": "Competition type",
        "recompete_score": "Recompete score",
        "priority": "Priority",
    }
    label = _labels.get(field, field.replace("_", " ").title())

    if kind == "INCREASE":
        verb = "increased"
    elif kind == "DECREASE":
        verb = "decreased"
    elif kind == "SET":
        verb = "set"
    else:
        verb = "changed"

    def _fmt(v):
        if v is None:
            return "—"
        if field == "value":
            try:
                return f"${int(float(v)):,}"
            except (ValueError, TypeError):
                return str(v)
        return str(v)

    return {
        "headline": f"{label} {verb}",
        "field": field,
        "old_value": _fmt(old),
        "new_value": _fmt(new),
        "contract": award_id or internal_id,
        "run_date": row.get("run_date", ""),
        "change_kind": kind,
    }

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
