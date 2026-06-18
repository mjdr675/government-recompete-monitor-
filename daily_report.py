from datetime import date

from db import change_summary, get_changes

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

from analytics import agency_summary

print("=" * 60)
print("AGENCY SUMMARY")
print("=" * 60)

rows = agency_summary(today)

if not rows:
    print("No agency changes today.")
else:
    for change_type, count in rows:
        print(f"{change_type:<15} {count}")

