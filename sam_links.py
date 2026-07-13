"""sam_links.py — canonical SAM.gov "Apply / View on SAM.gov" destination.

The Apply action must send the user to the *most specific trustworthy* SAM.gov
destination, deterministically:

  1. exact          — the stored SAM.gov opportunity URL (``sam_url``, from the
                      SAM opportunities API ``uiLink``) when present AND it passes
                      URL-safety validation.
  2. narrow_search  — a SAM.gov search prefilled with the strongest available
                      canonical identifier (the incumbent ``solicitation_id``).
                      Used only when no exact record URL is trustworthy.
  3. general_search — the previous behaviour: a broad SAM.gov keyword search
                      built from agency + description. Final fallback only.

We never *fabricate* an exact record URL from an award identifier — there is no
documented public SAM.gov URL convention that maps an award/contract id to an
opportunity record, so guessing one would send users to a dead or wrong page.
When only an award id exists we fall back to a narrow/general search instead.

Pure: no DB, network, clock, or secrets. Callers pass a plain contract row dict.
Internal ids are never placed in an outbound URL.
"""

from urllib.parse import quote, urlparse

# Hosts we will hand a user off to for an "exact" stored link. Anything else is
# treated as untrusted and ignored (we fall back to a SAM.gov search we build).
_ALLOWED_SAM_HOSTS = ("sam.gov",)

_SAM_SEARCH_BASE = "https://sam.gov/search/?keywords="

# Cap the general-search keyword string so a huge description can't build an
# unwieldy URL.
_GENERAL_TERMS_MAXLEN = 120


def is_safe_external_url(url):
    """True only for an https URL whose host is sam.gov (or a sam.gov subdomain).

    Rejects empty/None, non-https schemes (javascript:, data:, http:, ftp:, …),
    userinfo-embedding or host-spoofing attempts, and any non-SAM host. This is
    the gate for handing a *stored* URL to the user's browser via a link.
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    # Reject embedded credentials (https://evil.com@sam.gov style is handled by
    # urlparse putting evil.com@sam.gov in .netloc; hostname is the real host,
    # but userinfo is a phishing smell — refuse it outright).
    if "@" in parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return host == "sam.gov" or host.endswith(".sam.gov")


def _narrow_search_url(solicitation_id):
    return _SAM_SEARCH_BASE + quote(str(solicitation_id).strip(), safe="")


def _general_search_url(row):
    terms = " ".join(
        filter(None, [(row.get("agency") or "").strip(), (row.get("description") or "").strip()])
    )[:_GENERAL_TERMS_MAXLEN]
    return _SAM_SEARCH_BASE + quote(terms, safe="")


def resolve_apply_destination(row):
    """Return the canonical SAM.gov destination for a contract row.

    Returns a dict:
      url      — the URL to link to (always non-empty and safe to render)
      kind     — "exact" | "narrow_search" | "general_search"
      is_exact — True only when we resolved a validated stored record URL

    Deterministic: identical rows always yield identical results.
    """
    sam_url = (row.get("sam_url") or "").strip()
    if is_safe_external_url(sam_url):
        return {"url": sam_url, "kind": "exact", "is_exact": True}

    solicitation_id = (row.get("solicitation_id") or "").strip()
    if solicitation_id:
        return {
            "url": _narrow_search_url(solicitation_id),
            "kind": "narrow_search",
            "is_exact": False,
        }

    return {"url": _general_search_url(row), "kind": "general_search", "is_exact": False}
