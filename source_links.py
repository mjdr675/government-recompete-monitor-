"""source_links.py — canonical, source-aware outbound link resolver.

Every contract in this system originates from USASpending (``spending_by_award``).
Some are additionally enriched with a SAM.gov opportunity notice. The external
"source" link on a contract must therefore point at the record's *actual
authoritative source*, not universally at SAM.gov:

  * A contract enriched with a real, validated SAM.gov opportunity URL (an
    active / prior notice) links to that SAM.gov record.
  * Otherwise the record is a USASpending contract award and links to its
    USASpending award page, which is deterministically derivable from the
    stable, documented ``generated_internal_id`` permalink id
    (``https://www.usaspending.gov/award/<generated_internal_id>``).
  * Only when neither an exact record nor a strong identifier exists do we fall
    back to a source-specific search, then a general search.

Resolution tiers (highest priority first):

    1  exact_stored   — a validated stored authoritative URL (``sam_url`` or any
                        other allowlisted government host).
    2  exact_derived  — USASpending award page from ``generated_internal_id``.
    3  source_search  — a source-specific search on the strongest identifier
                        (SAM.gov search on the incumbent solicitation number —
                        a genuinely SAM-specific id for the follow-on notice).
    4  general_search — a broad SAM.gov keyword search (agency + work type).
    5  none           — no safe, meaningful destination → no external button.

We never *fabricate* an exact record path from an undocumented convention:
there is no public URL that maps an award/PIID to a SAM.gov opportunity record,
so USASpending-originated awards are never sent to a SAM.gov record page merely
because a PIID can be searched there.

Pure: no DB, network, clock, or secrets. Callers pass a plain row dict.
Internal ids are never placed in an outbound URL.
"""

import re
from urllib.parse import quote, urlparse

# ── Supported authoritative government sources ────────────────────────────────
SAM = "sam.gov"
USASPENDING = "usaspending"

_SAM_SEARCH_BASE = "https://sam.gov/search/?keywords="
_USA_AWARD_BASE = "https://www.usaspending.gov/award/"

# Cap the general-search keyword string so a huge description can't build an
# unwieldy URL.
_GENERAL_TERMS_MAXLEN = 120

# USASpending ``generated_internal_id`` tokens look like
# ``CONT_AWD_N6274219F0181_9700_N6274215D1818_9700`` / ``ASST_NON_...`` — only
# ASCII word chars, dot and hyphen. Anything else is refused rather than pasted
# into a URL (no-fabrication guard).
_GID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

# Destination-aware CTA labels (see PM decision B / procurement-status task).
_LABEL_OPPORTUNITY = "View Opportunity"
_LABEL_AWARD = "View Award"
_LABEL_SEARCH = "View Source"


def _host_source(url):
    """Return the source key for a safe, allowlisted government URL, else None.

    ``SAM`` for sam.gov (and subdomains), ``USASPENDING`` for usaspending.gov
    (and subdomains). HTTPS-only; rejects empty/None, non-https schemes
    (javascript:, data:, http:, ftp:, scheme-relative), embedded userinfo, and
    host-spoofing (e.g. ``sam.gov.evil.com``). Validates the parsed hostname,
    never a string prefix.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    # Embedded credentials (https://evil.com@sam.gov/...) are a phishing smell —
    # refuse outright even though .hostname would resolve to the real host.
    if "@" in parsed.netloc:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host == "sam.gov" or host.endswith(".sam.gov"):
        return SAM
    if host == "usaspending.gov" or host.endswith(".usaspending.gov"):
        return USASPENDING
    return None


def is_safe_source_url(url):
    """True only for an https URL on a supported authoritative government host."""
    return _host_source(url) is not None


def _usaspending_award_url(gid):
    return _USA_AWARD_BASE + quote(str(gid).strip(), safe="")


def _sam_narrow_search_url(solicitation_id):
    return _SAM_SEARCH_BASE + quote(str(solicitation_id).strip(), safe="")


def _sam_general_search_url(row):
    terms = " ".join(
        filter(None, [(row.get("agency") or "").strip(), (row.get("description") or "").strip()])
    )[:_GENERAL_TERMS_MAXLEN]
    return _SAM_SEARCH_BASE + quote(terms, safe="")


def _result(url, source, destination_type, label, tier, kind, is_exact):
    """Build the structured resolution result.

    Keys:
      url               — destination URL, or None when nothing safe is linkable
      source            — "sam.gov" | "usaspending" | None
      destination_type  — "opportunity" | "award" | "search" | None
      label             — destination-aware CTA label, or None
      tier              — 1..5 resolution tier (5 = no destination)
      kind              — legacy shape: "exact" | "narrow_search" |
                          "general_search" | "none"
      is_exact          — True only for an exact record (tier 1 or 2)
    """
    return {
        "url": url,
        "source": source,
        "destination_type": destination_type,
        "label": label,
        "tier": tier,
        "kind": kind,
        "is_exact": is_exact,
    }


def resolve_source_destination(row):
    """Resolve the strongest safe authoritative destination for a contract row.

    Deterministic: identical rows always yield identical results. See module
    docstring for the tier precedence.
    """
    # Tier 1 — exact stored authoritative URL (any allowlisted government host).
    stored = (row.get("sam_url") or "").strip()
    src = _host_source(stored)
    if src == SAM:
        return _result(stored, SAM, "opportunity", _LABEL_OPPORTUNITY, 1, "exact", True)
    if src == USASPENDING:
        return _result(stored, USASPENDING, "award", _LABEL_AWARD, 1, "exact", True)

    # Tier 2 — USASpending award page derived from the stable, documented
    # generated_internal_id permalink. This is where a USASpending-originated
    # award record resolves — never a SAM.gov record page it never had.
    gid = str(row.get("generated_internal_id") or "").strip()
    if gid and _GID_RE.match(gid):
        return _result(_usaspending_award_url(gid), USASPENDING, "award",
                       _LABEL_AWARD, 2, "exact", True)

    # Tier 3 — source-specific search on the strongest identifier. The incumbent
    # solicitation number is a genuinely SAM-specific id for the follow-on
    # notice, so a prefilled SAM.gov search is a meaningful source destination.
    solicitation_id = (row.get("solicitation_id") or "").strip()
    if solicitation_id:
        return _result(_sam_narrow_search_url(solicitation_id), SAM, "search",
                       _LABEL_SEARCH, 3, "narrow_search", False)

    # Tier 4 — general SAM.gov keyword search (agency + work type). Only when it
    # produces a non-empty query; an empty search is not a meaningful link.
    terms = " ".join(
        filter(None, [(row.get("agency") or "").strip(), (row.get("description") or "").strip()])
    ).strip()
    if terms:
        return _result(_sam_general_search_url(row), SAM, "search",
                       _LABEL_SEARCH, 4, "general_search", False)

    # Tier 5 — nothing safe or meaningful to link to; render no external button.
    return _result(None, None, None, None, 5, "none", False)
