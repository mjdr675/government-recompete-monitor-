import csv
import io
import json
import logging
import urllib.parse
import os
import subprocess
import sys
import threading
from datetime import date, datetime, timezone
from logging.handlers import RotatingFileHandler

import stripe
from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from auth import bp as auth_bp
from email_service import send_email
from change_detector import detect_changes
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import (
    connect,
    get_contracts,
    get_engine,
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

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
        environment=os.environ.get("RAILWAY_ENVIRONMENT", "development"),
    )

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])
app.register_blueprint(auth_bp)
app.view_functions["auth.login"] = limiter.limit(
    "5 per minute", per_method=True, methods=["POST"]
)(app.view_functions["auth.login"])
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
if not STRIPE_WEBHOOK_SECRET:
    logging.warning(
        "STRIPE_WEBHOOK_SECRET is not set. POST /stripe/webhook will return 400 "
        "for all requests. Set this env var in production."
    )

_PUBLIC_PATHS = frozenset({
    "/health",
    "/login",
    "/register",
    "/forgot-password",
    "/create-checkout-session",
    "/success",
    "/cancel",
    "/demo",
    "/early-access",
    "/stripe/webhook",
    "/watchlist/add",
    "/watchlist/remove",
    "/searches/save",
    "/api/data-freshness",
})


@app.before_request
def require_login():
    if request.path in _PUBLIC_PATHS:
        return None
    # Dynamic-path JSON API routes handle their own auth (return 401 JSON)
    if request.method == "DELETE" and request.path.startswith("/searches/"):
        return None
    if request.method == "POST" and request.path.endswith("/note"):
        return None
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.path))


@app.route("/health")
def health():
    # Railway polls this endpoint to confirm the app is running.
    return {"status": "ok"}, 200


@app.route("/")
def dashboard():
    analytics = dashboard_analytics()
    recommendations = opportunity_recommendations()
    engine = get_engine()
    last_ingest = None
    hours_ago = None
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT created_at FROM ingest_log"
                " WHERE status = 'success' ORDER BY created_at DESC LIMIT 1"
            )
        ).fetchone()
    if row:
        last_ingest = row[0]
        try:
            ts = datetime.fromisoformat(last_ingest)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hours_ago = round((datetime.now(timezone.utc) - ts).total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            pass
    return render_template(
        "dashboard.html",
        report=build_report(date.today().isoformat()),
        analytics=analytics,
        recommendations=recommendations,
        last_ingest=last_ingest,
        hours_ago=hours_ago,
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

    watchlist_ids = set()
    if g.user:
        engine = get_engine()
        with engine.connect() as conn:
            wl_rows = conn.execute(
                text("SELECT internal_id FROM user_watchlist WHERE user_id = :uid"),
                {"uid": g.user["id"]},
            ).fetchall()
        watchlist_ids = {r[0] for r in wl_rows}

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
        watchlist_ids=watchlist_ids,
    )


@app.route("/contracts/export.csv")
def contracts_export():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", type=float)
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")

    days_int = int(days) if days else None
    result = get_contracts(
        q=q, agency=agency, priority=priority,
        days=days_int, min_value=min_value,
        sort=sort, direction=direction,
        page=1, limit=10000,
    )

    fields = ["internal_id", "award_id", "vendor", "agency", "value",
              "end_date", "days_remaining", "priority", "recompete_score"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in result["contracts"]:
        writer.writerow({f: row[f] for f in fields})

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=\"contracts.csv\""},
    )


@app.route("/vendor/<name>")
def vendor_profile(name):
    profile = vendor_profile_query(name)
    return render_template("vendor.html", vendor=name, profile=profile)


@app.route("/agency/<name>")
def agency_profile(name):
    profile = agency_profile_query(name)
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
@csrf.exempt
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        logging.warning("Stripe webhook received but STRIPE_WEBHOOK_SECRET is not configured")
        return "Webhook secret not configured", 400
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
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


@app.route("/ingest/email-test")
def ingest_email_test():
    try:
        result = send_email(
            to=g.user["email"],
            subject="Test email — Gov Recompete Monitor",
            html_body="<p>Email delivery is working.</p>",
            text_body="Email delivery is working.",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    if result is None:
        return jsonify({"ok": False, "error": "EMAIL_API_KEY not set"}), 503
    return jsonify({"ok": True, "to": g.user["email"]})


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

    is_bookmarked = False
    notes = []
    if g.user:
        engine = get_engine()
        with engine.connect() as conn:
            hit = conn.execute(
                text("SELECT 1 FROM user_watchlist WHERE user_id = :uid AND internal_id = :iid"),
                {"uid": g.user["id"], "iid": internal_id},
            ).fetchone()
            is_bookmarked = hit is not None
            note_rows = conn.execute(
                text(
                    "SELECT id, body, created_at FROM contract_notes"
                    " WHERE user_id = :uid AND internal_id = :iid"
                    " ORDER BY created_at DESC"
                ),
                {"uid": g.user["id"], "iid": internal_id},
            ).mappings().fetchall()
            notes = [dict(r) for r in note_rows]

    return render_template("contract_detail.html", row=row, is_bookmarked=is_bookmarked, notes=notes)


@app.route("/watchlist/add", methods=["POST"])
@csrf.exempt
def watchlist_add():
    if not g.user:
        return jsonify({"error": "login required"}), 401
    internal_id = (request.get_json(silent=True) or {}).get("internal_id", "").strip()
    if not internal_id:
        return jsonify({"ok": False, "error": "internal_id required"}), 400
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (:uid, :iid, :ts)"),
                {"uid": g.user["id"], "iid": internal_id, "ts": now},
            )
        return jsonify({"ok": True})
    except IntegrityError:
        return jsonify({"ok": True, "already": True})


@app.route("/watchlist/remove", methods=["POST"])
@csrf.exempt
def watchlist_remove():
    if not g.user:
        return jsonify({"error": "login required"}), 401
    internal_id = (request.get_json(silent=True) or {}).get("internal_id", "").strip()
    if not internal_id:
        return jsonify({"ok": False, "error": "internal_id required"}), 400
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM user_watchlist WHERE user_id = :uid AND internal_id = :iid"),
            {"uid": g.user["id"], "iid": internal_id},
        )
    return jsonify({"ok": True})


@app.route("/watchlist")
def watchlist():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.* FROM contracts c"
                " JOIN user_watchlist w ON w.internal_id = c.internal_id"
                " WHERE w.user_id = :uid"
                " ORDER BY c.days_remaining ASC"
            ),
            {"uid": g.user["id"]},
        ).mappings().fetchall()
    contracts = [dict(r) for r in rows]
    return render_template("watchlist.html", contracts=contracts, count=len(contracts))


@app.route("/searches/save", methods=["POST"])
@csrf.exempt
def searches_save():
    if not g.user:
        return jsonify({"error": "login required"}), 401
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    params = body.get("params", {})
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        if is_pg:
            row = conn.execute(
                text(
                    "INSERT INTO user_saved_searches (user_id, name, query_params_json, created_at)"
                    " VALUES (:uid, :name, :params, :ts) RETURNING id"
                ),
                {"uid": g.user["id"], "name": name, "params": json.dumps(params), "ts": now},
            ).fetchone()
            new_id = row[0]
        else:
            result = conn.execute(
                text(
                    "INSERT INTO user_saved_searches (user_id, name, query_params_json, created_at)"
                    " VALUES (:uid, :name, :params, :ts)"
                ),
                {"uid": g.user["id"], "name": name, "params": json.dumps(params), "ts": now},
            )
            new_id = result.lastrowid
    return jsonify({"ok": True, "id": new_id})


@app.route("/searches/<int:search_id>", methods=["DELETE"])
@csrf.exempt
def searches_delete(search_id):
    if not g.user:
        return jsonify({"error": "login required"}), 401
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM user_saved_searches WHERE id = :id AND user_id = :uid"),
            {"id": search_id, "uid": g.user["id"]},
        )
    return jsonify({"ok": True})


@app.route("/api/data-freshness")
def data_freshness():
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT created_at, source, record_count FROM ingest_log"
                " WHERE status = 'success' ORDER BY created_at DESC LIMIT 1"
            )
        ).fetchone()
        total = conn.execute(text("SELECT COUNT(*) FROM contracts")).scalar() or 0
    if row is None:
        return jsonify({"last_ingest": None, "record_count": 0, "source": None, "hours_ago": None})
    last_ingest = row[0]
    try:
        ts = datetime.fromisoformat(last_ingest)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hours_ago = round((datetime.now(timezone.utc) - ts).total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        hours_ago = None
    return jsonify({
        "last_ingest": last_ingest,
        "record_count": total,
        "source": row[1],
        "hours_ago": hours_ago,
    })


@app.route("/contract/<internal_id>/note", methods=["POST"])
@csrf.exempt
def contract_note_add(internal_id):
    if not g.user:
        return jsonify({"error": "login required"}), 401
    body = (request.get_json(silent=True) or {}).get("body", "").strip()
    if not body:
        return jsonify({"ok": False, "error": "body required"}), 400
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        if is_pg:
            row = conn.execute(
                text(
                    "INSERT INTO contract_notes (user_id, internal_id, body, created_at)"
                    " VALUES (:uid, :iid, :body, :ts) RETURNING id"
                ),
                {"uid": g.user["id"], "iid": internal_id, "body": body, "ts": now},
            ).fetchone()
            new_id = row[0]
        else:
            result = conn.execute(
                text(
                    "INSERT INTO contract_notes (user_id, internal_id, body, created_at)"
                    " VALUES (:uid, :iid, :body, :ts)"
                ),
                {"uid": g.user["id"], "iid": internal_id, "body": body, "ts": now},
            )
            new_id = result.lastrowid
    return jsonify({"ok": True, "id": new_id, "created_at": now})


@app.route("/searches")
def searches():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, query_params_json, created_at"
                " FROM user_saved_searches WHERE user_id = :uid"
                " ORDER BY created_at DESC"
            ),
            {"uid": g.user["id"]},
        ).mappings().fetchall()
    searches_list = []
    for r in rows:
        params = json.loads(r["query_params_json"] or "{}")
        searches_list.append({
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "params": params,
            "url": "/contracts?" + urllib.parse.urlencode(params) if params else "/contracts",
        })
    return render_template("searches.html", searches=searches_list, count=len(searches_list))


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
