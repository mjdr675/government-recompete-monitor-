from urllib.parse import urlencode

SAVED_VIEWS = {
    "dod-critical": {
        "label": "DoD Critical Contracts",
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
