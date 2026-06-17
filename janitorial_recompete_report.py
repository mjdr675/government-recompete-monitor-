# janitorial_recompete_report.py

import requests
import csv
from datetime import date, timedelta

USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
NAICS = "561720"  # Janitorial Services


def fetch_expiring_contracts(days_ahead=540, limit=100):
    today = date.today()
    end = today + timedelta(days=days_ahead)

    payload = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": [NAICS],
            "time_period": [
                {
                    "start_date": "2020-01-01",
                    "end_date": end.isoformat()
                }
            ]
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Description"
        ],
        "page": 1,
        "limit": limit,
        "sort": "End Date",
        "order": "asc"
    }

    r = requests.post(USASPENDING_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()

    return data.get("results", [])


def score_contract(row):
    amount = row.get("Award Amount") or 0

    try:
        amount = float(amount)
    except:
        amount = 0

    score = 0

    if amount >= 1_000_000:
        score += 40
    elif amount >= 250_000:
        score += 30
    elif amount >= 100_000:
        score += 20
    else:
        score += 10

    desc = (row.get("Description") or "").lower()

    if "option" in desc or "extension" in desc:
        score += 20

    if "hospital" in desc or "medical" in desc or "va" in desc:
        score += 15

    return min(score, 100)


def build_report():
    contracts = fetch_expiring_contracts()

    rows = []

    for c in contracts:
        rows.append({
            "score": score_contract(c),
            "contract": c.get("Description"),
            "vendor": c.get("Recipient Name"),
            "value": c.get("Award Amount"),
            "start_date": c.get("Start Date"),
            "end_date": c.get("End Date"),
            "agency": c.get("Awarding Agency"),
            "sub_agency": c.get("Awarding Sub Agency"),
            "award_id": c.get("Award ID"),
        })

    rows.sort(key=lambda x: x["score"], reverse=True)

    with open("janitorial_recompete_report.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("Created janitorial_recompete_report.csv")
    print(f"Contracts found: {len(rows)}")


if __name__ == "__main__":
    build_report()
