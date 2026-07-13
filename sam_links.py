"""sam_links.py — backward-compatible SAM.gov adapter over ``source_links``.

Source-link resolution is centralized in :mod:`source_links` (the single,
source-aware resolver used by the routes/templates). This module preserves the
older SAM-focused public API — ``is_safe_external_url`` and
``resolve_apply_destination`` — so existing callers and tests keep working, by
delegating to the canonical resolver rather than duplicating link logic.

``is_safe_external_url`` remains a SAM-only gate (True only for https sam.gov);
``resolve_apply_destination`` returns the legacy ``{url, kind, is_exact}`` shape.
"""

from source_links import _host_source, resolve_source_destination


def is_safe_external_url(url):
    """True only for an https URL whose host is sam.gov (or a sam.gov subdomain).

    Backward-compatible SAM-only safety gate. Rejects empty/None, non-https
    schemes, userinfo-embedding / host-spoofing attempts, and any non-SAM host.
    """
    return _host_source(url) == "sam.gov"


def resolve_apply_destination(row):
    """Return the canonical destination for a contract row (legacy shape).

    Delegates to :func:`source_links.resolve_source_destination` and projects
    its structured result onto the legacy ``{url, kind, is_exact}`` contract.
    """
    d = resolve_source_destination(row)
    return {"url": d["url"], "kind": d["kind"], "is_exact": d["is_exact"]}
