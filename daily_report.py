from datetime import date, timedelta
from analytics import (
    new_opportunities,
    removed_opportunities,
    list_new_opportunities,
    list_removed_opportunities,
    list_priority_changes,
)

today = str(date.today())
yesterday = str(date.today() - timedelta(days=1))

print("=" * 60)
print("Government Recompete Daily Report")
print(today)
print("=" * 60)

print(f"New opportunities      : {new_opportunities(today, yesterday)}")
print(f"Removed opportunities  : {removed_opportunities(today, yesterday)}")
print(f"Priority upgrades      : {len(list_priority_changes(today, yesterday, 'up'))}")
print(f"Priority downgrades    : {len(list_priority_changes(today, yesterday, 'down'))}")

print("\nNEW OPPORTUNITIES")
print("-" * 60)

rows = list_new_opportunities(today, yesterday)

if not rows:
    print("None")
else:
    for p, agency, vendor, value, days, award in rows:
        print(f"[{p}] {agency}")
        print(f"  Vendor : {vendor}")
        print(f"  Value  : ${value:,.0f}")
        print(f"  Days   : {days}")
        print(f"  Award  : {award}")
        print()

print("\nREMOVED OPPORTUNITIES")
print("-" * 60)

rows = list_removed_opportunities(today, yesterday)

if not rows:
    print("None")
else:
    for p, agency, vendor, value, days, award in rows:
        print(f"[{p}] {agency}")
        print(f"  Vendor : {vendor}")
        print(f"  Value  : ${value:,.0f}")
        print(f"  Days   : {days}")
        print(f"  Award  : {award}")
        print()

print("\nPRIORITY UPGRADES")
print("-" * 60)

rows = list_priority_changes(today, yesterday, "up")

if not rows:
    print("None")
else:
    for old_p, new_p, agency, vendor, value, days, award in rows:
        print(f"{old_p} -> {new_p}")
        print(f"  {agency}")
        print(f"  {vendor}")
        print(f"  ${value:,.0f}")
        print()

print("\nPRIORITY DOWNGRADES")
print("-" * 60)

rows = list_priority_changes(today, yesterday, "down")

if not rows:
    print("None")
else:
    for old_p, new_p, agency, vendor, value, days, award in rows:
        print(f"{old_p} -> {new_p}")
        print(f"  {agency}")
        print(f"  {vendor}")
        print(f"  ${value:,.0f}")
        print()
