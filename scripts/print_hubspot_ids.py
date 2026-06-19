import os
import sys
import pathlib
import requests
from dotenv import load_dotenv, dotenv_values

# Always load from the project root .env, regardless of cwd
ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
print(f"[debug] loading .env from: {ENV_PATH}  (exists: {ENV_PATH.exists()})")
load_dotenv(dotenv_path=ENV_PATH, override=True)

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip().strip('"').strip("'")
if not TOKEN:
    sys.exit("HUBSPOT_ACCESS_TOKEN is not set in .env")

print(f"[debug] token first 8 chars : {TOKEN[:8]}")
print(f"[debug] token length         : {len(TOKEN)}")
print(f"[debug] contains spaces      : {' ' in TOKEN}")
print(f"[debug] contains newlines    : {any(c in TOKEN for c in chr(10) + chr(13))}")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

probe = requests.get("https://api.hubapi.com/account-info/v3/details", headers=HEADERS)
print(f"[debug] account-info: HTTP {probe.status_code}")
if not probe.ok:
    print(f"        {probe.text}")
    print("[!] Token rejected — update HUBSPOT_ACCESS_TOKEN in .env with a Private App token.")
    sys.exit(1)

resp = requests.get("https://api.hubapi.com/crm/v3/pipelines/deals", headers=HEADERS)
if not resp.ok:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

pipelines = resp.json().get("results", [])

TARGET = "Beta Customers"
beta = next((p for p in pipelines if p["label"].strip() == TARGET), None)

if beta is None:
    print(f"[!] Pipeline '{TARGET}' not found. Available pipelines:")
    for p in pipelines:
        print(f"  {p['label']!r}  id={p['id']}")
    sys.exit(1)

print(f"Pipeline: {beta['label']!r}  id={beta['id']}")
print()
for s in beta["stages"]:
    print(f"  Stage: {s['label']!r}  id={s['id']}")

demo_stage = next((s for s in beta["stages"] if "demo" in s["label"].lower()), None)
paying_stage = next(
    (s for s in beta["stages"] if "paying" in s["label"].lower() or "customer" in s["label"].lower()),
    None,
)

print()
print(f"HUBSPOT_BETA_PIPELINE_ID={beta['id']}")
print(f"HUBSPOT_DEMO_STAGE_ID={demo_stage['id'] if demo_stage else '<not found>'}")
print(f"HUBSPOT_PAYING_STAGE_ID={paying_stage['id'] if paying_stage else '<not found>'}")
