from datetime import date

from db import change_summary, get_changes
from analytics import agency_summary

today = str(date.today())
summary = change_summary(today)

print("=" * 60)
print("Government Recompete Daily Report")
print(today)
print("=" * 60)

for t in ("NEW", "NEW_TIER_A", "UPGRADE", "DOWNGRADE", "REMOVED"):
    print(f"{t:<15}: {summary.get(t, 0)}")

print()

for t in ("NEW", "NEW_TIER_A", "UPGRADE", "DOWNGRADE", "REMOVED"):
    print(t)
    print("-" * 60)

    rows = get_changes(today, t)

    if not rows:
        print("None\n")
        continue

    for _, _, _, _, desc in rows:
        print(desc)

    print()

print("=" * 60)
print("TOP AGENCIES")
print("=" * 60)

rows = agency_summary(today)

if not rows:
    print("No agency changes today.")
else:
    for agency, changes, value in rows:
        print(f"{agency}")
        print(f"  Changes : {changes}")
        print(f"  Value   : ${value:,.0f}")
        print()
