"""Pure deterministic functions for Business Match scoring and explanation.

No DB calls, no Flask dependencies. All inputs are plain dicts.

NAICS matching extracts sam_naics from raw_json when present. Geographic
filtering is not yet supported (contracts lack a performance_state column).
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
    """Return the NAICS code stored in raw_json, or None if unavailable."""
    raw = contract.get("raw_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get("sam_naics") or data.get("naics_code") or None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _naics_matches(contract_naics: str, profile_codes: list[str]) -> bool:
    """True when contract_naics shares a 6-digit prefix with any profile code."""
    if not contract_naics or not profile_codes:
        return False
    cn = contract_naics.strip()[:6]
    for code in profile_codes:
        pc = code.strip()[:6]
        if cn and pc and cn == pc:
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


def business_match_score(contract, profile) -> int:
    """Return a 0–100 Business Match score for a contract against a company profile.

    Weights:
      - NAICS match  : 35 pts  (only when contract has sam_naics AND profile has codes)
      - Agency match : 25 pts  (only when profile has preferred agencies)
      - Value range  : 25 pts  (only when profile has min or max value)
      - Set-aside    : 15 pts  (only when profile has set-asides AND contract has competition_type)

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
            possible += 25
            in_min = (contract_value >= min_val) if min_val is not None else True
            in_max = (contract_value <= max_val) if max_val is not None else True
            if in_min and in_max:
                earned += 25

    # Set-aside
    profile_set_asides = profile.get("set_asides") or []
    competition_type = contract.get("competition_type") or ""
    if profile_set_asides and competition_type:
        possible += 15
        if any(_comp_type_matches_set_aside(competition_type, sa) for sa in profile_set_asides):
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

    return reasons


def profile_filter_for_sql(profile) -> dict:
    """Translate a company profile into kwargs understood by get_contracts().

    Returns a dict with keys: agencies (list), min_value (float|None),
    max_value (float|None), set_aside_keywords (list[str]).
    """
    if not profile:
        return {}
    return {
        "agencies": profile.get("agencies") or [],
        "min_value": profile.get("min_contract_value"),
        "max_value": profile.get("max_contract_value"),
        "set_aside_keywords": _set_aside_sql_keywords(profile.get("set_asides") or []),
    }


def _set_aside_sql_keywords(set_aside_codes: list[str]) -> list[str]:
    """Return a flat list of competition_type substrings to OR-match in SQL."""
    keywords = []
    for code in set_aside_codes:
        keywords.extend(_SET_ASIDE_MAP.get(code, []))
    return keywords
