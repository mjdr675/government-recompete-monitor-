from db import change_summary, get_changes
from analytics import (
    agency_summary,
    top_contracts_overall,
    top_opportunities,
    value_summary,
    vendor_summary,
)


CHANGE_TYPES = ("NEW", "NEW_TIER_A", "UPGRADE", "DOWNGRADE", "REMOVED")


def build_report(run_date):
    summary = change_summary(run_date)

    values = value_summary(run_date)
    new_value = values.get("NEW", 0) + values.get("NEW_TIER_A", 0)
    upgrade_value = values.get("UPGRADE", 0)
    removed_value = values.get("REMOVED", 0)
    net_value = new_value + upgrade_value - removed_value

    return {
        "run_date": run_date,
        "summary": {t: summary.get(t, 0) for t in CHANGE_TYPES},
        "changes": {t: get_changes(run_date, t) for t in CHANGE_TYPES},
        "value_summary": {
            "new_value": new_value,
            "upgrade_value": upgrade_value,
            "removed_value": removed_value,
            "net_value": net_value,
        },
        "top_agencies": agency_summary(run_date),
        "top_vendors": vendor_summary(run_date),
        "top_opportunities": top_opportunities(run_date, limit=10),
        "top_contracts": top_contracts_overall(limit=25),
    }
