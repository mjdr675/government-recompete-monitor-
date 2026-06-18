from datetime import date, timedelta

from analytics import (
    list_new_opportunities,
    list_removed_opportunities,
    list_priority_changes,
)
from db import clear_changes_for_date, insert_change


def describe(row):
    # row shape: priority, agency, vendor, value, days_remaining, award_id
    priority, agency, vendor, value, days, award = row
    return f"[{priority}] {agency} | {vendor} | ${value:,.0f} | {days} days | {award}"


def record_daily_changes(today=None, yesterday=None):
    today = today or str(date.today())
    yesterday = yesterday or str(date.today() - timedelta(days=1))

    clear_changes_for_date(today)

    for row in list_new_opportunities(today, yesterday, limit=100):
        priority, agency, vendor, value, days, award = row
        insert_change(today, "NEW", award, None, priority, describe(row))

    for row in list_removed_opportunities(today, yesterday, limit=100):
        priority, agency, vendor, value, days, award = row
        insert_change(today, "REMOVED", award, priority, None, describe(row))

    for row in list_priority_changes(today, yesterday, "up", limit=100):
        old_priority, new_priority, agency, vendor, value, days, award = row
        desc = f"{old_priority} -> {new_priority} | {agency} | {vendor} | ${value:,.0f} | {days} days | {award}"
        insert_change(today, "UPGRADE", award, old_priority, new_priority, desc)

    for row in list_priority_changes(today, yesterday, "down", limit=100):
        old_priority, new_priority, agency, vendor, value, days, award = row
        desc = f"{old_priority} -> {new_priority} | {agency} | {vendor} | ${value:,.0f} | {days} days | {award}"
        insert_change(today, "DOWNGRADE", award, old_priority, new_priority, desc)

    print(f"Recorded changes for {today} vs {yesterday}")


if __name__ == "__main__":
    record_daily_changes()
