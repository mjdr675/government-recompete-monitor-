import csv
import io
import os
import subprocess
import sys
from datetime import date

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from auth import bp as auth_bp
from change_detector import detect_changes
from db import connect, get_contracts, init_db, upsert_contract, save_snapshot
from analytics import vendor_profile_analytics as vendor_profile_query
from analytics import agency_profile as agency_profile_query
from report_builder import build_report
from views import SAVED_VIEWS, build_view_query

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.register_blueprint(auth_bp)

_PUBLIC_PATHS = frozenset({"/health", "/login", "/register"})


@app.before_request
def require_login():
    if request.path in _PUBLIC_PATHS:
        return None
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.path))


@app.route("/health")
def health():
    # Railway polls this endpoint to confirm the app is running.
    return {"status": "ok"}, 200


@app.route("/")
def dashboard():
    return render_template("dashboard.html", report=build_report(date.today().isoformat()))


@app.route("/contracts")
def contracts():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")
    page = int(request.args.get("page", 1))

    result = get_contracts(
        q=q,
        agency=agency,
        priority=priority,
        days=int(days) if days else None,
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

    return render_template("contract_detail.html", row=row)


@app.route("/compare")
def compare():
    def _fetch(internal_id):
        if not internal_id:
            return None
        con = connect()
        con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
        row = con.execute(
            "SELECT * FROM contracts WHERE internal_id=?",
            (internal_id,),
        ).fetchone()
        con.close()
        return row

    id_a = request.args.get("a", "").strip()
    id_b = request.args.get("b", "").strip()
    return render_template("compare.html", a=_fetch(id_a), b=_fetch(id_b),
                           id_a=id_a, id_b=id_b)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
