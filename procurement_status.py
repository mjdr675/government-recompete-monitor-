"""procurement_status.py — canonical *procurement status* classifier.

Procurement status answers a question that is **independent** of recompete
lifecycle/priority: *is this contract currently open for bidding, or is it
already closed / awarded?*

  * PROCUREMENT STATUS  — Open / Closed (Awarded) / Closed (Expired) / Cancelled
  * RECOMPETE PRIORITY  — the canonical :mod:`lifecycle` system (Early, Prepare,
    Pursue, Closing, Too Late, Expired, Long Range)

The two must never be combined. In particular, status is **never** inferred
from the lifecycle bucket: a contract being lifecycle "Early"/"Prepare" does not
make it Open. Status is derived only from authoritative source data:

  * A SAM.gov opportunity notice that is a live solicitation type → Open.
  * A SAM.gov award notice → Closed (Awarded).
  * A SAM.gov cancellation notice → Cancelled.
  * Otherwise the record is a USASpending contract award (that is what we hold
    on file): a still-running award → Closed (Awarded); one whose period of
    performance has ended (days_remaining < 0) → Closed (Expired).

No fabrication: when source data carries no signal we fall back to the
USASpending award facts we actually have, never to a guessed "Open".

Pure: no DB, network, clock, or secrets. Expiry is decided from the caller's
precomputed ``days_remaining``, never from the wall clock.
"""

# ── Status codes ──────────────────────────────────────────────────────────────
OPEN = "open"
CLOSED_AWARDED = "closed_awarded"
CLOSED_EXPIRED = "closed_expired"
CANCELLED = "cancelled"

STATUS_LABELS = {
    OPEN: "Open",
    CLOSED_AWARDED: "Closed (Awarded)",
    CLOSED_EXPIRED: "Closed (Expired)",
    CANCELLED: "Cancelled",
}

# Short badge text for cards (kept compact).
STATUS_BADGE = {
    OPEN: "Open",
    CLOSED_AWARDED: "Closed",
    CLOSED_EXPIRED: "Closed",
    CANCELLED: "Cancelled",
}

# ── Authoritative SAM.gov notice-type buckets ────────────────────────────────
# A live opportunity notice (accepting offers or an imminent live opportunity —
# not an award). These are the only types that make a record "Open".
OPEN_SAM_TYPES = frozenset({
    "solicitation",
    "combined synopsis/solicitation",
    "rfq",
    "sale of surplus property",
    "presolicitation",
    "sources sought",
    "special notice",
})

# Award / post-award informational notices — the contract is already awarded.
# NOTE: "intent to bundle requirements" is deliberately excluded — it is a
# pre-solicitation/planning notice (DFARS/FAR bundling notification), not
# evidence of an award. Treating it as an award notice would force
# closed_awarded even when days_remaining shows the record has actually
# expired. Rows carrying only this notice type fall through to the
# days_remaining-based fallback below instead.
AWARD_SAM_TYPES = frozenset({
    "award notice",
    "justification",
    "fair opportunity / limited sources justification",
    "modification/amendment",
})

# Cancellation notices.
CANCELLED_SAM_TYPES = frozenset({
    "cancellation",
    "cancelled",
    "cancel",
})


def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def status_code(row):
    """Return the canonical procurement-status code for a contract row.

    One of: ``open``, ``closed_awarded``, ``closed_expired``, ``cancelled``.
    Derived from authoritative source data only — never from lifecycle.
    """
    sam_type = (row.get("sam_type") or "").lower().strip()
    days = _safe_int(row.get("days_remaining"))

    if sam_type in CANCELLED_SAM_TYPES:
        return CANCELLED
    if sam_type in OPEN_SAM_TYPES:
        # A live SAM.gov opportunity notice — open for bidding / not yet awarded.
        return OPEN
    if sam_type in AWARD_SAM_TYPES:
        return CLOSED_AWARDED
    # No open-opportunity signal: this is the USASpending award we hold on file.
    if days is not None and days < 0:
        return CLOSED_EXPIRED
    return CLOSED_AWARDED


def is_open(row):
    """True only when authoritative source data shows a live opportunity notice."""
    return status_code(row) == OPEN


def procurement_status(row):
    """Full procurement-status classification for a contract row.

    Keys:
      code         — canonical status code (see ``status_code``)
      label        — full display label (e.g. "Closed (Awarded)")
      badge        — compact card badge text (e.g. "Closed")
      is_open      — bool: currently open for bidding
      is_awarded   — bool: already awarded (awarded or expired)
      explanation  — one sentence of plain context for the detail page
    """
    code = status_code(row)
    label = STATUS_LABELS[code]
    explanations = {
        OPEN: (
            "This opportunity is currently posted on SAM.gov. Confirm the "
            "response deadline before preparing an offer."
        ),
        CLOSED_AWARDED: (
            "This contract has already been awarded. It is shown for recompete "
            "intelligence and incumbent research — you cannot submit a proposal "
            "against this award."
        ),
        CLOSED_EXPIRED: (
            "This contract's period of performance has ended. It is shown for "
            "recompete intelligence and incumbent research — watch for the "
            "follow-on solicitation."
        ),
        CANCELLED: (
            "The source shows this procurement was cancelled. It is shown for "
            "historical and incumbent-research context only."
        ),
    }
    return {
        "code": code,
        "label": label,
        "badge": STATUS_BADGE[code],
        "is_open": code == OPEN,
        "is_awarded": code in (CLOSED_AWARDED, CLOSED_EXPIRED),
        "explanation": explanations[code],
    }
