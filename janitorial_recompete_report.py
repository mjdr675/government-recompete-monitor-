import csv
import requests
from datetime import date, datetime, timedelta

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
TODAY = date.today()
CUTOFF = TODAY + timedelta(days=540)

def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def fetch_contracts():
    out = []
    for page in range(1, 101):
        payload = {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "naics_codes": ["561720"]
            },
            "fields": [
                "Award ID", "Recipient Name", "Award Amount",
                "Start Date", "End Date",
                "Awarding Agency", "Awarding Sub Agency", "Description"
            ],
            "page": page,
            "limit": 100,
            "sort": "Start Date",
            "order": "desc"
        }

        r = requests.post(API_URL, json=payload, timeout=30)
        print("page", page, "status", r.status_code)
        r.raise_for_status()

        data = r.json()
        results = data.get("results", [])
        out.extend(results)

        if not data.get("page_metadata", {}).get("hasNext"):
            break

    return out

def score(amount, days_left):
    value_score = 40 if amount >= 1000000 else 30 if amount >= 250000 else 20 if amount >= 50000 else 10
    time_score = 40 if days_left <= 180 else 30 if days_left <= 365 else 20
    return value_score + time_score

def main():
    rows = []

    for c in fetch_contracts():
        end = parse_date(c.get("End Date"))
        start = parse_date(c.get("Start Date"))

        if not end:
            continue

        if TODAY <= end <= CUTOFF:
            amount = c.get("Award Amount") or 0
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
                "description": c.get("Description", "")
            })

    rows.sort(key=lambda x: (-x["score"], x["days_remaining"]))

    with open("janitorial_recompete_report.csv", "w", newline="") as f:
        fields = ["score","days_remaining","contract","vendor","value","start_date","end_date","agency","sub_agency","description"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("Saved", len(rows), "upcoming recompete opportunities.")

if __name__ == "__main__":
    main()
