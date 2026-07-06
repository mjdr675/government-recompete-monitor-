import logging
import os
import time
from datetime import date, timedelta

import requests

logger = logging.getLogger("ingest")

API_URL = "https://api.sam.gov/opportunities/v2/search"

# SAM.gov enforces tight daily request quotas. Once we get a 429 the quota is
# effectively spent for a while, so retrying each lookup is futile and only
# slows the ingest. Trip a process-wide cooldown instead: skip further SAM
# calls (logging once) until it elapses, so one exhausted quota doesn't stall
# the whole run. Overridable via env for tests/ops.
RATE_LIMIT_COOLDOWN_SECONDS = int(os.getenv("SAM_RATE_LIMIT_COOLDOWN", "300"))
_rate_limited_until = 0.0

_REDACTED = "***REDACTED***"


def _redact(text, secret):
    """Strip the SAM API key from text before it reaches the logs.

    requests exceptions (connection errors, HTTPError from raise_for_status)
    embed the full request URL — including the ``api_key`` query param — in
    their string form. Logging that verbatim leaks the key in cleartext, so
    replace any occurrence of the key value with a redaction marker.
    """
    s = str(text)
    if secret:
        s = s.replace(secret, _REDACTED)
    return s


def lookup_solicitation(solnum):
    """Look up a SAM.gov solicitation by number.

    Returns a dict of sam_* fields on a match, or None on no match / missing
    key / error. Unlike the previous bare-except version, rate limits (429) and
    auth errors (401/403) are logged distinctly so an exhausted SAM quota is no
    longer indistinguishable from "no solicitation found".
    """
    global _rate_limited_until

    api_key = os.getenv("SAM_API_KEY")
    if not api_key or not solnum:
        return None

    if time.time() < _rate_limited_until:
        return None  # recently rate-limited; already logged, skip quietly

    today = date.today()
    params = {
        "api_key": api_key,
        "solnum": solnum,
        "postedFrom": (today - timedelta(days=365)).strftime("%m/%d/%Y"),
        "postedTo": (today + timedelta(days=365)).strftime("%m/%d/%Y"),
        "limit": 1,
        "offset": 0,
    }

    try:
        r = requests.get(API_URL, params=params, timeout=20)
    except Exception as e:
        logger.warning(
            "sam lookup solnum=%s connection error: %s", solnum, _redact(e, api_key)
        )
        return None

    if r.status_code == 429:
        retry_after = r.headers.get("Retry-After")
        _rate_limited_until = time.time() + RATE_LIMIT_COOLDOWN_SECONDS
        logger.warning(
            "sam lookup solnum=%s rate-limited (429, retry_after=%s) — SAM daily quota "
            "likely exhausted; pausing SAM enrichment for %ds",
            solnum, retry_after, RATE_LIMIT_COOLDOWN_SECONDS,
        )
        return None

    if r.status_code in (401, 403):
        logger.warning(
            "sam lookup solnum=%s auth error (%d) — check SAM_API_KEY validity",
            solnum, r.status_code,
        )
        return None

    try:
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(
            "sam lookup solnum=%s response error: %s", solnum, _redact(e, api_key)
        )
        return None

    opportunities = data.get("opportunitiesData") or data.get("data") or []
    if not opportunities:
        return None

    item = opportunities[0]
    return {
        "sam_title": item.get("title", ""),
        "sam_type": item.get("type", ""),
        "sam_due_date": item.get("responseDeadLine", ""),
        "sam_set_aside": item.get("setAside", ""),
        "sam_naics": item.get("naicsCode", ""),
        "sam_url": item.get("uiLink", ""),
    }
