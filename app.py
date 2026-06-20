import csv
import io
import logging
import os
import subprocess
import sys
import threading
from datetime import date
from logging.handlers import RotatingFileHandler

import stripe
from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

from auth import bp as auth_bp
from change_detector import detect_changes
from db import (
    connect,
    get_contracts,
    init_db,
    save_demo_request,
    save_early_access,
    save_snapshot,
    upsert_contract,
)
from analytics import vendor_profile_analytics as vendor_profile_query
from analytics import agency_profile as agency_profile_query
from analytics import dashboard_analytics, opportunity_recommendations
from report_builder import build_report
from views import SAVED_VIEWS, build_view_query, format_filter_summary
import hubspot_service

app = Flask(__name__)
load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.register_blueprint(auth_bp)
app.jinja_env.globals["format_filter_summary"] = format_filter_summary

init_db()

# ---------------------------------------------------------------------------
# Redis availability check (degraded mode on failure — never blocks startup)
# ---------------------------------------------------------------------------

def _check_redis() -> None:
    import redis as _redis
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = _redis.from_url(url, socket_connect_timeout=2)
        r.ping()
    except Exception:
        logging.getLogger(__name__).warning(
            "Redis unavailable at %s — running without background tasks", url
        )


_check_redis()

# ---------------------------------------------------------------------------
# Ingest logging
# ---------------------------------------------------------------------------

INGEST_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest.log")


def _setup_ingest_logger() -> logging.Logger:
    logger = logging.getLogger("ingest")
    if not logger.handlers:
        handler = RotatingFileHandler(INGEST_LOG_PATH, maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_ingest_logger = _setup_ingest_logger()


def _capture_subprocess_output(proc: subprocess.Popen, logger: logging.Logger) -> None:
    """Background thread: drain subprocess stdout+stderr into the ingest log."""
    try:
        for line in iter(proc.stdout.readline, b""):
            logger.info(line.decode("utf-8", errors="replace").rstrip())
        proc.wait()
        logger.info("[exit code %d]", proc.returncode)
    except Exception as exc:
        logger.warning("[capture error: %s]", exc)


def _warn_if_ephemeral_db() -> None:
    """Log a warning when deployed on Railway without a persistent volume.

    Railway's filesystem is ephemeral — contracts.db is wiped on every
    redeploy unless a volume is attached and DB_PATH points to it.
    RAILWAY_ENVIRONMENT is set on all Railway deployments; RAILWAY_VOLUME_NAME
    is only set when a volume is attached to the service.
    """
    if os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("RAILWAY_VOLUME_NAME"):
        logging.warning(
            "DATA LOSS RISK: Running on Railway with no persistent volume. "
            "contracts.db is on the ephemeral filesystem and will be wiped on "
            "every redeploy. Attach a Railway volume and point DB_PATH to it."
        )


_warn_if_ephemeral_db()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

_PUBLIC_PATHS = frozenset({
    "/health",
    "/login",
    "/register",
    "/create-checkout-session",
    "/success",
    "/cancel",
    "/demo",
    "/early-access",
    "/stripe/webhook",
})


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
    con = connect()
    analytics = dashboard_analytics(con)
    recommendations = opportunity_recommendations(con)
    con.close()
    return render_template(
        "dashboard.html",
        report=build_report(date.today().isoformat()),
        analytics=analytics,
        recommendations=recommendations,
    )


@app.route("/contracts")
def contracts():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", type=float)
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")
    page = int(request.args.get("page", 1))

    days_int = int(days) if days else None
    if days_int is not None and days_int < 0:
        return "days parameter must be a non-negative integer", 400

    if min_value is not None and min_value < 0:
        return "min_value must be a non-negative number", 400

    result = get_contracts(
        q=q,
        agency=agency,
        priority=priority,
        days=days_int,
        min_value=min_value,
        sort=sort,
        direction=direction,
        page=page,
        limit=25,
    )

    _total = result["total"]
    _page_size = 25
    _total_pages = max(1, (_total + _page_size - 1) // _page_size)

    return render_template(
        "contracts.html",
        rows=result["contracts"],
        total=_total,
        total_pages=_total_pages,
        start=result["start"] + 1 if result["count"] else 0,
        end=result["start"] + result["count"],
        page=result["page"],
        has_prev=result["page"] > 1,
        has_next=result["start"] + result["count"] < _total,
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

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=request.host_url.rstrip("/") + "/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + "/cancel",
        )
        return redirect(checkout.url, code=303)
    except Exception as e:
        return str(e), 500


@app.route("/success")
def success():
    session_id = request.args.get("session_id", "")
    if session_id:
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            details = checkout.get("customer_details") or {}
            email = details.get("email") or ""
            name = details.get("name") or ""
            if email:
                hubspot_service.handle_stripe_checkout(
                    email=email, name=name, stripe_session_id=session_id
                )
        except Exception:
            logging.exception("Could not retrieve Stripe session %s", session_id)
    return "<h1>Payment successful</h1><p>Welcome to Recompete Beta.</p>"


@app.route("/cancel")
def cancel():
    return "<h1>Checkout canceled</h1><p>You were not charged.</p>"


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(request.get_json(force=True), stripe.api_key)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        logging.warning("Stripe webhook signature error: %s", e)
        return "Bad request", 400

    if event["type"] == "checkout.session.completed":
        checkout = event["data"]["object"]
        details = checkout.get("customer_details") or {}
        email = details.get("email") or ""
        name = details.get("name") or ""
        session_id = checkout.get("id") or ""
        if email:
            hubspot_service.handle_stripe_checkout(
                email=email, name=name, stripe_session_id=session_id
            )
    return "", 200


@app.route("/demo", methods=["GET", "POST"])
def demo():
    message = None
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        company = request.form.get("company", "").strip()
        phone = request.form.get("phone", "").strip()
        notes = request.form.get("notes", "").strip()

        if not email or "@" not in email:
            error = "A valid email address is required."
        else:
            contact_id, deal_id = hubspot_service.handle_demo_request(
                email=email, name=name, company=company, phone=phone, notes=notes
            )
            save_demo_request(
                email=email,
                name=name,
                company=company,
                phone=phone,
                notes=notes,
                hubspot_contact_id=contact_id,
                hubspot_deal_id=deal_id,
            )
            message = "Thanks! We'll be in touch shortly to schedule your demo."

    return render_template("demo.html", message=message, error=error)


@app.route("/early-access", methods=["GET", "POST"])
def early_access():
    message = None
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email or "@" not in email:
            error = "A valid email address is required."
        else:
            contact_id = hubspot_service.handle_early_access_signup(email)
            save_early_access(email=email, hubspot_contact_id=contact_id)
            message = "You're on the list! We'll reach out when early access opens."

    return render_template("early_access.html", message=message, error=error)


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
            from tasks import run_ingest
            job = run_ingest.delay()
            return jsonify({"task_id": job.id})

    return render_template("ingest.html", message=message, error=error)


@app.route("/ingest/status")
def ingest_status():
    task_id = request.args.get("task_id")
    if task_id:
        try:
            from tasks import tasks as celery_app
            result = celery_app.AsyncResult(task_id)
            status = result.status
            if result.successful():
                message = "Ingest completed successfully."
                progress = 100
            elif result.failed():
                message = f"Ingest failed: {result.result}"
                progress = 0
            else:
                message = "Ingest is running…"
                progress = 50
            return jsonify({"task_id": task_id, "status": status,
                            "message": message, "progress": progress})
        except Exception as exc:
            logging.getLogger(__name__).warning("AsyncResult error: %s", exc)
            return jsonify({"task_id": task_id, "status": "UNKNOWN",
                            "message": "Unable to fetch task status.", "progress": 0})

    try:
        with open(INGEST_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = "".join(lines[-50:]) if lines else "(no log entries yet)"
    except FileNotFoundError:
        tail = "(ingest.log not found — no API pull has run yet)"
    return tail, 200, {"Content-Type": "text/plain; charset=utf-8"}


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
