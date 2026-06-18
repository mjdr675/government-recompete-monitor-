from datetime import date

from report_builder import CHANGE_TYPES, build_report


def money(value):
    return f"${float(value or 0):,.0f}"


today = str(date.today())
report = build_report(today)

print("=" * 60)
print("Government Recompete Daily Report")
print(report["run_date"])
print("=" * 60)

for t in CHANGE_TYPES:
    print(f"{t:<15}: {report['summary'].get(t, 0)}")

print()

for t in CHANGE_TYPES:
    print(t)
    print("-" * 60)

    rows = report["changes"].get(t, [])

    if not rows:
        print("None\n")
        continue

    for _, _, _, _, desc in rows:
        print(desc)

    print()

print("=" * 60)
print("VALUE SUMMARY")
print("=" * 60)

values = report["value_summary"]
print(f"New Value      : {money(values['new_value'])}")
print(f"Upgraded Value : {money(values['upgrade_value'])}")
print(f"Removed Value  : {money(values['removed_value'])}")
print(f"Net Change     : {money(values['net_value'])}")
print()

print("=" * 60)
print("TOP AGENCIES")
print("=" * 60)

rows = report["top_agencies"]

if not rows:
    print("No agency changes today.")
else:
    for agency, changes, value in rows:
        print(f"{agency}")
        print(f"  Changes : {changes}")
        print(f"  Value   : {money(value)}")
        print()

print("=" * 60)
print("TOP VENDORS")
print("=" * 60)

rows = report["top_vendors"]

if not rows:
    print("No vendor changes today.")
else:
    for vendor, changes, value in rows:
        print(vendor or "(Unknown Vendor)")
        print(f"  Changes : {changes}")
        print(f"  Value   : {money(value)}")
        print()

print("=" * 60)
print("TOP OPPORTUNITIES")
print("=" * 60)

rows = report["top_opportunities"]

if not rows:
    print("No top opportunities today.")
else:
    for i, r in enumerate(rows, 1):
        print(f"{i}. {r['priority']} | {money(r['value'])} | {r['change_type']}")
        print(f"   Agency         : {r.get('agency') or ''}")
        print(f"   Vendor         : {r.get('vendor') or ''}")
        print(f"   Days Remaining : {r.get('days_remaining') or ''}")
        print(f"   Score          : {r.get('recompete_score') or ''}")
        print(f"   Award ID       : {r.get('award_id') or ''}")
        print()
