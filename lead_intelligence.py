"""Deterministic Lead Intelligence: company → contract matching.

Pure functions only — no DB calls, no Flask dependencies. All inputs are plain
dicts/strings, mirroring business_match.py. The DB-aware layer (db.py) is
responsible for fetching candidate contracts and persisting results.

Goal: given a sales prospect (company + free-text notes) and Recompete's
contract set, decide (1) how likely the company is to want Recompete,
(2) which contracts they could pursue, (3) why they're a good prospect, and
(4) which contracts to mention in outreach.

No AI/API calls — matching is keyword/heuristic and fully testable offline.
"""

import csv
import io
import re

from apply_window import apply_stage

# ---------------------------------------------------------------------------
# Service categories
# ---------------------------------------------------------------------------

# Canonical service-category keys used across inference, scoring and the UI.
SERVICE_CATEGORIES = [
    "janitorial_facilities",
    "it",
    "cybersecurity",
    "logistics",
    "professional_services",
    "training",
    "health",
    "engineering_pm",
    "furniture_facilities",
    "partner",
    "unknown",
]

# Human-readable labels for display.
SERVICE_CATEGORY_LABELS = {
    "janitorial_facilities": "Janitorial / Facilities",
    "it": "Federal IT",
    "cybersecurity": "Cybersecurity",
    "logistics": "Logistics",
    "professional_services": "Professional Services",
    "training": "Training",
    "health": "Federal Health",
    "engineering_pm": "Engineering / PM",
    "furniture_facilities": "Furniture / Facilities",
    "partner": "Partner / Channel",
    "unknown": "Unknown",
}

# Inference rules: ordered (most specific first). The first category whose
# keywords appear in the company text/notes wins. Substrings are lowercased.
_INFERENCE_RULES = [
    ("cybersecurity", [
        "cyber", "infosec", "information security", "security operations",
        "soc ", "incident response", "penetration test", "zero trust", "siem",
    ]),
    ("health", [
        "health", "medical", "clinical", "healthcare", "nursing", "pharmacy",
        "behavioral health", "telehealth", "patient",
    ]),
    ("training", [
        "training", "e-learning", "elearning", "instructional", "curriculum",
        "courseware", "learning management",
    ]),
    ("furniture_facilities", [
        "furniture", "furnishing", "modular furniture", "office furniture",
    ]),
    ("janitorial_facilities", [
        "janitorial", "custodial", "cleaning", "housekeeping", "sanitation",
        "facility", "facilities", "hvac", "building maintenance", "grounds",
        "landscaping", "o&m", "operations and maintenance",
    ]),
    ("logistics", [
        "logistics", "supply chain", "transportation", "freight",
        "warehousing", "distribution", "fleet",
    ]),
    ("engineering_pm", [
        "program management", "project management", "systems engineering",
        "engineering", "pmo", "construction management", "a&e",
    ]),
    ("it", [
        "information technology", "software", "cloud", "network", "help desk",
        "helpdesk", "systems integrat", "data center", "managed service",
        "devops", "saas", "application develop", " it ", "it services",
    ]),
    ("professional_services", [
        "professional services", "consulting", "advisory", "staffing",
        "administrative support", "program support", "back office",
    ]),
    ("partner", [
        "partner", "channel", "reseller", "data partner", "alliance",
        "integration partner",
    ]),
]

# Contract-matching profile per service category: keywords to look for in a
# contract's searchable text, the canonical contract categories that count as a
# direct hit, and NAICS code prefixes that indicate the same industry.
_CONTRACT_MATCH = {
    "janitorial_facilities": {
        "keywords": ["janitorial", "custodial", "cleaning", "housekeeping",
                     "grounds", "landscaping", "facility", "facilities",
                     "hvac", "maintenance", "o&m"],
        "categories": ["Cleaning", "Facilities", "Grounds"],
        "naics": ["561720", "561210", "561730", "5617"],
    },
    "it": {
        "keywords": ["information technology", "software", "cloud", "network",
                     "help desk", "helpdesk", "systems integration",
                     "data center", "it support", "managed service"],
        "categories": ["IT"],
        "naics": ["5415", "5182", "5112", "5416"],
    },
    "cybersecurity": {
        "keywords": ["cyber", "information security", "security operations",
                     "soc", "incident response"],
        "categories": ["Cybersecurity"],
        "naics": ["541512", "541519", "5415"],
    },
    "logistics": {
        "keywords": ["logistics", "supply chain", "transportation",
                     "warehousing", "distribution", "freight"],
        "categories": ["Logistics"],
        "naics": ["4841", "4842", "4931", "488"],
    },
    "professional_services": {
        "keywords": ["professional services", "consulting", "advisory",
                     "administrative support", "program support",
                     "management support"],
        "categories": ["Administrative"],
        "naics": ["5416", "5611", "5414"],
    },
    "training": {
        "keywords": ["training", "instruction", "curriculum", "e-learning",
                     "courseware"],
        "categories": [],
        "naics": ["6114", "611"],
    },
    "health": {
        "keywords": ["health", "medical", "clinical", "nursing", "healthcare",
                     "pharmacy"],
        "categories": [],
        "naics": ["6211", "621", "622", "6214"],
    },
    "engineering_pm": {
        "keywords": ["engineering", "program management", "project management",
                     "systems engineering", "construction management",
                     "architect"],
        "categories": ["Construction"],
        "naics": ["5413", "2371", "2382", "5416"],
    },
    "furniture_facilities": {
        "keywords": ["furniture", "furnishing"],
        "categories": ["Facilities"],
        "naics": ["337", "4421"],
    },
    "partner": {"keywords": [], "categories": [], "naics": []},
    "unknown": {"keywords": [], "categories": [], "naics": []},
}

# Federal contracting jargon that signals a company already operates in the
# government market (strong "is a federal contractor" signal).
_FEDERAL_SIGNAL_TERMS = [
    "federal", "government", "govcon", "gov ", "idiq", "gwac", "set-aside",
    "set aside", "8(a)", "8a", "sam.gov", "gsa schedule", "gsa ", "past performance",
    "prime contractor", "subcontractor", "task order", "contract vehicle",
    "public sector", "dod", "doj", "dhs", "hhs", "va ", "naval", "army", "navy",
    "air force", "agency",
]

# Phrases that suggest the company sells to government end-customers.
_SELLS_TO_GOV_TERMS = [
    "government", "federal", "public sector", "agency", "agencies",
    "gsa", "dod", "military", "state and local", "civilian agency",
]

# Phrases that suggest a larger company (relaxes the big-contract penalty).
_LARGE_COMPANY_TERMS = [
    "enterprise", "nationwide", "prime", "fortune", "billion",
    "large business", "global", "multinational",
]

# Partner / channel signals (these prospects buy Recompete as a data/channel
# play rather than to bid on contracts directly).
_PARTNER_TERMS = ["partner", "channel", "reseller", "data partner", "alliance"]

# Known agency tokens used for agency/domain matching from notes.
_AGENCY_TOKENS = [
    "army", "navy", "air force", "marine", "defense", "dod", "va",
    "veterans affairs", "gsa", "dhs", "homeland", "hhs", "health and human",
    "doj", "justice", "doe", "energy", "usda", "agriculture", "treasury",
    "state department", "nasa", "interior", "epa", "labor", "transportation",
    "education", "commerce", "sba",
]

# DC / Maryland / Virginia — the federal-heavy contracting region.
_DMV_STATES = {"DC", "MD", "VA"}

_STATE_ABBRS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def _norm(value) -> str:
    return (value or "").strip()


def _lower(*parts) -> str:
    return " ".join(_norm(p) for p in parts).lower()


# Common legal-entity suffix tokens stripped when normalizing a company name
# for dedupe. Kept conservative so genuinely distinct names don't collapse.
_COMPANY_SUFFIX_TOKENS = {
    "inc", "incorporated", "llc", "corp", "corporation", "co", "company",
    "ltd", "limited", "lp", "llp", "plc", "pllc", "pc",
}


def normalize_company_name(name) -> str:
    """Return a normalized key for dedupe-matching company names.

    Case-insensitive, trims whitespace, drops punctuation, collapses internal
    spaces, strips a leading "the", and removes trailing legal-entity suffixes
    (Inc, Inc., LLC, L.L.C., Corp, Corporation, Co, Company, ...). So
    "Acme Inc", "ACME, Inc.", "Acme L.L.C." and "The Acme Co" all normalize to
    "acme". Falls back to the punctuation-stripped form if stripping suffixes
    would leave nothing.
    """
    s = (name or "").lower()
    # Drop dots/apostrophes with no gap so "L.L.C." -> "llc", "O'Brien" -> "obrien".
    s = re.sub(r"[.'’]", "", s)
    # Any other punctuation becomes a separator.
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = s.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    stripped = list(tokens)
    while stripped and stripped[-1] in _COMPANY_SUFFIX_TOKENS:
        stripped.pop()
    chosen = stripped or tokens
    return " ".join(chosen)


def infer_company_state(company_text="", notes="") -> str | None:
    """Extract a 2-letter US state code from company/location text.

    Handles "Company — City, ST", "Company - City, ST", "City, ST 20001", and
    a bare ", ST" anywhere in the company or notes text. Returns None when no
    valid state token is found.
    """
    for blob in (company_text, notes):
        blob = _norm(blob)
        if not blob:
            continue
        # ", ST" optionally followed by a ZIP — prefer the last such match.
        matches = re.findall(r",\s*([A-Za-z]{2})\b", blob)
        for cand in reversed(matches):
            st = cand.upper()
            if st in _STATE_ABBRS:
                return st
        # "... ST 20001" (state immediately before a ZIP)
        zip_match = re.search(r"\b([A-Za-z]{2})\s+\d{5}(?:-\d{4})?\b", blob)
        if zip_match:
            st = zip_match.group(1).upper()
            if st in _STATE_ABBRS:
                return st
    return None


def infer_service_category(notes="", company_name="") -> str:
    """Infer a broad service category from notes + company name.

    Returns one of SERVICE_CATEGORIES. "partner" is only returned when a
    partner signal is present AND no concrete service category matched.
    """
    text = _lower(notes, company_name)
    if not text.strip():
        return "unknown"
    for category, keywords in _INFERENCE_RULES:
        if category == "partner":
            continue  # handled below as a fallback
        for kw in keywords:
            if kw in text:
                return category
    if any(term in text for term in _PARTNER_TERMS):
        return "partner"
    return "unknown"


def detect_federal_signal(notes="", company_name="") -> bool:
    """True when the company text shows federal-contracting experience."""
    text = _lower(notes, company_name)
    return any(term in text for term in _FEDERAL_SIGNAL_TERMS)


def sells_to_government(notes="", company_name="") -> bool:
    text = _lower(notes, company_name)
    return any(term in text for term in _SELLS_TO_GOV_TERMS)


def is_partner_prospect(company) -> bool:
    """True when contact_type/notes mark this as a partner/channel prospect."""
    blob = _lower(
        company.get("contact_type"),
        company.get("notes") or company.get("service_notes"),
        company.get("source_notes"),
    )
    return any(term in blob for term in _PARTNER_TERMS)


def _is_large_company(company) -> bool:
    blob = _lower(company.get("notes") or company.get("service_notes"),
                  company.get("source_notes"), company.get("company_name"))
    return any(term in blob for term in _LARGE_COMPANY_TERMS)


def _company_notes(company) -> str:
    return _norm(company.get("notes") or company.get("service_notes")
                 or company.get("source_notes"))


def _has_contact(company) -> bool:
    return bool(_norm(company.get("email")) or _norm(company.get("phone")))


# ---------------------------------------------------------------------------
# Likely-customer scoring
# ---------------------------------------------------------------------------

def score_likely_customer(company) -> int:
    """Return a 0–100 score for how likely a company is to buy Recompete.

    Weights (additive, capped at 100):
      +25  federal-contracting experience signal in notes
      +20  a specific service category is known (not "unknown"/"partner")
      +20  company appears to sell to government
      +10  located in the DMV / federal-heavy region (DC/MD/VA)
      +10  contact info (email or phone) on file
      +15  partner / channel prospect (separate channel-opportunity bump)
    """
    score, _ = _likely_customer_breakdown(company)
    return score


def _likely_customer_breakdown(company):
    notes = _company_notes(company)
    name = company.get("company_name") or ""
    category = company.get("inferred_service_category") or infer_service_category(notes, name)
    state = company.get("state") or infer_company_state(
        company.get("company_location") or company.get("company_name") or "", notes)

    score = 0
    reasons = []
    if detect_federal_signal(notes, name):
        score += 25
        reasons.append("Shows federal-contracting experience")
    if category not in ("unknown", "partner"):
        score += 20
        reasons.append(f"Clear service focus: {SERVICE_CATEGORY_LABELS.get(category, category)}")
    if sells_to_government(notes, name):
        score += 20
        reasons.append("Sells to government customers")
    if state in _DMV_STATES:
        score += 10
        reasons.append(f"Based in the federal-heavy DMV region ({state})")
    if _has_contact(company):
        score += 10
        reasons.append("Reachable (email/phone on file)")
    if is_partner_prospect(company):
        score += 15
        reasons.append("Partner / channel opportunity")
    return min(score, 100), reasons


def likely_customer_reasons(company) -> list[str]:
    """Human-readable bullets explaining the likely-customer score."""
    _, reasons = _likely_customer_breakdown(company)
    return reasons


# ---------------------------------------------------------------------------
# Contract-fit scoring
# ---------------------------------------------------------------------------

def _contract_text(contract) -> str:
    return " ".join(filter(None, [
        contract.get("description") or "",
        contract.get("category") or "",
        contract.get("psc_description") or "",
        contract.get("vendor") or "",
        contract.get("agency") or "",
    ])).lower()


def _matched_keywords(contract, category) -> list[str]:
    profile = _CONTRACT_MATCH.get(category) or {}
    text = _contract_text(contract)
    return [kw for kw in profile.get("keywords", []) if kw in text]


def _naics_matches(contract, category) -> bool:
    profile = _CONTRACT_MATCH.get(category) or {}
    naics = _norm(contract.get("naics_code"))
    if not naics:
        return False
    return any(naics.startswith(p) for p in profile.get("naics", []))


def _category_matches(contract, category) -> bool:
    profile = _CONTRACT_MATCH.get(category) or {}
    return (contract.get("category") or "") in profile.get("categories", [])


def _coerce_days(contract):
    try:
        return int(contract.get("days_remaining"))
    except (TypeError, ValueError):
        return None


def score_contract_fit(company, contract) -> dict:
    """Return per-dimension scores + a 0–100 match_score for one contract.

    Dimensions (max): service 40, state 25, timing 20, value 10, federal 5.
    Expired/too-late contracts are penalised so they sort below live ones.
    """
    category = company.get("inferred_service_category") or "unknown"
    company_state = company.get("state")

    # --- service (0–40) ---
    service_score = 0
    if _category_matches(contract, category):
        service_score += 20
    matched_kw = _matched_keywords(contract, category)
    if matched_kw:
        service_score += min(len(matched_kw) * 8, 16)
    if _naics_matches(contract, category):
        service_score += 8
    service_score = min(service_score, 40)

    # --- state (0–25) ---
    pop_state = _norm(contract.get("place_of_performance_state")).upper()[:2] or None
    state_score = 0
    if company_state and pop_state and company_state == pop_state:
        state_score = 25
    elif company_state in _DMV_STATES and pop_state in _DMV_STATES:
        state_score = 12
    elif pop_state in _DMV_STATES or company_state in _DMV_STATES:
        state_score = 6

    # --- timing (0–20) + penalty ---
    days = _coerce_days(contract)
    timing_score = 0
    penalty = 0
    if days is not None and days <= 0:
        penalty = 30  # already expired
    else:
        stage = apply_stage(days)[0]
        if stage in ("prepare", "submit_now"):
            timing_score = 20
        elif stage == "research":
            timing_score = 12
        elif stage == "watch":
            timing_score = 5
        elif stage == "too_late":
            penalty = 15
        else:  # unknown timing
            timing_score = 5

    # --- value (0–10) ---
    value = contract.get("value")
    large = _is_large_company(company)
    if value is None:
        value_score = 5
    elif value <= 10_000_000:
        value_score = 10
    elif value <= 50_000_000:
        value_score = 7
    else:
        value_score = 10 if large else 3  # light penalty: huge contract, small co

    # --- federal / agency fit (0–5) ---
    notes = _company_notes(company)
    contract_agency = (contract.get("agency") or "").lower()
    federal_fit_score = 0
    note_agencies = [a for a in _AGENCY_TOKENS if a in notes.lower()]
    if contract_agency and any(a in contract_agency for a in note_agencies):
        federal_fit_score = 5
    elif detect_federal_signal(notes, company.get("company_name") or ""):
        federal_fit_score = 2

    subtotal = (service_score + state_score + timing_score
                + value_score + federal_fit_score)
    match_score = max(0, min(100, subtotal - penalty))

    return {
        "service_score": service_score,
        "state_score": state_score,
        "timing_score": timing_score,
        "value_score": value_score,
        "federal_fit_score": federal_fit_score,
        "penalty": penalty,
        "match_score": match_score,
        "matched_keywords": matched_kw,
    }


def generate_match_reason(company, contract, scores) -> str:
    """Build a short human-readable reason from the fit subscores."""
    bits = []
    category = company.get("inferred_service_category") or "unknown"
    label = SERVICE_CATEGORY_LABELS.get(category, category)

    if scores["service_score"] >= 20:
        bits.append(f"Strong {label} fit")
    elif scores["service_score"] > 0:
        bits.append(f"Partial {label} fit")

    pop_state = _norm(contract.get("place_of_performance_state")).upper()[:2]
    if scores["state_score"] == 25 and pop_state:
        bits.append(f"same state ({pop_state})")
    elif scores["state_score"] > 0:
        bits.append("federal-region overlap")

    days = _coerce_days(contract)
    if scores["penalty"] and days is not None and days <= 0:
        bits.append("but already expired")
    elif scores["penalty"]:
        bits.append("but likely too late to bid")
    else:
        stage_label = apply_stage(days)[1]
        bits.append(f"timing: {stage_label.lower()}")

    if scores["federal_fit_score"] == 5 and contract.get("agency"):
        bits.append(f"agency match ({contract.get('agency')})")

    if not bits:
        return "Low-confidence match."
    return "; ".join(bits).capitalize() + "."


def find_matching_contracts(company, contracts, limit=5) -> list[dict]:
    """Score `contracts` for `company` and return the top `limit` matches.

    Each result: {contract, scores, match_score, match_reason}. Contracts that
    score 0 (no service/state/timing fit at all) are excluded.
    """
    scored = []
    for contract in contracts:
        scores = score_contract_fit(company, contract)
        if scores["match_score"] <= 0:
            continue
        scored.append({
            "contract": dict(contract),
            "scores": scores,
            "match_score": scores["match_score"],
            "match_reason": generate_match_reason(company, contract, scores),
        })
    scored.sort(
        key=lambda m: (m["match_score"], m["contract"].get("recompete_score") or 0),
        reverse=True,
    )
    return scored[:limit]


def generate_outreach_angle(company, contract_matches) -> str:
    """Suggest a one-line outreach angle anchored on the top matched contract."""
    name = _norm(company.get("company_name")) or "this company"
    category = company.get("inferred_service_category") or "unknown"
    label = SERVICE_CATEGORY_LABELS.get(category, category)

    if not contract_matches:
        return (f"No live contract matches yet — lead with Recompete's coverage "
                f"of {label} recompetes and ask what agencies {name} targets.")

    top = contract_matches[0]
    contract = top["contract"]
    agency = _norm(contract.get("agency")) or "the agency"
    pop_state = _norm(contract.get("place_of_performance_state")).upper()[:2]
    award_id = _norm(contract.get("award_id")) or _norm(contract.get("internal_id"))
    end_date = _norm(contract.get("end_date"))
    where = f" in {pop_state}" if pop_state else ""
    when = f" expiring {end_date}" if end_date else ""
    ref = f" ({award_id})" if award_id else ""

    return (f"Lead with the {agency} {label} recompete{ref}{when}{where} — it "
            f"fits {name}'s focus. Use it to show Recompete surfaces their next "
            f"bid before the solicitation drops.")


# ---------------------------------------------------------------------------
# CSV import parsing
# ---------------------------------------------------------------------------

# Accepted header aliases (lowercased) → normalized field name.
_HEADER_ALIASES = {
    "rank": "rank",
    "company": "company",
    "name / title": "name_title",
    "name/title": "name_title",
    "name": "name_title",
    "title": "name_title",
    "phone": "phone",
    "email": "email",
    "contact type": "contact_type",
    "contacttype": "contact_type",
    "notes": "notes",
}


def parse_company_field(value) -> tuple[str, str, str | None]:
    """Split a "Company — City, ST" cell into (name, full_location, state).

    The full original text is preserved as `location`. The company name is the
    portion before the first em/en-dash or " - " separator; if no separator is
    present the whole string is the name.
    """
    raw = _norm(value)
    if not raw:
        return "", "", None
    # Split company name from location on em-dash, en-dash, or spaced hyphen.
    parts = re.split(r"\s*[—–]\s*|\s+-\s+", raw, maxsplit=1)
    name = _norm(parts[0])
    state = infer_company_state(raw)
    return name, raw, state


def split_name_title(value) -> tuple[str, str]:
    """Split a "Name / Title" cell into (contact_name, contact_title)."""
    raw = _norm(value)
    if not raw:
        return "", ""
    if "/" in raw:
        left, right = raw.split("/", 1)
        return _norm(left), _norm(right)
    if "," in raw:
        left, right = raw.split(",", 1)
        return _norm(left), _norm(right)
    return raw, ""


def normalize_lead_row(raw: dict) -> dict:
    """Turn a raw CSV row (header→value) into a normalized lead_companies dict.

    Recognised headers (case-insensitive): Rank, Company, Name / Title, Phone,
    Email, Contact Type, Notes. Unknown headers are ignored. Inference fills
    state, service category and likely-customer score.
    """
    norm: dict = {}
    for key, val in raw.items():
        if key is None:
            continue
        field = _HEADER_ALIASES.get(str(key).strip().lower())
        if field:
            norm[field] = _norm(val)

    company_name, location, state = parse_company_field(norm.get("company", ""))
    contact_name, contact_title = split_name_title(norm.get("name_title", ""))
    notes = norm.get("notes", "")

    lead = {
        "company_name": company_name,
        "contact_name": contact_name,
        "contact_title": contact_title,
        "phone": norm.get("phone", ""),
        "email": norm.get("email", ""),
        "company_location": location,
        "state": state,
        "service_notes": notes,
        "contact_type": norm.get("contact_type", ""),
        "source_notes": notes,
    }
    lead["inferred_service_category"] = infer_service_category(notes, company_name)
    lead["federal_experience_signal"] = (
        1 if detect_federal_signal(notes, company_name) else 0
    )
    lead["likely_customer_score"] = score_likely_customer(lead)
    return lead


def parse_leads_csv(text: str) -> list[dict]:
    """Parse CSV text into a list of normalized lead dicts.

    Rows with no company name are skipped. Safe on empty/whitespace input.
    """
    text = (text or "").strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    leads = []
    for raw in reader:
        lead = normalize_lead_row(raw)
        if lead["company_name"]:
            leads.append(lead)
    return leads
