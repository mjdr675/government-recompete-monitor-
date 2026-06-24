import csv
import time
from sam_lookup import lookup_solicitation
from change_detector import detect_changes
from update_detector import detect_field_changes
from db import save_snapshot
import requests
from datetime import date, datetime, timedelta

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

TODAY = date.today()
CUTOFF = TODAY + timedelta(days=540)

MAX_CONTRACT_VALUE = 10_000_000  # $10M ceiling — right-sized for 50-100 employee companies

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

def get_nested(d, path, default=""):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur

def fetch_contracts():
    out = []
    session = requests.Session()

    for page in range(1, 101):
        payload = {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [
                    {
                        "start_date": TODAY.isoformat(),
                        "end_date": CUTOFF.isoformat(),
                        "date_type": "end_date",
                    }
                ],
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
                "NAICS Code",
            ],
            "page": page,
            "limit": 100,
            "sort": "Award Amount",
            "order": "desc",
        }

        success = False
        for attempt in range(1, 6):
            try:
                r = session.post(API_URL, json=payload, timeout=60)
                print("search page", page, "attempt", attempt, "status", r.status_code)
                if r.status_code < 500:
                    r.raise_for_status()
                    success = True
                    break
                time.sleep(3 * attempt)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f"search page {page} attempt {attempt} connection error: {e}")
                time.sleep(5 * attempt)
                session = requests.Session()

        if not success:
            print(f"Skipping page {page} after 5 failed attempts")
            continue

        data = r.json()
        results = data.get("results", [])

        for c in results:
            end = parse_date(c.get("End Date"))
            if not end or not (TODAY <= end <= CUTOFF):
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
    a=(row.get("agency") or "").upper(); return 5 if "DEFENSE" in a else 4 if "VETERANS AFFAIRS" in a else 3 if "HOMELAND SECURITY" in a else 0

def solicitation_bonus(row):
    return 5 if row.get("solicitation_id") else 0

def office_bonus(row):
    o=(row.get("awarding_office") or "").upper(); return 5 if any(x in o for x in ["697DCK","NETWORK CONTRACT OFFICE","DEFENSE HEALTH AGENCY","NAVFAC","W40M"]) else 0

def recompete_score(row):
    return competition_score(row.get("competition_type")) + value_score(row.get("value")) + days_score(row.get("days_remaining")) + agency_bonus(row) + solicitation_bonus(row) + office_bonus(row)

def priority(score):
    return "CRITICAL" if score >= 90 else "HIGH" if score >= 75 else "MEDIUM" if score >= 60 else "LOW"

def enrichment_award_id(row):
    return row.get("internal_id") or row.get("generated_internal_id")

def should_enrich(row):
    return row["value"] >= 500_000 and row["days_remaining"] <= 180 and bool(enrichment_award_id(row))

def fetch_award_detail(internal_id):
    try:
        url = AWARD_DETAIL_URL.format(award_id=internal_id)
        r = requests.get(url, timeout=30)
        print("detail", internal_id, "status", r.status_code)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("detail failed", internal_id, e)
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

def main():
    rows = []

    for c in fetch_contracts():
        end = parse_date(c.get("End Date"))
        start = parse_date(c.get("Start Date"))

        if not end or not (TODAY <= end <= CUTOFF):
            continue

        amount = money(c.get("Award Amount"))
        if amount > MAX_CONTRACT_VALUE:
            continue

        days_left = (end - TODAY).days

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
            "naics_code": c.get("NAICS Code", ""),
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

    enrich_count = 0
    for row in rows:
        if should_enrich(row):
            detail = fetch_award_detail(enrichment_award_id(row))
            row.update(enrichment_from_detail(detail))
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
        "description", "naics_code", "generated_internal_id", "internal_id",
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

    run_date = str(TODAY)
    save_snapshot(run_date, rows)
    detect_changes(run_date)
    detect_field_changes(run_date)

    print("Saved", len(rows), "upcoming recompete opportunities.")
    print(f"Persisted {len(rows)} rows to the contracts database (snapshot {run_date}).")
    print("Enriched", enrich_count, "Tier A opportunities.")
    print("SAM.gov matches", sam_count, "solicitations.")

if __name__ == "__main__":
    main()
