import csv
import io
import os
import subprocess
import sys
from datetime import date
from functools import wraps

from urllib.parse import urlencode

from flask import Flask, flash, redirect, render_template, request, Response

from change_detector import detect_changes
from db import (
    connect, get_contracts, init_db, upsert_contract, save_snapshot,
    create_saved_search, get_saved_searches, get_saved_search,
    rename_saved_search, delete_saved_search,
    watch_contract, unwatch_contract, is_watched, get_watchlist,
)
from analytics import vendor_profile_analytics as vendor_profile_query
from analytics import agency_profile as agency_profile_query
from report_builder import build_report
from views import SAVED_VIEWS, build_view_query
from alerts import alert_config, send_alert

app = Flask(__name__)

_AUTH_USER = os.environ.get("AUTH_USER", "")
_AUTH_PASS = os.environ.get("AUTH_PASS", "")

def _require_auth():
    if not _AUTH_USER or not _AUTH_PASS:
        return None
    auth = request.authorization
    if auth and auth.username == _AUTH_USER and auth.password == _AUTH_PASS:
        return None
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Recompete Monitor"'},
    )

@app.before_request
def check_auth():
    if request.path == "/health":
        return None
    return _require_auth()


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/")
def dashboard():
    total_contracts = get_contracts(limit=1)["total"]
    return render_template(
        "dashboard.html",
        report=build_report(date.today().isoformat()),
        saved_searches=get_saved_searches(),
        watched=get_watchlist(),
        total_contracts=total_contracts,
        alert_configured=bool(os.environ.get("ALERT_TO")),
    )


@app.route("/contracts")
def contracts():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", None)
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")
    page = int(request.args.get("page", 1))

    result = get_contracts(
        q=q,
        agency=agency,
        priority=priority,
        days=int(days) if days else None,
        min_value=float(min_value) if min_value else None,
        sort=sort,
        direction=direction,
        page=page,
        limit=25,
    )

    return render_template(
        "contracts.html",
        rows=result["contracts"],
        total=result["total"],
        start=result["start"] + 1 if result["count"] else 0,
        end=result["start"] + result["count"],
        page=result["page"],
        has_prev=result["page"] > 1,
        has_next=result["start"] + result["count"] < result["total"],
        priorities=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        q=q,
        agency=agency,
        priority=priority,
        days=days or "",
        min_value=min_value or "",
        sort=sort,
        direction=direction,
    )


@app.route("/vendor/<name>")
def vendor_profile(name):
    con = connect()
    profile = vendor_profile_query(con, name)
    con.close()
    return render_template("vendor.html", vendor=name, profile=profile)


@app.route("/agency/<name>")
def agency_profile(name):
    con = connect()
    profile = agency_profile_query(con, name)
    con.close()
    return render_template("agency.html", agency=name, profile=profile)


@app.route("/views")
def views_list():
    return render_template("views.html", views=SAVED_VIEWS)


@app.route("/views/<view_id>")
def views_detail(view_id):
    qs = build_view_query(view_id)
    if not qs:
        return redirect("/contracts")
    return redirect(f"/contracts?{qs}")


@app.route("/ingest", methods=["GET", "POST"])
def ingest():
    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "csv":
            f = request.files.get("file")
            if not f or not f.filename.endswith(".csv"):
                error = "Please upload a .csv file."
            else:
                text = f.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(text))
                rows = list(reader)
                init_db()
                for row in rows:
                    upsert_contract(row)
                run_date = date.today().isoformat()
                save_snapshot(run_date, rows)
                detect_changes(run_date)
                message = f"Imported {len(rows)} contracts from CSV."

        elif action == "api":
            subprocess.Popen(
                [sys.executable, "recompete_report.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            message = "API pull started in background. Refresh the dashboard in a few minutes."

    return render_template("ingest.html", message=message, error=error)


@app.route("/contract/<internal_id>")
def contract_detail(internal_id):
    con = connect()
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    row = con.execute(
        "SELECT * FROM contracts WHERE internal_id=?",
        (internal_id,),
    ).fetchone()
    con.close()

    if not row:
        return redirect("/contracts")

    return render_template("contract_detail.html", row=row, watched=is_watched(internal_id))


@app.route("/saved-searches")
def saved_searches():
    return render_template("saved_searches.html", searches=get_saved_searches())


@app.route("/saved-searches/save", methods=["POST"])
def saved_searches_save():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(request.referrer or "/contracts")
    filters = {
        k: v for k, v in {
            "q": request.form.get("q", ""),
            "agency": request.form.get("agency", ""),
            "priority": request.form.get("priority", ""),
            "days": request.form.get("days", ""),
            "sort": request.form.get("sort", ""),
            "direction": request.form.get("direction", ""),
        }.items()
        if v
    }
    create_saved_search(name, filters)
    return redirect("/saved-searches")


@app.route("/saved-searches/<int:search_id>/load")
def saved_searches_load(search_id):
    search = get_saved_search(search_id)
    if not search:
        return redirect("/saved-searches")
    qs = urlencode(search["filters"])
    return redirect(f"/contracts?{qs}" if qs else "/contracts")


@app.route("/saved-searches/<int:search_id>/rename", methods=["POST"])
def saved_searches_rename(search_id):
    name = request.form.get("name", "").strip()
    if name:
        rename_saved_search(search_id, name)
    return redirect("/saved-searches")


@app.route("/saved-searches/<int:search_id>/delete", methods=["POST"])
def saved_searches_delete(search_id):
    delete_saved_search(search_id)
    return redirect("/saved-searches")


@app.route("/watchlist")
def watchlist():
    return render_template("watchlist.html", contracts=get_watchlist())


@app.route("/watch/<internal_id>", methods=["POST"])
def watch(internal_id):
    watch_contract(internal_id)
    return redirect(request.form.get("next") or f"/contract/{internal_id}")


@app.route("/unwatch/<internal_id>", methods=["POST"])
def unwatch(internal_id):
    unwatch_contract(internal_id)
    return redirect(request.form.get("next") or f"/contract/{internal_id}")


@app.route("/alerts", methods=["GET", "POST"])
def alerts_page():
    result = None
    if request.method == "POST":
        run_date = request.form.get("run_date") or date.today().isoformat()
        result = send_alert(run_date)
    return render_template("alerts.html", config=alert_config(), result=result)


@app.route("/contracts.csv")
def contracts_csv():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", None)
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")

    result = get_contracts(
        q=q,
        agency=agency,
        priority=priority,
        days=int(days) if days else None,
        min_value=float(min_value) if min_value else None,
        sort=sort,
        direction=direction,
        all_rows=True,
    )

    fields = ["internal_id", "award_id", "vendor", "agency", "sub_agency",
              "value", "start_date", "end_date", "days_remaining",
              "competition_type", "solicitation_id", "recompete_score", "priority"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in result["contracts"]:
        writer.writerow({f: row[f] for f in fields})

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=contracts.csv"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
