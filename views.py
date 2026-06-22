from urllib.parse import urlencode

_FILTER_LABELS = {
    "days": "Expiring within",
    "priority": "Priority",
    "min_value": "Min value",
    "naics_code": "NAICS",
    "agency": "Agency",
    "keywords": "Keywords",
}


def format_filter_value(key: str, value) -> str:
    if key == "days":
        return f"{value} days"
    if key == "priority":
        return str(value).title()
    if key == "min_value":
        try:
            return f"${int(value):,}"
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def format_filter_summary(filters: dict) -> str:
    """Return a human-readable summary of a filter dict, e.g. 'Priority: Critical, Expiring within: 90 days'."""
    parts = []
    for key, value in filters.items():
        label = _FILTER_LABELS.get(key, key)
        formatted = format_filter_value(key, value)
        parts.append(f"{label}: {formatted}")
    return ", ".join(parts)

SAVED_VIEWS = {
    "dod-critical": {
        # "DoD" = U.S. Department of Defense. Label spelled out for clarity since it
        # was the only preset using a bare acronym; the agency filter is "DEFENSE".
        "label": "Defense (DoD) Critical Contracts",
        "filters": {
            "agency": "DEFENSE",
            "priority": "CRITICAL"
        }
    },
    "high-value-contracts": {
        "label": "High Value Contracts",
        "filters": {
            "min_value": 1000000
        }
    },
    "top-risk-agencies": {
        "label": "Top Risk Agencies",
        "filters": {
            "priority": "CRITICAL"
        }
    },
    "expiring-soon": {
        "label": "Expiring Soon",
        "filters": {
            "days": 90
        }
    }
}


def build_view_query(view_id: str) -> str:
    view = SAVED_VIEWS.get(view_id)
    if not view:
        return ""
    return urlencode(view["filters"])
