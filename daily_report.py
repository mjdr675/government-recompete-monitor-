from datetime import date

from db import change_summary, get_changes
from analytics import agency_summary, top_opportunities, value_summary, vendor_summary

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
print("VALUE SUMMARY")
print("=" * 60)

values = value_summary(today)

new_value = values.get("NEW", 0) + values.get("NEW_TIER_A", 0)
upgrade_value = values.get("UPGRADE", 0)
removed_value = values.get("REMOVED", 0)
net_value = new_value + upgrade_value - removed_value

print(f"New Value      : ${new_value:,.0f}")
print(f"Upgraded Value : ${upgrade_value:,.0f}")
print(f"Removed Value  : ${removed_value:,.0f}")
print(f"Net Change     : ${net_value:,.0f}")
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



print("=" * 60)
print("TOP VENDORS")
print("=" * 60)

rows = vendor_summary(today)

if not rows:
    print("No vendor changes today.")
else:
    for vendor, changes, value in rows:
        print(vendor or "(Unknown Vendor)")
        print(f"  Changes : {changes}")
        print(f"  Value   : ${value:,.0f}")
        print()
print("=" * 60)
print("TOP OPPORTUNITIES")
print("=" * 60)

rows = top_opportunities(today, limit=10)

if not rows:
    print("No top opportunities today.")
else:
    for i, r in enumerate(rows, 1):
        value = float(r["value"] or 0)
        print(f"{i}. {r['priority']} | ${value:,.0f} | {r['change_type']}")
        print(f"   Agency         : {r.get('agency') or ''}")
        print(f"   Vendor         : {r.get('vendor') or ''}")
        print(f"   Days Remaining : {r.get('days_remaining') or ''}")
        print(f"   Score          : {r.get('recompete_score') or ''}")
        print(f"   Award ID       : {r.get('award_id') or ''}")
        print()

