import os
import requests
from datetime import date, timedelta

API_URL = "https://api.sam.gov/opportunities/v2/search"

def lookup_solicitation(solnum):
    api_key = os.getenv("SAM_API_KEY")

    if not api_key or not solnum:
        return None

    today = date.today()

    params = {
        "api_key": api_key,
        "solnum": solnum,
        "postedFrom": (today - timedelta(days=365)).strftime("%m/%d/%Y"),
        "postedTo": (today + timedelta(days=365)).strftime("%m/%d/%Y"),
        "limit": 1,
        "offset": 0,
    }

    try:
        r = requests.get(API_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        opportunities = data.get("opportunitiesData") or data.get("data") or []

        if not opportunities:
            return None

        item = opportunities[0]

        return {
            "sam_title": item.get("title", ""),
            "sam_type": item.get("type", ""),
            "sam_due_date": item.get("responseDeadLine", ""),
            "sam_set_aside": item.get("setAside", ""),
            "sam_naics": item.get("naicsCode", ""),
            "sam_url": item.get("uiLink", ""),
        }

    except Exception:
        return None
