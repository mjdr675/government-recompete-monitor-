"""Generic, configurable USASpending contract ingest.

This is the primary production ingest script. NAICS codes are read from the
``INGEST_NAICS_CODES`` environment variable (comma-separated) so production
scope can be changed without code changes. When the variable is unset, a broad
default covering major federal service categories is used.

All codes are passed to the USASpending API in a single request — pagination
is per page, not per NAICS code — so adding more codes does not multiply API
calls.

``janitorial_recompete_report.py`` is preserved as a standalone script for
backward compatibility and ad-hoc use, but it is NOT called by the scheduled
Celery task. Only this module is called by the scheduler.
"""

import csv
import logging
import os
import time
from datetime import date, datetime, timedelta

import requests

from change_detector import detect_changes
from db import save_snapshot
from sam_lookup import lookup_solicitation

logger = logging.getLogger("ingest")

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

# Default NAICS codes when INGEST_NAICS_CODES env var is not set.
# All are passed in one API call — adding codes does not multiply requests.
# Override in Railway: INGEST_NAICS_CODES=561720,561210,541512,541611
DEFAULT_NAICS_CODES = [
    "561720",   # Janitorial Services
    "561210",   # Facilities Support Services
    "541512",   # Computer Systems Design Services
    "541611",   # Admin Management Consulting
    "541330",   # Engineering Services
    "238290",   # Other Building Equipment Contractors
]


def _today() -> date:
    """Return today's date.

    Called on every ingest run so long-lived Celery workers never reuse
    a stale import-time date.
    """
    return date.today()


def _naics_codes() -> list:
    """Return the NAICS code list for this ingest run.

    Read from INGEST_NAICS_CODES env var (comma-separated) or fall back to
    DEFAULT_NAICS_CODES. Never returns an empty list — guards against an
    accidental blank env var.
    """
    raw = os.environ.get("INGEST_NAICS_CODES", "").strip()
    if raw:
        codes = [c.strip() for c in raw.split(",") if c.strip()]
        if codes:
            return codes
    return list(DEFAULT_NAICS_CODES)


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def money(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def fetch_contracts(naics_codes: list) -> list:
    """Fetch all active contracts from USASpending for the given NAICS codes.

    All codes are passed in a single filter so the pagination is over the
    combined result set, not per-code.
    """
    out = []
    for page in range(1, 101):
        payload = {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "naics_codes": naics_codes,
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Start Date",
                "End Date",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Description",
                "generated_internal_id",
            ],
            "page": page,
            "limit": 100,
            "sort": "Start Date",
            "order": "desc",
        }
        for attempt in range(1, 4):
            r = requests.post(API_URL, json=payload, timeout=30)
            logger.info("fetch page=%d attempt=%d status=%d", page, attempt, r.status_code)
            if r.status_code < 500:
                r.raise_for_status()
                break
            logger.warning("fetch page=%d attempt=%d got %d — retrying", page, attempt, r.status_code)
            time.sleep(2 * attempt)
        else:
            r.raise_for_status()

        data = r.json()
        out.extend(data.get("results", []))
        if not data.get("page_metadata", {}).get("hasNext"):
            break
    return out


def _score(amount, days_left):
    value_score = 40 if amount >= 1_000_000 else 30 if amount >= 250_000 else 20 if amount >= 50_000 else 10
    time_score = 40 if days_left <= 180 else 30 if days_left <= 365 else 20
    return value_score + time_score


def _competition_score(comp):
    comp = (comp or "").upper()
    if comp == "FULL AND OPEN COMPETITION":
        return 40
    if comp == "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES":
        return 35
    if comp == "COMPETED UNDER SAP":
        return 30
    return 0


def _value_score(value):
    value = money(value)
    if value >= 10_000_000:
        return 35
    if value >= 5_000_000:
        return 25
    if value >= 2_000_000:
        return 15
    if value >= 1_000_000:
        return 10
    return 0


def _days_score(days):
    """Timing score rewards realistic pursuit windows, not imminent expiry.

    Contracts expiring in < 30 days are essentially un-winnable for a new
    challenger (solicitation already closed). The best pursuit window is
    365-540 days out — enough runway to engage the agency, build a team,
    and prepare a competitive proposal.
    """
    days = int(days) if days is not None else 9999
    if days <= 0:
        return 0   # expired or too late
    if days < 30:
        return 0   # too late for new challengers
    if days < 90:
        return 5   # urgent / late-stage
    if days < 180:
        return 10  # active pursuit window
    if days < 270:
        return 15  # prepare proposal and team
    if days < 365:
        return 20  # shape opportunity
    if days <= 540:
        return 25  # best pursuit window — maximum points
    return 5       # too early; watch only


def _agency_bonus(row):
    a = (row.get("agency") or "").upper()
    if "DEFENSE" in a:
        return 5
    if "VETERANS AFFAIRS" in a:
        return 4
    if "HOMELAND SECURITY" in a:
        return 3
    return 0


def _solicitation_bonus(row):
    return 5 if row.get("solicitation_id") else 0


def _office_bonus(row):
    o = (row.get("awarding_office") or "").upper()
    key_offices = ["697DCK", "NETWORK CONTRACT OFFICE", "DEFENSE HEALTH AGENCY", "NAVFAC", "W40M"]
    return 5 if any(x in o for x in key_offices) else 0


def recompete_score(row):
    return (
        _competition_score(row.get("competition_type"))
        + _value_score(row.get("value"))
        + _days_score(row.get("days_remaining"))
        + _agency_bonus(row)
        + _solicitation_bonus(row)
        + _office_bonus(row)
    )


def _priority(score, days=None):
    """Assign pursuit priority.

    CRITICAL requires meaningful runway: a contract expiring in < 30 days
    cannot be CRITICAL because there is no realistic time to prepare a bid.
    High score with very short runway is HIGH at best.
    """
    if days is not None:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = None
    if days is not None and days < 30:
        if score >= 75:
            return "HIGH"
        if score >= 60:
            return "MEDIUM"
        return "LOW"
    if score >= 90:
        return "CRITICAL"
    if score >= 75:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    return "LOW"


def enrichment_award_id(row):
    return row.get("internal_id") or row.get("generated_internal_id")


def should_enrich(row):
    # Enrich contracts within the best pursuit window (up to 540 days out).
    days = row.get("days_remaining")
    in_window = days is None or (0 < days <= 540)
    return (
        row["value"] >= 1_000_000
        and in_window
        and bool(enrichment_award_id(row))
    )


def fetch_award_detail(internal_id):
    try:
        url = AWARD_DETAIL_URL.format(award_id=internal_id)
        r = requests.get(url, timeout=30)
        logger.info("award detail award_id=%s status=%d", internal_id, r.status_code)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error("award detail failed award_id=%s: %s", internal_id, e)
        return {}


def _enrichment_from_detail(data):
    latest = data.get("latest_transaction_contract_data") or {}
    recipient = data.get("recipient") or {}
    recipient_loc = recipient.get("location") or {}
    pop = data.get("place_of_performance") or {}
    awarding = data.get("awarding_agency") or {}
    funding = data.get("funding_agency") or {}
    parent = data.get("parent_award") or {}
    psc = data.get("psc_hierarchy") or {}
    psc_base = psc.get("base_code") or {}
    return {
        "solicitation_id": latest.get("solicitation_identifier") or "",
        "awarding_office": awarding.get("office_agency_name") or "",
        "funding_office": funding.get("office_agency_name") or "",
        "recipient_uei": recipient.get("recipient_uei") or "",
        "cage_code": recipient.get("cage_code") or latest.get("cage_code") or "",
        "recipient_city": recipient_loc.get("city_name") or "",
        "recipient_state": recipient_loc.get("state_code") or recipient_loc.get("state_name") or "",
        "recipient_country": recipient_loc.get("country_name") or recipient_loc.get("location_country_code") or "",
        "recipient_address": recipient_loc.get("address_line1") or "",
        "recipient_zip": recipient_loc.get("zip5") or recipient_loc.get("zip4") or recipient_loc.get("foreign_postal_code") or "",
        "performance_city": pop.get("city_name") or "",
        "performance_state": pop.get("state_code") or pop.get("state_name") or "",
        "performance_country": pop.get("country_name") or pop.get("location_country_code") or "",
        "performance_zip": pop.get("zip5") or pop.get("zip4") or pop.get("foreign_postal_code") or "",
        "competition_type": latest.get("extent_competed_description") or "",
        "solicitation_procedure": latest.get("solicitation_procedures_description") or "",
        "pricing_type": latest.get("type_of_contract_pricing_description") or "",
        "psc_code": latest.get("product_or_service_code") or psc_base.get("code") or "",
        "psc_description": latest.get("product_or_service_description") or psc_base.get("description") or "",
        "parent_contract": parent.get("piid") or "",
        "parent_contract_type": parent.get("type_of_idc_description") or parent.get("idv_type_description") or "",
    }


def main(naics_codes: list | None = None) -> int:
    """Run the full contract ingest pipeline.

    Args:
        naics_codes: NAICS codes to fetch. When None, reads ``INGEST_NAICS_CODES``
                     env var or falls back to DEFAULT_NAICS_CODES.

    Returns:
        Number of contracts persisted.

    Raises:
        RuntimeError: When 0 contracts match the active date filter — this is
                      treated as a failure so the caller (run_ingest Celery task)
                      records status='failure' in ingest_log.
    """
    today = _today()
    cutoff = today + timedelta(days=540)

    codes = naics_codes if naics_codes is not None else _naics_codes()

    if not os.environ.get("SAM_API_KEY"):
        logger.warning(
            "SAM_API_KEY is not set — SAM.gov solicitation enrichment will be skipped"
        )

    logger.info(
        "ingest starting: today=%s cutoff=%s naics_codes=%s",
        today, cutoff, codes,
    )

    rows = []
    for c in fetch_contracts(codes):
        end = parse_date(c.get("End Date"))
        start = parse_date(c.get("Start Date"))
        if not end:
            continue
        if today <= end <= cutoff:
            amount = money(c.get("Award Amount"))
            days_left = (end - today).days
            rows.append({
                "score": _score(amount, days_left),
                "days_remaining": days_left,
                "contract": c.get("Award ID"),
                "vendor": c.get("Recipient Name"),
                "value": amount,
                "start_date": start.isoformat() if start else "",
                "end_date": end.isoformat(),
                "agency": c.get("Awarding Agency"),
                "sub_agency": c.get("Awarding Sub Agency"),
                "description": c.get("Description", ""),
                "generated_internal_id": c.get("generated_internal_id"),
                "internal_id": c.get("internal_id"),
                "solicitation_id": "",
                "awarding_office": "",
                "funding_office": "",
                "recipient_uei": "",
                "cage_code": "",
                "recipient_city": "",
                "recipient_state": "",
                "recipient_country": "",
                "recipient_address": "",
                "recipient_zip": "",
                "performance_city": "",
                "performance_state": "",
                "performance_country": "",
                "performance_zip": "",
                "competition_type": "",
                "solicitation_procedure": "",
                "pricing_type": "",
                "psc_code": "",
                "psc_description": "",
                "parent_contract": "",
                "parent_contract_type": "",
            })

    rows.sort(key=lambda x: (-x["score"], x["days_remaining"]))

    # Tier-A enrichment: fetch USASpending award detail for high-value / soon-expiring contracts.
    enrich_count = 0
    for row in rows:
        if should_enrich(row):
            detail = fetch_award_detail(enrichment_award_id(row))
            row.update(_enrichment_from_detail(detail))
            enrich_count += 1
            time.sleep(0.1)

    # Compute final recompete scores after enrichment (solicitation_id may have been populated).
    for row in rows:
        rs = recompete_score(row)
        row["recompete_score"] = rs
        row["priority"] = _priority(rs, row.get("days_remaining"))

    rows.sort(key=lambda r: (-int(r["recompete_score"]), -float(r["value"]), int(r["days_remaining"])))

    # SAM.gov solicitation enrichment (requires SAM_API_KEY).
    sam_cache: dict = {}
    sam_count = 0
    for row in rows:
        sid = row.get("solicitation_id", "")
        sam = None
        if sid:
            if sid not in sam_cache:
                sam_cache[sid] = lookup_solicitation(sid)
            sam = sam_cache[sid]
        if sam:
            row.update(sam)
            sam_count += 1
        for field in ["sam_title", "sam_type", "sam_due_date", "sam_set_aside", "sam_naics", "sam_url"]:
            row.setdefault(field, "")

    # Write CSV for manual inspection (filename reflects actual scope).
    csv_fields = [
        "recompete_score", "priority", "score", "days_remaining", "contract", "vendor", "value",
        "start_date", "end_date", "agency", "sub_agency", "description",
        "generated_internal_id", "internal_id",
        "solicitation_id", "awarding_office", "funding_office",
        "recipient_uei", "cage_code", "recipient_city", "recipient_state",
        "recipient_country", "recipient_address", "recipient_zip",
        "performance_city", "performance_state", "performance_country",
        "performance_zip", "competition_type", "solicitation_procedure",
        "pricing_type", "psc_code", "psc_description",
        "parent_contract", "parent_contract_type",
        "sam_title", "sam_type", "sam_due_date", "sam_set_aside", "sam_naics", "sam_url",
    ]
    with open("recompete_report.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Persist to DB — single upsert after ALL enrichment passes are complete.
    run_date = str(today)
    save_snapshot(run_date, rows)
    detect_changes(run_date)

    if not rows:
        msg = (
            f"ingest complete but 0 rows matched filter today={today} "
            f"naics={codes} — possible API issue or date filter problem"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("ingest complete: %d contracts persisted (snapshot %s)", len(rows), run_date)
    logger.info("naics codes used: %s", codes)
    logger.info("tier-a enrichment: %d contracts enriched", enrich_count)
    logger.info("sam.gov enrichment: %d solicitations matched", sam_count)
    return len(rows)


if __name__ == "__main__":
    import sys
    codes = sys.argv[1:] if len(sys.argv) > 1 else None
    main(naics_codes=codes)
