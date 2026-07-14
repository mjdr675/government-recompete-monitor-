"""lifecycle.py — the single canonical recompete lifecycle classifier.

One deterministic, pure function turns ``days_remaining`` on the incumbent
contract into a lifecycle stage, so every surface (dashboard "Critical
Opportunities", quick views, recommendations, contracts listing, filters,
detail pages, exports) applies the *same* thresholds and the *same* notion of
what is "critical" / "actionable" / hidden-by-default.

Design rules (see G1 urgency-lifecycle fix):

  * "Critical" means a valuable, *actionable preparation window* — NOT imminent
    expiry. A contract with only a few days left is never Critical, no matter
    how high its recompete score or dollar value.
  * Too Late and Expired contracts are hidden by default from actionable /
    critical views (they remain reachable via an explicit include filter).
  * High score / high value can never restore Critical status under 30 days —
    the label is a pure function of days remaining.

Stage buckets (days_remaining):

    > 540            long_range   "Long Range"
    365 .. 540       early        "Early"        actionable, critical
    180 .. 364       prepare      "Prepare"      actionable, critical
     90 .. 179       pursue       "Pursue"       actionable, critical
     30 .. 89        closing      "Closing"      actionable
      0 .. 29        too_late     "Too Late"     hidden by default
    < 0              expired      "Expired"      hidden by default
    None / invalid   unknown      "Timing Unknown"

Pure: no DB, config, clock, randomness, or external services. All time-relative
inputs (``days_remaining``) are computed by the caller.
"""

# ── Canonical thresholds (inclusive lower bounds, in days remaining) ──────────
# These are the ONLY place lifecycle day thresholds are defined. Other modules
# (apply_window, contract_summary.pursuit_stage, recompete_report._priority,
# db.get_contracts) import from here rather than repeating magic numbers.
EARLY_MIN = 365          # 365..540  → early
PREPARE_MIN = 180        # 180..364  → prepare
PURSUE_MIN = 90          # 90..179   → pursue
CLOSING_MIN = 30         # 30..89    → closing
TOO_LATE_MIN = 0         # 0..29     → too_late
LONG_RANGE_MIN = 541     # > 540     → long_range (541 and up)

# Outer edge of the useful preparation window (top of "early").
BEST_WINDOW_MAX = 540

# Stage keys grouped by behaviour. These drive filtering/display everywhere.
#
# A contract "qualifies as CRITICAL" only inside the actionable window
# (Closing..Early, i.e. 30–540 days): there is realistic runway to prepare a
# competitive bid, and it is not imminent expiry. Too Late / Expired (< 30 days,
# hidden by default) and Long Range (> 540 days, not yet actionable) never
# qualify — this is what stops a "few days remaining" contract, or a very early
# one, from being surfaced as Critical no matter how high its score/value.
CRITICAL_STAGES = frozenset({"closing", "pursue", "prepare", "early"})
ACTIONABLE_STAGES = frozenset({"closing", "pursue", "prepare", "early"})
HIDDEN_BY_DEFAULT_STAGES = frozenset({"too_late", "expired"})

# Human-readable label per stage key.
STAGE_LABELS = {
    "unknown": "Timing Unknown",
    "expired": "Expired",
    "too_late": "Too Late",
    "closing": "Closing",
    "pursue": "Pursue",
    "prepare": "Prepare",
    "early": "Early",
    "long_range": "Long Range",
}


def _coerce_days(days_remaining):
    """Return days_remaining as an int, or None when missing/uncoercible."""
    if days_remaining is None:
        return None
    try:
        return int(days_remaining)
    except (TypeError, ValueError):
        return None


def stage_key(days_remaining):
    """Return the canonical lifecycle stage key for ``days_remaining``.

    One of: unknown, expired, too_late, closing, pursue, prepare, early,
    long_range.
    """
    d = _coerce_days(days_remaining)
    if d is None:
        return "unknown"
    if d < 0:
        return "expired"
    if d < CLOSING_MIN:          # 0..29
        return "too_late"
    if d < PURSUE_MIN:           # 30..89
        return "closing"
    if d < PREPARE_MIN:          # 90..179
        return "pursue"
    if d < EARLY_MIN:            # 180..364
        return "prepare"
    if d <= BEST_WINDOW_MAX:     # 365..540
        return "early"
    return "long_range"          # > 540


def is_critical(days_remaining):
    """True when the contract is in a valuable, actionable preparation window.

    Never true under 30 days — imminent expiry is not "critical". This is the
    guard that stops high score/value from surfacing a near-expired contract as
    Critical.
    """
    return stage_key(days_remaining) in CRITICAL_STAGES


def is_actionable(days_remaining):
    """True when there is realistic time to act (30..540 days)."""
    return stage_key(days_remaining) in ACTIONABLE_STAGES


def is_hidden_by_default(days_remaining):
    """True for Too Late / Expired — hidden from default critical/actionable views."""
    return stage_key(days_remaining) in HIDDEN_BY_DEFAULT_STAGES


def label(days_remaining):
    """Human-readable lifecycle label (e.g. 'Pursue', 'Too Late')."""
    return STAGE_LABELS[stage_key(days_remaining)]


def effective_priority(priority, days_remaining):
    """Display guard so a stored priority never overstates lifecycle urgency.

    Two rules, in order of the day bucket:

      * Too Late / Expired (< 30 days, ``hidden_by_default``): a record this
        close to (or past) expiry must **never** display High **or** Critical —
        there is no realistic runway to prepare a competitive bid. A stored
        CRITICAL/HIGH is downgraded to LOW.
      * Long Range (> 540 days) and any other non-critical bucket: a stored
        CRITICAL is downgraded to HIGH (real value, but not an imminent
        actionable window).

    Inside the critical window (30..540) the stored priority stands. When days
    are unknown we leave the stored priority as-is (no lifecycle signal). This
    is the single guard that stops high score/value from surfacing a
    near-expired contract as High/Critical in any listing or badge.
    """
    p = (priority or "").strip()
    if _coerce_days(days_remaining) is None:
        return priority
    if is_hidden_by_default(days_remaining):
        return "LOW" if p.upper() in ("CRITICAL", "HIGH") else priority
    if p.upper() != "CRITICAL":
        return priority
    return priority if is_critical(days_remaining) else "HIGH"


def lifecycle_stage(days_remaining):
    """Full classification dict for a contract's days remaining.

    Keys:
      stage_key          — canonical key (see ``stage_key``)
      label              — human-readable label
      critical           — bool: valuable actionable preparation window
      actionable         — bool: realistic time to act
      hidden_by_default  — bool: Too Late / Expired, hidden from default views
    """
    key = stage_key(days_remaining)
    return {
        "stage_key": key,
        "label": STAGE_LABELS[key],
        "critical": key in CRITICAL_STAGES,
        "actionable": key in ACTIONABLE_STAGES,
        "hidden_by_default": key in HIDDEN_BY_DEFAULT_STAGES,
    }
