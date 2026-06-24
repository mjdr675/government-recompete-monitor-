#!/usr/bin/env python3
"""Apply the applyable-filter changes to db.py and app.py.

Run once from the repo root:
    python _patch_applyable.py

Then commit the result and delete this file:
    git add db.py app.py
    git rm _patch_applyable.py
    git commit -m 'Push applyable filter into SQL WHERE clause'
    git push
"""
import sys


def patch(path, replacements):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"ERROR: target not found in {path!r}:\n  {old[:80]!r}")
            sys.exit(1)
        content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Patched {path}")


# ── db.py ────────────────────────────────────────────────────────────────────

db_patches = [
    # 1. Add applyable=False to the signature
    (
        'def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score", direction="desc", page=1, limit=25, status="", profile_filter=None, internal_ids=None, state="", category="", exclude_ids=None, all_rows=False):',
        'def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score", direction="desc", page=1, limit=25, status="", profile_filter=None, internal_ids=None, state="", category="", exclude_ids=None, all_rows=False, applyable=False):',
    ),
    # 2. Inject the BETWEEN clause after the open/expired status filter
    (
        '    elif status == "expired":\n        base += " AND c.days_remaining <= 0"\n\n    if profile_filter:',
        '    elif status == "expired":\n        base += " AND c.days_remaining <= 0"\n\n    if applyable:\n        base += " AND c.days_remaining BETWEEN 60 AND 540"\n\n    if profile_filter:',
    ),
]

# ── app.py ───────────────────────────────────────────────────────────────────

app_patches = [
    # 1. Parse ?applyable from request args alongside ?discover
    (
        '    discover = request.args.get("discover", "")\n',
        '    discover = request.args.get("discover", "")\n    applyable = request.args.get("applyable", "")\n',
    ),
    # 2. Thread applyable into the get_contracts() call
    (
        '            exclude_ids=discover_exclude_ids,\n        )',
        '            exclude_ids=discover_exclude_ids,\n            applyable=bool(applyable),\n        )',
    ),
    # 3. Expose applyable to the template (for filter-chip / URL round-trip)
    (
        '        for_my_business=for_my_business,\n        in_pipeline=in_pipeline,\n        has_profile=profile is not None,\n    )',
        '        for_my_business=for_my_business,\n        in_pipeline=in_pipeline,\n        applyable=applyable,\n        has_profile=profile is not None,\n    )',
    ),
]

patch("db.py", db_patches)
patch("app.py", app_patches)
print("All done. Review with: git diff db.py app.py")
