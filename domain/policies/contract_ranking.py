"""Shared contract ranking policy (domain layer).

A single deterministic, stateless ordering policy for contracts, reusable by
pipeline, search, recommendation ranking, and compare_insights.

Policy:
    1. recompete_score  — higher first (primary)
    2. value            — higher first (tiebreaker)

The recompete_score already encodes timing quality: contracts in the 365–540 day
best-pursuit-window earn the maximum timing component, so urgency is not a
separate secondary sort criterion. Ranking by "soonest expiry" would unfairly
prefer near-expired contracts that are too late for a new challenger to pursue.

Pure: no DB, config, time, randomness, or external services.
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


def _rank_key(row):
    """Composite sort key: (-score, -value)."""
    return (-_score_of(row), -_value_of(row))


def rank_contracts(contracts):
    """Return contracts ordered by the recompete ranking policy (best first).

    Pure and stable: identical input order yields identical output order. Does
    not mutate the input list or its rows.
    """
    return sorted(contracts, key=_rank_key)
