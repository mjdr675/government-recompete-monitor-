"""Today's Work Dashboard — platform data layer.

Exposes today_work_items(user_id) — a single, stable data contract that powers
the 'What should I work on today?' dashboard.

Design principles:
  - Pure data contract: no Flask, no templates, no rendering logic.
  - Delegates CI decisions to contract_summary (pursuit_stage, recommended_action).
  - Delegates fit scoring to business_match (business_match_score, business_match_reasons).
  - Delegates sort policy to domain/policies/contract_ranking.
  - Each contract appears in at most one section (highest-priority section wins).

Returned list schema per item (all keys always present):
  internal_id, award_id, vendor, agency, value, end_date,
  days_remaining, recompete_score, competition_type, solicitation_id,
  section, priority, why, why_now,
  next_action, next_action_explanation, too_late,
  pursuit_stage_key, pursuit_stage_label,
  confidence, business_fit {score, reasons},
  pipeline_stage, pipeline_overdue, next_action_due
"""

from __future__ import annotations

from datetime import date

from contract_summary import recommended_action, pursuit_stage
from business_match import business_match_score, business_match_reasons

# Sections in display-priority order (position in this tuple is not the sort key;
# _PRIORITY_ORDER drives actual sort).
SECTIONS = (
    "needs_attention",
    "start_capture",
    "revenue_opp",
    "expiring",
    "monitor",
)

_PRIORITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# Pursuit stage keys owned by contract_summary.pursuit_stage()
_CAPTURE_STAGES = frozenset({"best_window", "shape"})
_ACTIONABLE_STAGES = frozenset({"active_pursuit", "prepare", "shape", "best_window"})
_EXPIRING_MAX_DAYS = 90
_REVENUE_THRESHOLD = 5_000_000
_DISCOVERY_SCORE_FLOOR = 50       # minimum recompete_score to surface in discovery
_CAPTURE_FIT_FLOOR = 30           # minimum business fit to surface in start_capture
_CAPTURE_SCORE_FLOOR = 65         # OR minimum recompete_score to surface in start_capture


def _make_item(
    contract: dict,
    section: str,
    priority: str,
    why: str,
    why_now: str,
    profile: dict | None = None,
    pipeline_stage: str | None = None,
    next_action_due: str | None = None,
) -> dict:
    """Build a normalized work item dict from a contract row.

    Calls into contract_summary and business_match to fill the CI and fit fields.
    Never raises — missing contract fields are handled gracefully by the
    downstream functions (they already guard against None inputs).
    """
    rec = recommended_action(contract)
    stage = pursuit_stage(contract.get("days_remaining"))

    fit_score: int | None = None
    fit_reasons: list[str] = []
    if profile:
        fit_score = business_match_score(contract, profile)
        fit_reasons = business_match_reasons(contract, profile)

    overdue = False
    if next_action_due and pipeline_stage:
        try:
            overdue = date.fromisoformat(str(next_action_due)[:10]) < date.today()
        except (ValueError, TypeError):
            pass

    return {
        # Contract identity
        "internal_id": contract.get("internal_id"),
        "award_id": contract.get("award_id"),
        "vendor": contract.get("vendor"),
        "agency": contract.get("agency"),
        "value": contract.get("value"),
        "end_date": contract.get("end_date"),
        "days_remaining": contract.get("days_remaining"),
        "recompete_score": contract.get("recompete_score"),
        "competition_type": contract.get("competition_type"),
        "solicitation_id": contract.get("solicitation_id"),
        # Section classification
        "section": section,
        "priority": priority,
        # Why surfaced
        "why": why,
        "why_now": why_now,
        # Next action — contract_summary.recommended_action owns this logic
        "next_action": rec["action"],
        "next_action_explanation": rec.get("explanation", ""),
        "too_late": rec.get("too_late", False),
        # Pursuit stage — contract_summary.pursuit_stage owns this logic
        "pursuit_stage_key": stage["stage_key"],
        "pursuit_stage_label": stage["label"],
        # Business fit — business_match owns this logic
        "confidence": fit_score,
        "business_fit": {
            "score": fit_score,
            "reasons": fit_reasons,
        },
        # Pipeline context
        "pipeline_stage": pipeline_stage,
        "pipeline_overdue": overdue,
        "next_action_due": next_action_due,
    }


def today_work_items(user_id: int | None) -> list[dict]:
    """Return a prioritized list of work items for the Today's Work dashboard.

    Sections:
      needs_attention  — active pipeline items that are overdue or in a closing
                         window (capturing/proposal with <180 days remaining).
      start_capture    — high-scoring contracts in the 365–540-day best-pursuit
                         window where capture planning should start now.
      revenue_opp      — highest-value contracts in any actionable stage that
                         haven't been claimed by a higher-priority section.
      expiring         — watchlist contracts expiring within 90 days.
      monitor          — watchlist contracts not yet captured by other sections.

    Items are sorted: critical > high > medium > low, then days_remaining asc
    (most urgent within a priority first).  Each contract_id appears once only.

    Returns [] when user_id is None.
    """
    if not user_id:
        return []

    # Deferred imports to avoid circular dependencies and keep module importable
    # without a live DB engine (important for unit tests that monkeypatch db).
    from db import get_company_profile, get_engine, list_opportunities, PIPELINE_TERMINAL_STAGES
    from sqlalchemy import text

    profile = get_company_profile(user_id)
    engine = get_engine()
    today = date.today()

    # ── 1. Load pipeline opportunities (contract fields joined in) ──────────
    all_opps = list_opportunities(user_id)
    active_opps = [o for o in all_opps if o.get("stage") not in PIPELINE_TERMINAL_STAGES]

    # ── 2. Load watchlist contracts ─────────────────────────────────────────
    with engine.connect() as conn:
        wl_rows = conn.execute(text("""
            SELECT c.internal_id, c.award_id, c.vendor, c.agency, c.value,
                   c.end_date, c.days_remaining, c.priority, c.recompete_score,
                   c.competition_type, c.solicitation_id, c.raw_json,
                   c.psc_code, c.naics_code, c.place_of_performance_state
            FROM contracts c
            JOIN user_watchlist w ON w.internal_id = c.internal_id
            WHERE w.user_id = :uid
        """), {"uid": user_id}).mappings().fetchall()
        watchlist: dict[str, dict] = {r["internal_id"]: dict(r) for r in wl_rows}

        # ── 3. Discovery pool for start_capture and revenue_opp ─────────────
        # Only contracts with recompete_score >= floor and days remaining > 0.
        discovery_rows = conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value,
                   end_date, days_remaining, priority, recompete_score,
                   competition_type, solicitation_id, raw_json,
                   psc_code, naics_code, place_of_performance_state
            FROM contracts
            WHERE COALESCE(days_remaining, 0) > 0
              AND recompete_score >= :floor
            ORDER BY recompete_score DESC, value DESC
            LIMIT 150
        """), {"floor": _DISCOVERY_SCORE_FLOOR}).mappings().fetchall()
    discovery: list[dict] = [dict(r) for r in discovery_rows]

    # ── Deduplication state ──────────────────────────────────────────────────
    seen: set[str] = set()
    items: list[dict] = []

    def _add(item: dict) -> bool:
        iid = item.get("internal_id")
        if not iid or iid in seen:
            return False
        seen.add(iid)
        items.append(item)
        return True

    # ── Section: needs_attention ─────────────────────────────────────────────
    # Active pipeline items that are overdue or in a closing window.
    for opp in active_opps:
        contract = dict(opp)
        nad = opp.get("next_action_due")
        stage_key = opp.get("stage", "")
        days = int(contract.get("days_remaining") or 0)

        overdue = False
        if nad:
            try:
                overdue = date.fromisoformat(str(nad)[:10]) < today
            except (ValueError, TypeError):
                pass

        if overdue:
            priority = "critical"
            why = f"Next action overdue (was due {nad})"
            why_now = "This pipeline opportunity has a past-due action — address it today."
        elif stage_key in ("capturing", "proposal") and days < 180:
            priority = "high"
            why = (
                f"{'Capture' if stage_key == 'capturing' else 'Proposal'} "
                f"in progress with {days} days left"
            )
            why_now = "The proposal window is closing — keep momentum."
        elif stage_key in ("capturing", "proposal"):
            priority = "medium"
            why = f"Active {stage_key} underway"
            why_now = "Steady progress needed to meet the timeline."
        else:
            # Other pipeline stages without urgency signals don't go in needs_attention
            continue

        _add(_make_item(
            contract, "needs_attention", priority, why, why_now,
            profile=profile, pipeline_stage=stage_key, next_action_due=nad,
        ))

    # ── Section: start_capture ───────────────────────────────────────────────
    # Best-window or shape-stage contracts worth beginning capture on now.
    for row in discovery:
        ps = pursuit_stage(row.get("days_remaining"))
        if ps["stage_key"] not in _CAPTURE_STAGES:
            continue
        fit = business_match_score(row, profile) if profile else 0
        rs = int(row.get("recompete_score") or 0)
        if fit < _CAPTURE_FIT_FLOOR and rs < _CAPTURE_SCORE_FLOOR:
            continue
        if fit >= 60:
            priority = "high"
            why = f"Strong business match ({fit}% fit) — ready for capture"
        elif fit >= _CAPTURE_FIT_FLOOR:
            priority = "medium"
            why = f"Business match ({fit}% fit) in the best capture window"
        else:
            priority = "medium"
            why = f"High recompete score ({rs}) — worth capture planning"
        days = int(row.get("days_remaining") or 0)
        why_now = (
            f"{days} days remaining — the optimal window to begin capture planning "
            f"is now ({ps['label']})."
        )
        _add(_make_item(row, "start_capture", priority, why, why_now, profile=profile))

    # ── Section: revenue_opp ─────────────────────────────────────────────────
    # Highest-value contracts in any actionable stage, not yet claimed above.
    for row in sorted(discovery, key=lambda r: -(r.get("value") or 0)):
        val = float(row.get("value") or 0)
        if val < _REVENUE_THRESHOLD:
            break  # sorted descending; everything below is also < threshold
        ps = pursuit_stage(row.get("days_remaining"))
        if ps["stage_key"] not in _ACTIONABLE_STAGES:
            continue
        priority = "high" if val >= 10_000_000 else "medium"
        why = f"${val:,.0f} opportunity in an actionable window"
        why_now = f"{ps['label']} — {row.get('days_remaining', '?')} days remaining."
        _add(_make_item(row, "revenue_opp", priority, why, why_now, profile=profile))

    # ── Section: expiring ────────────────────────────────────────────────────
    # Tracked watchlist contracts expiring within 90 days.
    for iid, row in watchlist.items():
        days = int(row.get("days_remaining") or 0)
        if not (0 < days <= _EXPIRING_MAX_DAYS):
            continue
        priority = "high" if days <= 30 else "medium"
        why = f"Expiring in {days} days — track the follow-on solicitation"
        why_now = f"You are watching this contract and it expires in {days} days."
        _add(_make_item(row, "expiring", priority, why, why_now, profile=profile))

    # ── Section: monitor ─────────────────────────────────────────────────────
    # Remaining watchlist contracts worth keeping an eye on.
    for iid, row in watchlist.items():
        ps = pursuit_stage(row.get("days_remaining"))
        why = "You are watching this contract"
        why_now = ps["description"]
        _add(_make_item(row, "monitor", "low", why, why_now, profile=profile))

    # ── Sort: priority asc, then days_remaining asc within priority ──────────
    items.sort(key=lambda x: (
        _PRIORITY_ORDER.get(x["priority"], 99),
        x["days_remaining"] if x["days_remaining"] is not None else 9999,
    ))

    return items


def section_counts(items: list[dict]) -> dict[str, int]:
    """Return a dict of section → item count for a today_work_items result.

    Useful for template badges and empty-state rendering.
    """
    counts: dict[str, int] = {s: 0 for s in SECTIONS}
    for item in items:
        sec = item.get("section")
        if sec in counts:
            counts[sec] += 1
    return counts
