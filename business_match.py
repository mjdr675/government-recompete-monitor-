"""Pure deterministic functions for Business Match scoring and explanation.

No DB calls, no Flask dependencies. All inputs are plain dicts.

NAICS matching extracts sam_naics from raw_json when present. State matching
uses place_of_performance_state on the contract dict. PSC matching uses
psc_code on the contract dict with prefix-hierarchy logic (same as NAICS).
"""

import json

# Set-aside code → substrings to look for in competition_type (case-insensitive)
_SET_ASIDE_MAP = {
    "small_business": ["SMALL BUSINESS"],
    "8a": ["8A", "8(A)"],
    "hubzone": ["HUBZONE", "HUB ZONE"],
    "sdvosb": ["SERVICE-DISABLED", "SDVOSB"],
    "wosb": ["WOMEN-OWNED", "WOSB"],
    "full_and_open": ["FULL AND OPEN"],
}

# Human-readable labels used in match/mismatch explanations
_SET_ASIDE_LABELS = {
    "small_business": "Small Business",
    "8a": "8(a)",
    "hubzone": "HUBZone",
    "sdvosb": "SDVOSB",
    "wosb": "WOSB",
    "full_and_open": "Full & Open",
}


def _naics_from_contract(contract) -> str | None:
    """Return the contract's NAICS code, preferring the dedicated column.

    Checks naics_code column first (canonical, ingest-normalised value), then
    falls back to raw_json for SAM-enriched values (sam_naics) that may differ
    from the USASpending column value.
    """
    column_val = (contract.get("naics_code") or "").strip()
    if column_val:
        return column_val
    raw = contract.get("raw_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get("sam_naics") or data.get("naics_code") or None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _naics_matches(contract_naics: str, profile_codes: list[str]) -> bool:
    """True when contract_naics starts with any profile code (prefix hierarchy).

    A profile code of "56" matches "561720"; "5617" matches "561720"; "561720"
    matches "561720" exactly.  The profile code must be 2–6 digits; shorter
    profile codes are more permissive (broader industry match).
    """
    if not contract_naics or not profile_codes:
        return False
    cn = contract_naics.strip()
    for code in profile_codes:
        pc = code.strip()
        if pc and cn.startswith(pc):
            return True
    return False


def _comp_type_matches_set_aside(competition_type: str, set_aside_code: str) -> bool:
    ct_upper = (competition_type or "").upper()
    for keyword in _SET_ASIDE_MAP.get(set_aside_code, []):
        if keyword in ct_upper:
            return True
    return False


def _agency_matches(contract_agency: str, profile_agencies: list[str]) -> bool:
    ca = (contract_agency or "").strip().lower()
    if not ca:
        return False
    for pa in profile_agencies:
        pa_lower = pa.strip().lower()
        if pa_lower and (pa_lower in ca or ca in pa_lower):
            return True
    return False


def _keyword_matches(contract, profile_keywords: list[str]) -> list[str]:
    """Return the subset of profile_keywords found in vendor/description/award_id."""
    if not profile_keywords:
        return []
    searchable = " ".join(filter(None, [
        contract.get("vendor") or "",
        contract.get("description") or "",
        contract.get("award_id") or "",
    ])).lower()
    return [kw for kw in profile_keywords if kw and kw.lower() in searchable]


def _state_matches(contract_state: str, profile_states: list[str]) -> bool:
    """True when contract's place_of_performance_state is in the profile's preferred states."""
    cs = (contract_state or "").strip().upper()
    if not cs:
        return False
    return cs in {s.strip().upper() for s in profile_states if s}


def _psc_matches(contract_psc: str, profile_psc_codes: list[str]) -> bool:
    """True when contract_psc starts with any profile PSC code (prefix hierarchy).

    A profile code of "R" matches "R499"; "R4" matches "R499"; "R499" exact.
    """
    cp = (contract_psc or "").strip().upper()
    if not cp or not profile_psc_codes:
        return False
    for code in profile_psc_codes:
        pc = code.strip().upper()
        if pc and cp.startswith(pc):
            return True
    return False


def business_match_score(contract, profile) -> int:
    """Return a 0–100 Business Match score for a contract against a company profile.

    Weights:
      - NAICS match  : 35 pts  (only when contract has sam_naics AND profile has codes)
      - Agency match : 25 pts  (only when profile has preferred agencies)
      - Value range  : 20 pts  (only when profile has min or max value)
      - Set-aside    : 10 pts  (only when profile has set-asides AND contract has competition_type)
      - Keywords     : 10 pts  (only when profile has keywords)
      - State        : 10 pts  (only when geo_coverage==states, profile has states, contract has state)
      - PSC codes    : 15 pts  (only when profile has PSC codes AND contract has psc_code)

    Each dimension is skipped (not penalised) when the data is unavailable.
    Returns 0 if profile is None or no dimension can be evaluated.
    """
    if not profile:
        return 0

    earned = 0
    possible = 0

    # NAICS
    profile_naics = profile.get("naics_codes") or []
    if profile_naics:
        contract_naics = _naics_from_contract(contract)
        if contract_naics:
            possible += 35
            if _naics_matches(contract_naics, profile_naics):
                earned += 35

    # Agency
    profile_agencies = profile.get("agencies") or []
    if profile_agencies:
        possible += 25
        if _agency_matches(contract.get("agency"), profile_agencies):
            earned += 25

    # Value range
    min_val = profile.get("min_contract_value")
    max_val = profile.get("max_contract_value")
    if min_val is not None or max_val is not None:
        contract_value = contract.get("value")
        if contract_value is not None:
            possible += 20
            in_min = (contract_value >= min_val) if min_val is not None else True
            in_max = (contract_value <= max_val) if max_val is not None else True
            if in_min and in_max:
                earned += 20

    # Set-aside
    profile_set_asides = profile.get("set_asides") or []
    competition_type = contract.get("competition_type") or ""
    if profile_set_asides and competition_type:
        possible += 10
        if any(_comp_type_matches_set_aside(competition_type, sa) for sa in profile_set_asides):
            earned += 10

    # Keywords
    profile_keywords = profile.get("keywords") or []
    if profile_keywords:
        possible += 10
        matched = _keyword_matches(contract, profile_keywords)
        if matched:
            ratio = len(matched) / len(profile_keywords)
            earned += round(10 * min(ratio, 1.0))

    # State (only active when user explicitly chose state-limited coverage)
    profile_states = profile.get("states") or []
    if profile.get("geo_coverage") == "states" and profile_states:
        contract_state = contract.get("place_of_performance_state")
        if contract_state:
            possible += 10
            if _state_matches(contract_state, profile_states):
                earned += 10

    # PSC codes
    profile_psc = profile.get("psc_codes") or []
    if profile_psc:
        contract_psc = contract.get("psc_code")
        if contract_psc:
            possible += 15
            if _psc_matches(contract_psc, profile_psc):
                earned += 15

    if possible == 0:
        return 0
    return round(earned * 100 / possible)


def business_match_reasons(contract, profile) -> list[str]:
    """Return human-readable strings for each dimension that matched."""
    if not profile:
        return []
    reasons = []

    profile_naics = profile.get("naics_codes") or []
    if profile_naics:
        contract_naics = _naics_from_contract(contract)
        if contract_naics and _naics_matches(contract_naics, profile_naics):
            reasons.append(f"Matches NAICS {contract_naics.strip()}")

    profile_agencies = profile.get("agencies") or []
    if profile_agencies and _agency_matches(contract.get("agency"), profile_agencies):
        reasons.append("Agency is in your preferred list")

    min_val = profile.get("min_contract_value")
    max_val = profile.get("max_contract_value")
    if min_val is not None or max_val is not None:
        val = contract.get("value")
        if val is not None:
            in_min = (val >= min_val) if min_val is not None else True
            in_max = (val <= max_val) if max_val is not None else True
            if in_min and in_max:
                reasons.append("Contract value fits your range")

    profile_set_asides = profile.get("set_asides") or []
    competition_type = contract.get("competition_type") or ""
    if profile_set_asides and competition_type:
        for sa in profile_set_asides:
            if _comp_type_matches_set_aside(competition_type, sa):
                label = _SET_ASIDE_LABELS.get(sa, sa)
                reasons.append(f"Matches your {label} set-aside preference")
                break

    profile_keywords = profile.get("keywords") or []
    matched_kws = _keyword_matches(contract, profile_keywords)
    if matched_kws:
        display = ", ".join(matched_kws[:3])
        reasons.append(f"Keywords match: {display}")

    profile_states = profile.get("states") or []
    if profile.get("geo_coverage") == "states" and profile_states:
        contract_state = contract.get("place_of_performance_state")
        if contract_state and _state_matches(contract_state, profile_states):
            reasons.append(f"Performance state ({contract_state.upper()}) matches your coverage")

    profile_psc = profile.get("psc_codes") or []
    if profile_psc:
        contract_psc = contract.get("psc_code")
        if contract_psc and _psc_matches(contract_psc, profile_psc):
            reasons.append(f"PSC code {contract_psc.upper()} matches your service categories")

    return reasons


def business_mismatch_reasons(contract, profile) -> list[str]:
    """Return human-readable strings for each dimension that did NOT match."""
    if not profile:
        return []
    reasons = []

    profile_naics = profile.get("naics_codes") or []
    if profile_naics:
        contract_naics = _naics_from_contract(contract)
        if contract_naics and not _naics_matches(contract_naics, profile_naics):
            reasons.append(f"NAICS {contract_naics.strip()} is outside your codes")

    profile_agencies = profile.get("agencies") or []
    if profile_agencies:
        contract_agency = (contract.get("agency") or "").strip()
        if contract_agency and not _agency_matches(contract_agency, profile_agencies):
            reasons.append("Agency is not in your preferred list")

    min_val = profile.get("min_contract_value")
    max_val = profile.get("max_contract_value")
    if min_val is not None or max_val is not None:
        val = contract.get("value")
        if val is not None:
            if min_val is not None and val < min_val:
                reasons.append(f"Contract value is below your minimum (${min_val:,.0f})")
            if max_val is not None and val > max_val:
                reasons.append(f"Contract value exceeds your maximum (${max_val:,.0f})")

    profile_states = profile.get("states") or []
    if profile.get("geo_coverage") == "states" and profile_states:
        contract_state = (contract.get("place_of_performance_state") or "").strip()
        if contract_state and not _state_matches(contract_state, profile_states):
            reasons.append(f"Performance state ({contract_state.upper()}) is outside your coverage")

    profile_psc = profile.get("psc_codes") or []
    if profile_psc:
        contract_psc = (contract.get("psc_code") or "").strip()
        if contract_psc and not _psc_matches(contract_psc, profile_psc):
            reasons.append(f"PSC code {contract_psc.upper()} is outside your service categories")

    return reasons


def profile_filter_for_sql(profile) -> dict:
    """Translate a company profile into kwargs understood by get_contracts().

    Returns a dict with keys: agencies (list), min_value (float|None),
    max_value (float|None), set_aside_keywords (list[str]),
    states (list[str] — only populated when geo_coverage == "states").
    """
    if not profile:
        return {}
    states = []
    if profile.get("geo_coverage") == "states":
        states = profile.get("states") or []
    return {
        "agencies": profile.get("agencies") or [],
        "min_value": profile.get("min_contract_value"),
        "max_value": profile.get("max_contract_value"),
        "set_aside_keywords": _set_aside_sql_keywords(profile.get("set_asides") or []),
        "states": states,
    }


def _set_aside_sql_keywords(set_aside_codes: list[str]) -> list[str]:
    """Return a flat list of competition_type substrings to OR-match in SQL."""
    keywords = []
    for code in set_aside_codes:
        keywords.extend(_SET_ASIDE_MAP.get(code, []))
    return keywords


# Profile completeness: 9 dimensions, each worth ~11 points.
_COMPLETENESS_FIELDS = [
    ("company_name", lambda p: bool(p.get("company_name"))),
    ("naics_codes", lambda p: bool(p.get("naics_codes"))),
    ("agencies", lambda p: bool(p.get("agencies"))),
    ("min_contract_value", lambda p: p.get("min_contract_value") is not None),
    ("max_contract_value", lambda p: p.get("max_contract_value") is not None),
    ("set_asides", lambda p: bool(p.get("set_asides"))),
    ("geo", lambda p: bool(p.get("states")) or p.get("geo_coverage") == "nationwide"),
    ("keywords", lambda p: bool(p.get("keywords"))),
    ("psc_codes", lambda p: bool(p.get("psc_codes"))),
]


def profile_completeness(profile) -> int:
    """Return 0–100 completion percentage for a company profile dict."""
    if not profile:
        return 0
    filled = sum(1 for _, check in _COMPLETENESS_FIELDS if check(profile))
    return round(filled * 100 / len(_COMPLETENESS_FIELDS))


def profile_completion_hints(profile) -> list[str]:
    """Return actionable one-line hints for each missing profile field."""
    if not profile:
        return ["Create your Company Profile to see personalized opportunities."]
    hints = []
    if not profile.get("naics_codes"):
        hints.append("Add your NAICS codes to match contracts in your industry.")
    if not profile.get("agencies"):
        hints.append("Choose preferred agencies to focus on the most relevant contracts.")
    if profile.get("min_contract_value") is None and profile.get("max_contract_value") is None:
        hints.append("Set your preferred contract size range.")
    if not profile.get("set_asides"):
        hints.append("Add your set-aside certifications if applicable.")
    if not profile.get("keywords"):
        hints.append("Add keywords (e.g. 'lawn care', 'janitorial', 'IT support') to improve matching.")
    return hints
