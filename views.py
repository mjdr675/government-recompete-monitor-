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
        "description": "High-priority recompete opportunities within the Department of Defense. These contracts are expiring soon, competitively awarded, and large enough to be worth pursuing.",
        "filters": {
            "agency": "DEFENSE",
            "priority": "CRITICAL"
        }
    },
    "high-value-contracts": {
        "label": "High-Value Contracts",
        "description": "Contracts worth $1 million or more across all agencies. Larger awards take longer to pursue — start early to build relationships and submit a strong bid.",
        "filters": {
            "min_value": 1000000
        }
    },
    "top-risk-agencies": {
        "label": "Critical Priority",
        "description": "All contracts scored CRITICAL (90+). These have the highest combination of competitive bid type, contract value, and time urgency — act before the window closes.",
        "filters": {
            "priority": "CRITICAL"
        }
    },
    "expiring-soon": {
        "label": "Expiring Within 90 Days",
        "description": "Contracts expiring in the next 90 days. Agencies typically issue a new solicitation 60–90 days before expiration — this window is your best opportunity to engage.",
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
