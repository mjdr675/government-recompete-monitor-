from urllib.parse import urlencode

_FILTER_LABELS = {
    "days": "Expiring within",
    "min_days_left": "Min days left",
    "priority": "Priority",
    "min_value": "Min value",
    "naics_code": "NAICS",
    "agency": "Agency",
    "keywords": "Keywords",
}


def format_filter_value(key: str, value) -> str:
    if key == "days":
        return f"{value} days"
    if key == "min_days_left":
        return f"{value}+ days"
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


# Filter keys that show up as removable chips on the contracts page, in display
# order. Labels here favour brevity (chips are small); they intentionally differ
# from _FILTER_LABELS in a couple of spots ("Search", "State", "Category").
_CHIP_LABELS = {
    "q": "Search",
    "naics_code": "NAICS",
    "agency": "Agency",
    "category": "Category",
    "state": "State",
    "priority": "Priority",
    "days": "Expiring within",
    "min_days_left": "Min days left",
    "min_value": "Min value",
    # Labeled "Expiry" (not "Status") to avoid colliding with the separate
    # procurement-status Open/Closed filter — this one is purely
    # days_remaining-based and says nothing about procurement status.
    "status": "Expiry",
}

# Params that are not filters but must survive when a chip is removed (so sort
# order / mode toggles aren't lost). "page" is deliberately excluded: removing a
# filter changes the result set, so we reset to page 1.
_PRESERVED_PARAMS = ("sort", "dir", "for_my_business", "in_pipeline", "discover")

_STATUS_CHIP_VALUES = {"open": "Not expired", "expired": "Expired"}


def _format_chip_value(key, value):
    """Human-readable value for a filter chip (shorter than the views summary)."""
    if key == "days":
        return f"{value} days"
    if key == "min_days_left":
        return f"{value}+ days"
    if key == "priority":
        return str(value).title()
    if key == "status":
        return _STATUS_CHIP_VALUES.get(str(value), str(value))
    if key == "min_value":
        try:
            v = int(float(value))
        except (ValueError, TypeError):
            return str(value)
        if v >= 1_000_000:
            n = v / 1_000_000
            return f"${n:.0f}M+" if n == int(n) else f"${n:g}M+"
        if v >= 1_000:
            return f"${v // 1000}K+"
        return f"${v:,}+"
    return str(value)


def active_filter_chips(args):
    """Build removable active-filter chips from request args.

    ``args`` is any mapping of query params (e.g. ``request.args.to_dict()``).
    Returns a list of ``{key, label, value, remove_url}`` — one per applied
    filter, in a stable display order. ``remove_url`` points back at
    ``/contracts`` with that single filter dropped, all other filters and the
    preserved params (sort/dir/mode toggles) kept, and pagination reset.

    Empty/blank filter values produce no chip. Non-filter params never appear as
    chips but are preserved in every ``remove_url``.
    """
    # Normalise to plain str values, ignoring blanks.
    present = {
        k: str(v).strip()
        for k, v in args.items()
        if v is not None and str(v).strip() != ""
    }

    chips = []
    for key, label in _CHIP_LABELS.items():
        if key not in present:
            continue
        value = present[key]
        # Everything still applied EXCEPT this one filter, plus preserved params.
        remaining = {
            k: val for k, val in present.items()
            if k != key and (k in _CHIP_LABELS or k in _PRESERVED_PARAMS)
        }
        remove_url = "/contracts" + ("?" + urlencode(remaining) if remaining else "")
        chips.append({
            "key": key,
            "label": label,
            "value": _format_chip_value(key, value),
            "remove_url": remove_url,
        })
    return chips


# Curated subset of SAVED_VIEWS surfaced as one-click chips on the contracts
# page. Keeps the most common research starting points within reach without
# duplicating the full /views catalogue.
QUICK_VIEW_KEYS = [
    "critical-expiring",
    "expiring-soon",
    "open-contracts",
    "high-value-contracts",
    "cleaning-contracts",
    "grounds-contracts",
    "it-contracts",
    "cybersecurity-contracts",
]


def quick_views():
    """Return ``[{id, label}]`` for the curated quick-access presets.

    Skips any key missing from SAVED_VIEWS so the list never breaks if a preset
    is renamed or removed.
    """
    return [
        {"id": key, "label": SAVED_VIEWS[key]["label"]}
        for key in QUICK_VIEW_KEYS
        if key in SAVED_VIEWS
    ]


def active_view_id(args):
    """Return the SAVED_VIEWS key whose filters exactly match the applied filters.

    "Exactly" means every filter param currently set equals the preset's filters
    and no extra filter params are set. Sort/paging/mode toggles are ignored.
    Returns ``None`` when no preset matches, letting the contracts page highlight
    the preset a user is currently inside (filter-state visibility).
    """
    applied = {
        k: str(v).strip()
        for k, v in args.items()
        if k in _CHIP_LABELS and v is not None and str(v).strip() != ""
    }
    if not applied:
        return None
    for key, view in SAVED_VIEWS.items():
        preset = {k: str(v) for k, v in view.get("filters", {}).items()}
        if preset == applied:
            return key
    return None


SAVED_VIEWS = {
    "critical-expiring": {
        "label": "Critical + Expiring Soon",
        "description": "CRITICAL-priority contracts expiring within 90 days — highest-urgency opportunities. These have the best combination of competitive bid type, value, and timing. Act before the window closes.",
        "filters": {
            "priority": "CRITICAL",
            "days": 90,
        },
    },
    "open-contracts": {
        "label": "Open Solicitations",
        "description": "Contracts with an open SAM.gov solicitation — actively accepting bids right now. Sorted by days remaining so the most time-sensitive appear first.",
        "filters": {
            "status": "open",
        },
    },
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
    },
    "facilities-contracts": {
        "label": "Facilities Contracts",
        "description": "Browse Facilities contracts filtered by category.",
        "filters": {
            "category": "Facilities"
        }
    },
    "cleaning-contracts": {
        "label": "Cleaning / Janitorial",
        "description": "Browse cleaning / janitorial matched by your current filters.",
        "filters": {"category": "Cleaning"}
    },
    "grounds-contracts": {
        "label": "Grounds / Landscaping",
        "description": "Browse grounds / landscaping matched by your current filters.",
        "filters": {"category": "Grounds"}
    },
    "it-contracts": {
        "label": "IT Contracts",
        "description": "Browse it contracts matched by your current filters.",
        "filters": {"category": "IT"}
    },
    "cybersecurity-contracts": {
        "label": "Cybersecurity Contracts",
        "description": "Browse cybersecurity contracts matched by your current filters.",
        "filters": {"category": "Cybersecurity"}
    },
    "construction-contracts": {
        "label": "Construction Contracts",
        "description": "Browse construction contracts matched by your current filters.",
        "filters": {"category": "Construction"}
    },
    "security-contracts": {
        "label": "Physical Security",
        "description": "Browse physical security matched by your current filters.",
        "filters": {"category": "Security"}
    },
    "logistics-contracts": {
        "label": "Logistics Contracts",
        "description": "Browse logistics contracts matched by your current filters.",
        "filters": {"category": "Logistics"}
    },
}


def build_view_query(view_id: str) -> str:
    view = SAVED_VIEWS.get(view_id)
    if not view:
        return ""
    return urlencode(view["filters"])


def contract_search_url(category=None, state=None, agency=None, naics_code=None):
    """Build a /contracts search URL from contract-level metadata.

    Priority: category > agency > NAICS prefix. State is appended when
    category or agency is set. Returns "/contracts" when no useful signals
    are available so callers always get a valid URL.
    """
    params = {}
    if category and str(category).strip().lower() not in ("", "other", "unknown"):
        params["category"] = category.strip()
        if state:
            params["state"] = str(state).strip()
    elif agency and str(agency).strip():
        params["agency"] = agency.strip()
    elif naics_code and str(naics_code).strip():
        # 4-digit prefix catches related sub-sectors without over-filtering
        params["naics_code"] = str(naics_code).strip()[:4]
    if not params:
        return "/contracts"
    return "/contracts?" + urlencode(params)
