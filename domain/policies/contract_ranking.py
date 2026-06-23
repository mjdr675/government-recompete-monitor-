"""Shared contract ranking policy (domain layer).

A single deterministic, stateless ordering policy for contracts, extracted
verbatim from contract_summary.compare_insights() so it can be reused by
pipeline, search, and recommendation ranking later without re-deriving it.

Policy (unchanged):
    1. recompete_score  — higher first (primary)
    2. days_remaining   — sooner first, ACTIVE contracts only (urgency);
                          non-active / unknown sort last
    3. value            — higher first (tiebreaker)

Pure: no DB, config, time, randomness, or external services. The helpers below
replicate exactly the normalization previously embedded in compare_insights so
ordering is byte-identical.
"""


def _safe_int(v):
    """Identical to contract_summary._safe_int — int or None, never raises."""
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _score_of(row):
    return _safe_int(row.get("recompete_score")) or 0


def _value_of(row):
    try:
        return float(row.get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


def _active_days(row):
    """Positive days_remaining for active contracts, else None."""
    d = _safe_int(row.get("days_remaining"))
    return d if (d is not None and d > 0) else None


def _rank_key(row):
    """Composite sort key: (-score, urgency, -value).

    urgency uses a large sentinel for non-active/unknown days so active
    contracts (smaller positive days) sort ahead of them.
    """
    urgency = _active_days(row)
    urgency = urgency if urgency is not None else 10 ** 9
    return (-_score_of(row), urgency, -_value_of(row))


def rank_contracts(contracts):
    """Return contracts ordered by the recompete ranking policy (best first).

    Pure and stable: identical input order yields identical output order. Does
    not mutate the input list or its rows. Ties beyond (score, urgency, value)
    preserve input order (Python's sort is stable).
    """
    return sorted(contracts, key=_rank_key)
