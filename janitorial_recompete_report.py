import csv
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

import requests
from sqlalchemy import text

from change_detector import detect_changes
from db import get_engine, save_snapshot
from sam_lookup import lookup_solicitation
from update_detector import detect_field_changes

logger = logging.getLogger("ingest")

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

# TODAY is kept at module level so test fixtures can construct relative dates
# (e.g. jrr.TODAY + timedelta(days=90)). Do NOT use TODAY inside main() — call
# _today() instead so nightly Celery runs always get a fresh value rather than
# the date the worker process first imported this module.
TODAY = date.today()
CUTOFF = TODAY + timedelta(days=540)

MAX_CONTRACT_VALUE = 10_000_000  # $10M ceiling — right-sized for 50-100 employee companies

# USASpending award search can't filter by POP end date. Approximate "active/expiring
# soon" by pulling awards with a recent action_date, then filter to the real expiry
# window (today..cutoff) client-side as before.
ACTION_DATE_LOOKBACK_DAYS = 365 * 5


def _today() -> date:
    """Return today's date. Separate function so tests can monkeypatch it and
    so Celery workers don't silently reuse the import-time date."""
    return date.today()

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

def fetch_contracts(today, cutoff):
    out = []
    session = requests.Session()

    for page in range(1, 101):
        payload = {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [
                    {
                        "start_date": (today - timedelta(days=ACTION_DATE_LOOKBACK_DAYS)).isoformat(),
                        "end_date": today.isoformat(),
                        "date_type": "action_date",
                    }
                ],
                "award_amounts": [{"upper_bound": MAX_CONTRACT_VALUE}],
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
                "NAICS",
                # Valid place-of-performance fields for the search endpoint.
                # These return a state code and zip5 (not full city names).
                "Place of Performance State Code",
                "Place of Performance Zip5",
            ],
            "page": page,
            "limit": 100,
            "sort": "Award Amount",
            "order": "desc",
        }

        action_start = (today - timedelta(days=ACTION_DATE_LOOKBACK_DAYS)).isoformat()
        action_end = today.isoformat()
        success = False
        for attempt in range(1, 6):
            logger.info(
                "fetch page=%d attempt=%d date_range=%s..%s",
                page, attempt, action_start, action_end,
            )
            try:
                r = session.post(API_URL, json=payload, timeout=(10, 30))
                logger.info("fetch page=%d attempt=%d status=%d", page, attempt, r.status_code)
                if r.status_code < 500:
                    r.raise_for_status()
                    success = True
                    break
                logger.warning("fetch page=%d attempt=%d got %d — retrying", page, attempt, r.status_code)
                time.sleep(3 * attempt)
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "fetch page=%d attempt=%d request error (%s): %s — reconnecting",
                    page, attempt, type(e).__name__, e,
                )
                time.sleep(5 * attempt)
                session = requests.Session()

        if not success:
            logger.error("skipping page %d after 5 failed attempts", page)
            continue

        data = r.json()
        results = data.get("results", [])

        for c in results:
            end = parse_date(c.get("End Date"))
            if not end or not (today <= end <= cutoff):
                continue
            amount = money(c.get("Award Amount"))
            if amount > MAX_CONTRACT_VALUE:
                continue
            out.append(c)

        if not data.get("page_metadata", {}).get("hasNext"):
            break

        if len(out) >= 5000:
            break

        time.sleep(0.2)

    return out

def score(amount, days_left):
    value_score = 40 if amount >= 1_000_000 else 30 if amount >= 250_000 else 20 if amount >= 50_000 else 10
    time_score = 40 if days_left <= 180 else 30 if days_left <= 365 else 20
    return value_score + time_score

def competition_score(comp):
    comp = (comp or "").upper()
    return 40 if comp == "FULL AND OPEN COMPETITION" else 35 if comp == "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES" else 30 if comp == "COMPETED UNDER SAP" else 0

def value_score(value):
    value = money(value)
    return 35 if value >= 10_000_000 else 25 if value >= 5_000_000 else 15 if value >= 2_000_000 else 10 if value >= 1_000_000 else 0

def days_score(days):
    days = int(days or 9999)
    return 25 if days <= 30 else 20 if days <= 60 else 15 if days <= 90 else 10 if days <= 180 else 0

def agency_bonus(row):
    a = (row.get("agency") or "").upper()
    return 5 if "DEFENSE" in a else 4 if "VETERANS AFFAIRS" in a else 3 if "HOMELAND SECURITY" in a else 0

def solicitation_bonus(row):
    return 5 if row.get("solicitation_id") else 0

def office_bonus(row):
    o = (row.get("awarding_office") or "").upper()
    return 5 if any(x in o for x in ["697DCK","NETWORK CONTRACT OFFICE","DEFENSE HEALTH AGENCY","NAVFAC","W40M"]) else 0

def recompete_score(row):
    return (competition_score(row.get("competition_type")) + value_score(row.get("value")) +
            days_score(row.get("days_remaining")) + agency_bonus(row) +
            solicitation_bonus(row) + office_bonus(row))

def priority(score):
    return "CRITICAL" if score >= 90 else "HIGH" if score >= 75 else "MEDIUM" if score >= 60 else "LOW"

def enrichment_award_id(row):
    return row.get("internal_id") or row.get("generated_internal_id")

def should_enrich(row):
    return row["value"] >= 500_000 and row["days_remaining"] <= 180 and bool(enrichment_award_id(row))

AWARD_DETAIL_RETRIES = int(os.getenv("AWARD_DETAIL_RETRIES", "3"))


def fetch_award_detail(internal_id, retries=None):
    """Fetch a single award's detail, retrying transient failures.

    USASpending intermittently drops connections (RemoteDisconnected) or returns
    5xx under load; a single attempt loses that award's enrichment entirely
    (notably its solicitation_identifier, which SAM enrichment depends on).
    Retry connection errors, timeouts and 5xx with a short bounded backoff so a
    transient drop doesn't permanently blank the row. A genuine 4xx (e.g. 404)
    is not retried.
    """
    if retries is None:
        retries = AWARD_DETAIL_RETRIES
    url = AWARD_DETAIL_URL.format(award_id=internal_id)
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code >= 500:
                logger.warning(
                    "award detail award_id=%s attempt=%d status=%d — retrying",
                    internal_id, attempt, r.status_code,
                )
                if attempt < retries:
                    time.sleep(min(attempt, 3))
                    continue
                logger.error(
                    "award detail failed award_id=%s: status=%d after %d attempts",
                    internal_id, r.status_code, retries,
                )
                return {}
            r.raise_for_status()
            logger.info("award detail award_id=%s status=%d", internal_id, r.status_code)
            return r.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(
                "award detail award_id=%s attempt=%d connection error: %s — retrying",
                internal_id, attempt, e,
            )
            if attempt < retries:
                time.sleep(min(attempt, 3))
                continue
            logger.error(
                "award detail failed award_id=%s: %s after %d attempts",
                internal_id, e, retries,
            )
            return {}
        except Exception as e:
            logger.error("award detail failed award_id=%s: %s", internal_id, e)
            return {}
    return {}

def enrichment_from_detail(data):
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
        "recipient_city": recipient_loc.get("city_name") or "",
        "recipient_state": recipient_loc.get("state_code") or recipient_loc.get("state_name") or "",
        "recipient_country": recipient_loc.get("country_name") or recipient_loc.get("location_country_code") or "",
        "recipient_address": recipient_loc.get("address_line1") or "",
        "recipient_zip": recipient_loc.get("zip5") or recipient_loc.get("zip4") or recipient_loc.get("foreign_postal_code") or "",
        # Enrichment provides full city + state names (better than search-level state code)
        "performance_city": pop.get("city_name") or "",
        "performance_state": pop.get("state_code") or pop.get("state_name") or "",
        "performance_country": pop.get("country_name") or pop.get("location_country_code") or "",
        "performance_zip": pop.get("zip5") or pop.get("zip4") or pop.get("foreign_postal_code") or "",
        "competition_type": latest.get("extent_competed_description") or "",
        "solicitation_procedure": latest.get("solicitation_procedures_description") or "",
        "pricing_type": latest.get("type_of_contract_pricing_description") or "",
        "naics_description": latest.get("naics_description") or "",
        "psc_code": latest.get("product_or_service_code") or psc_base.get("code") or "",
        "psc_description": latest.get("product_or_service_description") or psc_base.get("description") or "",
        "parent_contract": parent.get("piid") or "",
        "parent_contract_type": parent.get("type_of_idc_description") or parent.get("idv_type_description") or "",
    }

def _write_ingest_log(run_date: str, record_count: int, status: str, error_message) -> None:
    """Write one row to ingest_log. Failure is non-fatal — log and swallow."""
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ingest_log
                    (run_date, source, record_count, duration_seconds, status, error_message, created_at)
                VALUES (:run_date, :source, :record_count, NULL, :status, :error_message, :created_at)
            """), {
                "run_date": run_date,
                "source": "usaspending",
                "record_count": record_count,
                "status": status,
                "error_message": error_message,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as log_exc:
        logger.warning("could not write ingest_log: %s", log_exc)


def _naics_code(naics):
    """Normalize the USASpending search ``NAICS`` field to a code string.

    The award search endpoint returns NAICS as a ``{"code", "description"}``
    object, but the contracts.naics_code column is TEXT — binding the raw dict
    raises a sqlite ProgrammingError. Extract the code; tolerate a plain string
    or a missing value.
    """
    if isinstance(naics, dict):
        return naics.get("code") or ""
    return naics or ""


def _naics_description(naics):
    """Extract the human-readable description from a USASpending NAICS field."""
    if isinstance(naics, dict):
        return naics.get("description") or ""
    return ""


def main():
    today = _today()  # fresh on every call — avoids stale-date bug in long-lived Celery workers
    cutoff = today + timedelta(days=540)

    if not os.environ.get("SAM_API_KEY"):
        logger.warning(
            "SAM_API_KEY is not set — SAM.gov solicitation enrichment will be skipped"
        )

    logger.info("ingest starting: today=%s cutoff=%s", today, cutoff)
    rows = []

    for c in fetch_contracts(today, cutoff):
        end = parse_date(c.get("End Date"))
        start = parse_date(c.get("Start Date"))

        if not end or not (today <= end <= cutoff):
            continue

        amount = money(c.get("Award Amount"))
        if amount > MAX_CONTRACT_VALUE:
            continue

        days_left = (end - today).days

        # Search endpoint gives a state code + zip5 (no city name); city comes from enrichment
        pop_state = c.get("Place of Performance State Code") or ""
        pop_zip = c.get("Place of Performance Zip5") or ""

        rows.append({
            "score": score(amount, days_left),
            "days_remaining": days_left,
            "contract": c.get("Award ID"),
            "vendor": c.get("Recipient Name"),
            "value": amount,
            "start_date": start.isoformat() if start else "",
            "end_date": end.isoformat(),
            "agency": c.get("Awarding Agency"),
            "sub_agency": c.get("Awarding Sub Agency"),
            "description": c.get("Description", ""),
            "naics_code": _naics_code(c.get("NAICS")),
            "naics_description": _naics_description(c.get("NAICS")),
            "generated_internal_id": c.get("generated_internal_id"),
            "internal_id": c.get("internal_id"),
            "solicitation_id": "",
            "awarding_office": "",
            "funding_office": "",
            "recipient_uei": "",
            "recipient_city": "",
            "recipient_state": "",
            "recipient_country": "",
            "recipient_address": "",
            "recipient_zip": "",
            # State code + zip available for every contract; city filled in by enrichment
            "performance_city": "",
            "performance_state": str(pop_state) if pop_state else "",
            "performance_country": "",
            "performance_zip": str(pop_zip) if pop_zip else "",
            "competition_type": "",
            "solicitation_procedure": "",
            "pricing_type": "",
            "psc_code": "",
            "psc_description": "",
            "parent_contract": "",
            "parent_contract_type": "",
        })

    rows.sort(key=lambda x: (-x["score"], x["days_remaining"]))

    enrich_count = 0
    for row in rows:
        if should_enrich(row):
            detail = fetch_award_detail(enrichment_award_id(row))
            enriched = enrichment_from_detail(detail)
            # Only override these fields if enrichment has better data; don't blank them
            for k, v in enriched.items():
                if v or k not in ("performance_city", "performance_state", "performance_zip", "performance_country", "naics_description"):
                    row[k] = v
            enrich_count += 1
            time.sleep(0.2)

    for row in rows:
        rs = recompete_score(row)
        row["recompete_score"] = rs
        row["priority"] = priority(rs)

    rows.sort(key=lambda r: (-int(r["recompete_score"]), -float(r["value"]), int(r["days_remaining"])))

    fields = [
        "recompete_score", "priority", "score", "days_remaining", "contract", "vendor", "value",
        "start_date", "end_date", "agency", "sub_agency",
        "description", "naics_code", "naics_description", "generated_internal_id", "internal_id",
        "solicitation_id", "awarding_office", "funding_office",
        "recipient_uei", "recipient_city", "recipient_state",
        "recipient_country", "recipient_address", "recipient_zip",
        "performance_city", "performance_state", "performance_country",
        "performance_zip", "competition_type", "solicitation_procedure",
        "pricing_type", "psc_code", "psc_description",
        "parent_contract", "parent_contract_type",
        "sam_title", "sam_type", "sam_due_date",
        "sam_set_aside", "sam_naics", "sam_url"
    ]

    sam_cache = {}
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

    with open("recompete_report.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Persist to the database so the scheduled run_ingest task actually updates
    # the contracts the app serves — previously this script only wrote a CSV, so
    # the nightly ingest fetched data but never touched the DB. save_snapshot()
    # is idempotent (upsert by internal_id + UNIQUE(run_date, internal_id)) and
    # calls init_db() itself, so the job is safe to rerun. detect_changes() is
    # likewise idempotent for the run_date (it clears that date's changes first).
    run_date = str(today)  # today() — not module-level TODAY — so date is always current
    try:
        save_snapshot(run_date, rows)
        detect_changes(run_date)
        detect_field_changes(run_date)
    except Exception as exc:
        logger.error("ingest persistence failed: %s", exc)
        _write_ingest_log(run_date, 0, "failure", str(exc))
        raise

    if not rows:
        msg = (
            f"ingest complete but 0 rows matched filter today={today} — "
            "possible API issue or date filter problem"
        )
        logger.error(msg)
        _write_ingest_log(run_date, 0, "failure", msg)
        raise RuntimeError(msg)

    logger.info("ingest complete: %d contracts persisted (snapshot %s)", len(rows), run_date)
    logger.info("tier-a enrichment: %d contracts enriched", enrich_count)
    logger.info("sam.gov enrichment: %d solicitations matched", sam_count)
    _write_ingest_log(run_date, len(rows), "success", None)

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    main()
