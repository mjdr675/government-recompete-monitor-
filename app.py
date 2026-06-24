import csv
import io
import json
import logging
import re
import urllib.parse
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

import payments
import sentry_sdk
import stripe
from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename

from auth import bp as auth_bp
from access import get_access_state, is_access_granted
from access_observability import log_access_decision
from email_service import send_email
from change_detector import detect_changes
from update_detector import detect_field_changes
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db import (
    connect,
    get_company_profile,
    get_contracts,
    get_engine,
    init_db,
    list_saved_searches,
    list_contract_states,
    save_company_profile,
    save_demo_request,
    save_early_access,
    save_snapshot,
    upsert_contract,
    ALL_CATEGORIES,
    PIPELINE_STAGES,
    PIPELINE_TERMINAL_STAGES,
    add_opportunity,
    remove_opportunity,
    get_opportunity,
    get_opportunity_by_contract,
    list_opportunities,
    update_opportunity,
    get_notification_preferences,
    update_notification_preferences,
    infer_category,
    extract_raw_field,
    parse_nl_query,
    get_recent_updates_for_user,
    get_workspace_for_user,
    get_or_create_workspace_for_user,
    update_workspace,
    get_workspace_billing,
    update_workspace_subscription_status,
    is_workspace_active,
    list_workspace_members,
    VALID_PLANS,
    record_workspace_billing_event,
    is_workspace_in_trial,
    get_workspace_by_stripe_customer,
    find_contract_by_award_id,
    submit_feedback,
    get_feedback_submissions,
)
from analytics import vendor_profile_analytics as vendor_profile_query
from analytics import agency_profile as agency_profile_query
from analytics import dashboard_analytics, opportunity_recommendations, dashboard_recommended_actions, business_opportunities
from analytics import suggested_matches as get_suggested_matches, my_contracts_summary, personalized_for_business, my_current_contracts, my_current_contract_summary
from business_match import (
    business_match_score,
    business_match_reasons,
    business_mismatch_reasons,
    profile_completeness,
    profile_completion_hints,
    profile_filter_for_sql,
)
from report_builder import build_report
from views import SAVED_VIEWS, build_view_query, format_filter_summary, active_filter_chips, quick_views, active_view_id
from apply_window import apply_stage, is_applyable, in_sweet_spot, MIN_APPLY_DAYS, MAX_PREP_DAYS
import hubspot_service
from users import (
    get_user_by_email,
    get_user_by_stripe_customer,
    set_subscription,
    update_company_name,
    update_password,
    verify_password,
)

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_json_logging() -> None:
    formatter = _JsonFormatter()
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))
    for handler in root.handlers:
        handler.setFormatter(formatter)


_configure_json_logging()

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
UNIFIED_ACCESS_ENABLED = os.getenv("UNIFIED_ACCESS_ENABLED", "").lower() in ("1", "true", "yes")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_PRICE_ID_YEARLY = os.getenv("STRIPE_PRICE_ID_YEARLY")
STRIPE_PRICE_IDS = {
    "basic":      os.getenv("STRIPE_PRICE_ID_BASIC", ""),
    "pro":        os.getenv("STRIPE_PRICE_ID_PRO", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ID_ENTERPRISE", ""),
    # Legacy aliases kept so existing webhook events referencing old plan names still resolve.
    "starter": os.getenv("STRIPE_PRICE_ID_STARTER", ""),
    "growth":  os.getenv("STRIPE_PRICE_ID_GROWTH", ""),
}
STRIPE_PRICE_IDS_YEARLY = {
    "basic":      os.getenv("STRIPE_PRICE_ID_BASIC_YEARLY", ""),
    "pro":        os.getenv("STRIPE_PRICE_ID_PRO_YEARLY", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ID_ENTERPRISE_YEARLY", ""),
}

# Canonical plan definitions used by the billing UI and checkout logic.
# UI lane reads this to render pricing cards; Platform owns the truth here.
PLAN_CATALOG = {
    "basic": {
        "name": "Basic",
        "max_seats": 1,
        "price_monthly": 49,
        "price_yearly": 470,   # ~20 % discount vs monthly
        "features": [
            "Contract monitoring",
            "Watchlist up to 25 contracts",
            "Email alerts",
        ],
    },
    "pro": {
        "name": "Pro",
        "max_seats": 1,
        "price_monthly": 99,
        "price_yearly": 950,
        "features": [
            "Everything in Basic",
            "Unlimited watchlist",
            "Pipeline & opportunity tracking",
            "AI contract summaries",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "max_seats": 5,
        "price_monthly": 299,
        "price_yearly": 2870,
        "features": [
            "Everything in Pro",
            "Up to 5 team members",
            "Priority support",
            "Custom onboarding",
        ],
    },
}
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB
WORKSPACE_LOGO_DIR = os.path.join(app.static_folder, "uploads", "logos")
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])
app.register_blueprint(auth_bp)


@app.after_request
def _set_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not response.headers.get("Content-Security-Policy"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://js.stripe.com; "
            "frame-src https://js.stripe.com https://hooks.stripe.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://api.stripe.com;"
        )
    return response
app.view_functions["auth.login"] = limiter.limit(
    "5 per minute", per_method=True, methods=["POST"]
)(app.view_functions["auth.login"])
app.view_functions["auth.register"] = limiter.limit(
    "10 per hour", per_method=True, methods=["POST"]
)(app.view_functions["auth.register"])
app.jinja_env.globals["format_filter_summary"] = format_filter_summary
app.jinja_env.globals["apply_stage"] = apply_stage
app.jinja_env.globals["is_applyable"] = is_applyable

init_db()

# ---------------------------------------------------------------------------
# Daily ingest scheduler — local dev fallback only.
#
# In production (Railway) the canonical schedule is the Railway cron service
# defined in railway.toml, which POSTs to /ingest/run at 06:00 UTC.
# The thread below runs only in local dev so developers don't need a cron
# service to see ingest fire.  It is intentionally NOT started on Railway.
# ---------------------------------------------------------------------------

def _next_2am_utc(after: datetime) -> datetime:
    """Return the next 02:00 UTC datetime strictly after `after`."""
    candidate = after.replace(hour=2, minute=0, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


def _run_daily_ingest():
    _log = logging.getLogger("ingest.scheduler")
    _log.info("Daily ingest scheduler started (local-dev mode)")
    while True:
        now = datetime.now(timezone.utc)
        next_run = _next_2am_utc(now)
        sleep_secs = (next_run - now).total_seconds()
        _log.info("Next ingest scheduled in %.0f seconds (at %s UTC)", sleep_secs, next_run.isoformat())
        time.sleep(sleep_secs)
        try:
            _log.info("Starting scheduled ingest")
            from janitorial_recompete_report import main
            main()
            _log.info("Scheduled ingest completed successfully")
        except Exception as exc:
            _log.exception("Scheduled ingest failed: %s", exc)


# Start thread ONLY in local dev: not on Railway (Railway cron handles it),
# and not in the werkzeug reloader child process (would cause two threads).
_ON_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
if not _ON_RAILWAY and not os.environ.get("WERKZEUG_RUN_MAIN"):
    _scheduler_thread = threading.Thread(target=_run_daily_ingest, daemon=True, name="ingest-scheduler")
    _scheduler_thread.start()

# ---------------------------------------------------------------------------
# Ingest overlap prevention — one ingest at a time across all callers.
# ---------------------------------------------------------------------------
import threading as _threading
_ingest_lock = _threading.Lock()
_ingest_running = False

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


def _format_freshness_display(ts_str: str) -> str:
    """Return a human-readable freshness string for a UTC ISO timestamp.

    'Updated today at 3:04 AM' or 'Last updated Jun 24, 2026 at 3:04 AM'.
    Returns None on parse error so callers can fall back gracefully.
    """
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hour = ts.hour % 12 or 12
        minute = ts.strftime("%M")
        ampm = "AM" if ts.hour < 12 else "PM"
        time_str = f"{hour}:{minute} {ampm}"
        if ts.date() == now.date():
            return f"Updated today at {time_str}"
        return f"Last updated {ts.strftime('%b %-d, %Y')} at {time_str}"
    except (ValueError, TypeError):
        return None


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
    if os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("RAILWAY_VOLUME_NAME"):
        logging.warning(
            "DATA LOSS RISK: Running on Railway with no persistent volume. "
            "contracts.db is on the ephemeral filesystem and will be wiped on "
            "every redeploy. Attach a Railway volume and point DB_PATH to it."
        )


_warn_if_ephemeral_db()

_CRON_SECRET = os.environ.get("CRON_SECRET", "")
if _ON_RAILWAY and not _CRON_SECRET:
    logging.warning(
        "SECURITY: CRON_SECRET is not set. POST /ingest/run is unprotected "
        "and can be triggered by anyone. Set CRON_SECRET in Railway environment variables."
    )
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not STRIPE_WEBHOOK_SECRET:
    logging.warning(
        "STRIPE_WEBHOOK_SECRET is not set. POST /stripe/webhook will return 400 "
        "for all requests. Set this env var in production."
    )

_PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/create-checkout-session",
    "/success",
    "/cancel",
    "/subscribe",
    "/demo",
    "/early-access",
    "/stripe/webhook",
    "/watchlist/add",
    "/watchlist/remove",
    "/watchlist/add-by-award-id",
    "/searches/save",
    "/api/data-freshness",
    "/ingest/run",
    "/feedback",
})


_SUBSCRIPTION_EXEMPT = frozenset({
    "/subscribe",
    "/billing/portal",
    "/settings/billing",
    "/logout",
    "/create-checkout-session",
    "/success",
    "/cancel",
    "/onboarding",
    "/onboarding/complete",
    "/onboarding/skip",
    "/onboarding/dismiss",
})


@app.before_request
def require_login():
    if request.path in _PUBLIC_PATHS:
        return None
    # Static assets and the favicon must never require auth, otherwise logged-out
    # visitors get unstyled public pages (no CSS/JS loads).
    if request.path.startswith("/static/") or request.path == "/favicon.ico":
        return None
    if request.method == "DELETE" and request.path.startswith("/searches/"):
        return None
    if request.method == "POST" and request.path.endswith("/note"):
        return None
    if request.path.startswith("/api/health/"):
        return None
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.path))
    if not UNIFIED_ACCESS_ENABLED and request.path not in _SUBSCRIPTION_EXEMPT:
        user = g.get("user")
        if user and user.get("subscription_status") != "active":
            trial_ends_at = user.get("trial_ends_at")
            if trial_ends_at:
                trial_end = datetime.fromisoformat(trial_ends_at)
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > trial_end:
                    log_access_decision(
                        user.get("id"), None, "expired",
                        "/subscribe?expired=1", "legacy", request.path,
                    )
                    return redirect(url_for("subscribe", expired="1"))


_WORKSPACE_GATED_PREFIXES = ("/dashboard", "/contracts", "/compare", "/pipeline")


@app.before_request
def require_active_workspace():
    if UNIFIED_ACCESS_ENABLED:
        return None
    if "user_id" not in session:
        return None
    path = request.path
    if not any(path == p or path.startswith(p + "/") for p in _WORKSPACE_GATED_PREFIXES):
        return None
    user = g.get("user")
    if not user:
        return None
    workspace = get_workspace_for_user(user["id"])
    if workspace and not is_workspace_active(workspace["id"]):
        label = get_access_state(user, get_workspace_billing(workspace["id"]))
        log_access_decision(
            user["id"], workspace["id"], label,
            "/settings/billing?expired=1", "legacy", request.path,
        )
        return redirect(url_for("settings_billing", expired="1"))


_ACCESS_REDIRECTS = {
    "billing_required": "/settings/billing",
    "expired": "/settings/billing?expired=1",
}


def get_access_redirect(state):
    return _ACCESS_REDIRECTS.get(state)


@app.before_request
def require_access():
    if not UNIFIED_ACCESS_ENABLED:
        return None
    if request.path in _PUBLIC_PATHS or request.path in _SUBSCRIPTION_EXEMPT:
        return None
    if request.path.startswith("/static/") or request.path == "/favicon.ico":
        return None
    if "user_id" not in session:
        return None
    user = g.get("user")
    if not user:
        return None
    workspace = get_workspace_for_user(user["id"])
    billing = get_workspace_billing(workspace["id"]) if workspace else None
    state = get_access_state(user, billing)
    target = get_access_redirect(state)
    log_access_decision(
        user["id"], workspace["id"] if workspace else None,
        state, target, "unified", request.path,
    )
    if target:
        return redirect(target)


@app.before_request
def observe_access_decision():
    if UNIFIED_ACCESS_ENABLED:
        return None
    if request.path in _PUBLIC_PATHS or request.path in _SUBSCRIPTION_EXEMPT:
        return None
    if "user_id" not in session:
        return None
    user = g.get("user")
    if not user:
        return None
    workspace = get_workspace_for_user(user["id"])
    billing = get_workspace_billing(workspace["id"]) if workspace else None
    state = get_access_state(user, billing)
    log_access_decision(
        user["id"], workspace["id"] if workspace else None,
        state, get_access_redirect(state), "shadow", request.path,
    )
    return None


@app.context_processor
def inject_workspace():
    user = g.get("user")
    if not user:
        return {"workspace": None}
    try:
        return {"workspace": get_workspace_for_user(user["id"])}
    except Exception:
        return {"workspace": None}


@app.context_processor
def inject_trial_info():
    user = g.get("user")
    if not user or user.get("subscription_status") == "active":
        return {"trial_days_remaining": None}
    trial_ends_at = user.get("trial_ends_at")
    if not trial_ends_at:
        return {"trial_days_remaining": None}
    try:
        trial_end = datetime.fromisoformat(trial_ends_at)
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        days = (trial_end - datetime.now(timezone.utc)).days
        return {"trial_days_remaining": max(0, days)}
    except (ValueError, TypeError):
        return {"trial_days_remaining": None}


@app.context_processor
def inject_company_name():
    """Expose company_name as a top-level template variable for branding."""
    user = g.get("user")
    return {"company_name": (user or {}).get("company_name") or ""}


@app.context_processor
def inject_plan_catalog():
    """Expose plan catalog and current workspace plan to all templates."""
    user = g.get("user")
    workspace_plan = None
    if user:
        try:
            ws = get_workspace_for_user(user["id"])
            if ws:
                billing = get_workspace_billing(ws["id"])
                workspace_plan = (billing or {}).get("plan")
        except Exception:
            pass
    return {"plan_catalog": PLAN_CATALOG, "workspace_plan": workspace_plan}


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/ingest/run", methods=["POST"])
def ingest_run():
    """Ingest trigger endpoint called daily by the Railway cron service.

    Protection:
      - Requires Authorization: Bearer <CRON_SECRET> when CRON_SECRET is set.
      - Returns 409 if an ingest is already running (overlap prevention).
      - Returns 200 with {"status": "already_ran"} if a successful ingest was
        recorded in ingest_log today (idempotent for Railway retry logic).
        Pass force=1 in the request body to override the idempotency check.
    """
    global _ingest_running

    if _CRON_SECRET:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {_CRON_SECRET}":
            return {"error": "unauthorized"}, 401

    # Overlap prevention: reject if another ingest is already in progress.
    with _ingest_lock:
        if _ingest_running:
            return {"status": "already_running"}, 409

    # Idempotency: if ingest already succeeded today, skip unless forced.
    force = (request.get_json(silent=True) or {}).get("force") or request.args.get("force")
    if not force:
        today = date.today().isoformat()
        engine = get_engine()
        with engine.connect() as conn:
            ran_today = conn.execute(
                text(
                    "SELECT 1 FROM ingest_log WHERE run_date = :d AND status = 'success' LIMIT 1"
                ),
                {"d": today},
            ).fetchone()
        if ran_today:
            return {"status": "already_ran", "date": today}, 200

    def _run():
        global _ingest_running
        with _ingest_lock:
            _ingest_running = True
        try:
            from janitorial_recompete_report import main
            main()
        except Exception as exc:
            logging.getLogger("ingest").exception("Manual ingest failed: %s", exc)
        finally:
            with _ingest_lock:
                _ingest_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "date": date.today().isoformat()}, 202


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/dashboard")
def dashboard():
    try:
        user_id = g.user["id"] if g.user else None
        profile = get_company_profile(user_id) if user_id else None

        if user_id and not profile and not session.get("onboarding_skipped"):
            return redirect(url_for("onboarding"))

        analytics = dashboard_analytics()
        recommendations = opportunity_recommendations()
        engine = get_engine()
        last_ingest = None
        hours_ago = None
        last_ingest_display = None
        last_failure_display = None
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT created_at FROM ingest_log"
                    " WHERE status = 'success' ORDER BY created_at DESC LIMIT 1"
                )
            ).fetchone()
            fail_row = conn.execute(
                text(
                    "SELECT created_at FROM ingest_log"
                    " WHERE status = 'failure' ORDER BY created_at DESC LIMIT 1"
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
            last_ingest_display = _format_freshness_display(last_ingest)
        if fail_row:
            fail_ts = fail_row[0]
            # Only surface the failure if it is more recent than the last success
            # (a success after a failure means the pipeline recovered).
            if not last_ingest or fail_ts > last_ingest:
                last_failure_display = _format_freshness_display(fail_ts)
        show_onboarding = (
            g.get("watchlist_count", 0) == 0
            and not session.get("onboarding_dismissed")
        )
        dash_actions = dashboard_recommended_actions(user_id)
        has_profile = bool(profile)
        biz_opps = business_opportunities(user_id)
        my_contracts = my_contracts_summary(user_id)
        current_contracts = my_current_contracts(user_id)
        contract_summary = my_current_contract_summary(user_id)
        suggested = get_suggested_matches(user_id)
        for_business = personalized_for_business(user_id, profile) if profile else []
        p_completion = profile_completeness(profile) if profile else 0
        p_hints = profile_completion_hints(profile) if profile and p_completion < 100 else []

        pipeline_summary = {"total": 0, "active": 0, "by_stage": {}, "top": []}
        if user_id:
            all_opps = list_opportunities(user_id)
            active_opps = [o for o in all_opps if o["stage"] not in PIPELINE_TERMINAL_STAGES]
            by_stage: dict = {}
            for o in all_opps:
                by_stage[o["stage"]] = by_stage.get(o["stage"], 0) + 1
            top_opps = sorted(
                active_opps,
                key=lambda o: (
                    o["next_action_due"] or "9999-99-99",
                    -(o["recompete_score"] or 0),
                    o["updated_at"] or "",
                ),
            )[:5]
            pipeline_summary = {
                "total": len(all_opps),
                "active": len(active_opps),
                "by_stage": by_stage,
                "top": top_opps,
            }

        recent_updates = []
        if user_id:
            from contract_summary import format_contract_update
            recent_updates = [
                format_contract_update(r)
                for r in get_recent_updates_for_user(user_id, limit=8)
            ]

        dash_saved_searches = _saved_searches_with_urls(user_id) if user_id else []
        alert_configured = bool(os.environ.get("ALERT_TO"))

        return render_template(
            "dashboard.html",
            report=build_report(date.today().isoformat()),
            analytics=analytics,
            recommendations=recommendations,
            dash_actions=dash_actions,
            biz_opps=biz_opps,
            my_contracts=my_contracts,
            current_contracts=current_contracts,
            contract_summary=contract_summary,
            suggested_matches=suggested,
            for_business=for_business,
            recent_updates=recent_updates,
            company_name=profile.get("company_name") if profile else None,
            vendor_name=profile.get("vendor_name") if profile else None,
            uei=profile.get("uei") if profile else None,
            cage_code=profile.get("cage_code") if profile else None,
            has_profile=has_profile,
            profile_completion=p_completion,
            profile_hints=p_hints,
            last_ingest=last_ingest,
            hours_ago=hours_ago,
            last_ingest_display=last_ingest_display,
            last_failure_display=last_failure_display,
            show_onboarding=show_onboarding,
            pipeline_summary=pipeline_summary,
            pipeline_stages=PIPELINE_STAGES,
            saved_searches=dash_saved_searches,
            alert_configured=alert_configured,
        )

    except Exception:
        import traceback
        print(traceback.format_exc())
        return "Dashboard error", 500


@app.route("/onboarding/dismiss", methods=["POST"])
def onboarding_dismiss():
    session["onboarding_dismissed"] = "1"
    return redirect(url_for("dashboard"))


@app.route("/onboarding/skip")
def onboarding_skip():
    session["onboarding_skipped"] = "1"
    return redirect(url_for("dashboard"))


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if not g.user:
        return redirect(url_for("auth.login", next="/onboarding"))
    user_id = g.user["id"]

    if request.method == "POST":
        posted_step = request.form.get("step", "1")

        if posted_step == "1":
            raw_naics = request.form.get("naics_codes", "")
            _raw_codes = [
                c.strip()
                for line in raw_naics.splitlines()
                for c in line.split(",")
                if c.strip()
            ]
            naics_codes = [c for c in _raw_codes if re.fullmatch(r"\d{2,6}", c)]
            session["ob"] = {
                **session.get("ob", {}),
                "company_name": request.form.get("company_name", "").strip(),
                "vendor_name": request.form.get("vendor_name", "").strip(),
                "naics_codes": naics_codes,
            }
            session.modified = True
            return redirect(url_for("onboarding", step=2))

        if posted_step == "2":
            geo_coverage = request.form.get("geo_coverage", "nationwide")
            if geo_coverage not in ("nationwide", "states"):
                geo_coverage = "nationwide"
            states = [s for s in request.form.getlist("states") if s in _VALID_STATE_CODES]
            session["ob"] = {
                **session.get("ob", {}),
                "geo_coverage": geo_coverage,
                "states": states if geo_coverage == "states" else [],
            }
            session.modified = True
            return redirect(url_for("onboarding", step=3))

        if posted_step == "3":
            engine = get_engine()
            with engine.connect() as conn:
                agency_rows = conn.execute(
                    text(
                        "SELECT DISTINCT agency FROM contracts"
                        " WHERE agency IS NOT NULL AND agency != '' ORDER BY agency"
                    )
                ).fetchall()
            all_agencies_set = frozenset(r[0] for r in agency_rows)

            min_val = request.form.get("min_contract_value", "").strip()
            max_val = request.form.get("max_contract_value", "").strip()
            try:
                min_v = float(min_val) if min_val else None
            except ValueError:
                min_v = None
            try:
                max_v = float(max_val) if max_val else None
            except ValueError:
                max_v = None

            agencies = [a for a in request.form.getlist("agencies") if a in all_agencies_set]
            set_asides = [s for s in request.form.getlist("set_asides") if s in _VALID_SET_ASIDES]

            ob = session.pop("ob", {})
            save_company_profile(user_id, {
                "company_name": ob.get("company_name", ""),
                "vendor_name": ob.get("vendor_name", ""),
                "website": "",
                "geo_coverage": ob.get("geo_coverage", "nationwide"),
                "min_contract_value": min_v,
                "max_contract_value": max_v,
                "naics_codes": ob.get("naics_codes", []),
                "states": ob.get("states", []),
                "agencies": agencies,
                "set_asides": set_asides,
            })
            session.modified = True
            return redirect(url_for("onboarding_complete"))

        return redirect(url_for("onboarding"))

    step = request.args.get("step", "1")
    if step not in ("1", "2", "3"):
        step = "1"
    step = int(step)

    ob = session.get("ob", {})
    all_agencies = []
    if step == 3:
        engine = get_engine()
        with engine.connect() as conn:
            agency_rows = conn.execute(
                text(
                    "SELECT DISTINCT agency FROM contracts"
                    " WHERE agency IS NOT NULL AND agency != '' ORDER BY agency"
                )
            ).fetchall()
        all_agencies = [r[0] for r in agency_rows]

    return render_template(
        "onboarding.html",
        step=step,
        ob=ob,
        all_agencies=all_agencies,
        us_states=_US_STATES,
        set_aside_options=_SET_ASIDE_OPTIONS,
    )


@app.route("/onboarding/complete")
def onboarding_complete():
    if not g.user:
        return redirect(url_for("auth.login"))
    user_id = g.user["id"]
    profile = get_company_profile(user_id)
    opps = business_opportunities(user_id)
    return render_template("onboarding_complete.html", profile=profile, opps=opps)


@app.route("/contracts")
def contracts():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    category = request.args.get("category", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", type=float)
    status = request.args.get("status", "")
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")
    page = int(request.args.get("page", 1))
    state = request.args.get("state", "")
    category = request.args.get("category", "")
    discover = request.args.get("discover", "")
    # Apply-window filter: default ON. Only show contracts a small business can
    # realistically still bid on (enough runway, not already closed/too far out).
    # Pass applyable=0 in the query string to see everything. The filtering is
    # done in SQL (get_contracts applyable=...) so pagination stays cheap.
    applyable = request.args.get("applyable", "1") != "0"

    if status not in ("", "open", "expired"):
        status = ""

    # Natural-language query parsing: extract category/state intent from free text
    # so "lawn care contracts in Virginia" routes correctly without exact wording.
    # Only applied when the user hasn't already set those filters explicitly.
    if q:
        parsed = parse_nl_query(q)
        if not category and parsed.get("category"):
            category = parsed["category"]
        if not state and parsed.get("state"):
            state = parsed["state"]
        if parsed.get("category") or parsed.get("state"):
            q = parsed.get("q_remainder", q)

    days_int = int(days) if days else None
    if days_int is not None and days_int < 0:
        return "days parameter must be a non-negative integer", 400

    if min_value is not None and min_value < 0:
        return "min_value must be a non-negative number", 400

    for_my_business = request.args.get("for_my_business", "")
    in_pipeline = request.args.get("in_pipeline", "")
    profile = None
    pf = None
    if for_my_business and g.user:
        profile = get_company_profile(g.user["id"])
        if profile:
            pf = profile_filter_for_sql(profile)

    pipeline_map: dict = {}
    if g.user:
        for opp in list_opportunities(g.user["id"]):
            pipeline_map[opp["internal_id"]] = opp["id"]

    discover_exclude_ids = None
    if discover and g.user and pipeline_map:
        discover_exclude_ids = list(pipeline_map.keys())
    elif discover:
        discover_exclude_ids = []

    pipeline_ids: list | None = None
    if in_pipeline and g.user and pipeline_map:
        pipeline_ids = list(pipeline_map.keys())
    elif in_pipeline and g.user:
        pipeline_ids = []

    engine = get_engine()
    all_states = list_contract_states(engine)

    if pipeline_ids is not None and len(pipeline_ids) == 0:
        result = {"contracts": [], "total": 0, "count": 0, "start": 0, "page": page}
    else:
        result = get_contracts(
            q=q,
            agency=agency,
            priority=priority,
            days=days_int,
            min_value=min_value,
            status=status,
            sort=sort,
            direction=direction,
            page=page,
            limit=25,
            profile_filter=pf,
            internal_ids=pipeline_ids,
            state=state,
            category=category,
            exclude_ids=discover_exclude_ids,
            applyable=applyable,
        )

    _total = result["total"]
    _page_size = 25
    _total_pages = max(1, (_total + _page_size - 1) // _page_size)

    watchlist_ids = set()
    saved_searches = []
    if g.user:
        with engine.connect() as conn:
            wl_rows = conn.execute(
                text("SELECT internal_id FROM user_watchlist WHERE user_id = :uid"),
                {"uid": g.user["id"]},
            ).fetchall()
        watchlist_ids = {r[0] for r in wl_rows}
        saved_searches = _saved_searches_with_urls(g.user["id"])

    with engine.connect() as conn:
        agency_rows = conn.execute(text(
            "SELECT DISTINCT agency FROM contracts WHERE agency IS NOT NULL AND agency != ''"
            " ORDER BY agency"
        )).fetchall()
    all_agencies = [r[0] for r in agency_rows]

    rows = result["contracts"]
    if pf and profile:
        rows_with_scores = []
        for r in rows:
            rd = dict(r)
            rd["match_score"] = business_match_score(rd, profile)
            rows_with_scores.append(rd)
        rows = rows_with_scores

    return render_template(
        "contracts.html",
        rows=rows,
        total=_total,
        total_pages=_total_pages,
        start=result["start"] + 1 if result["count"] else 0,
        end=result["start"] + result["count"],
        page=result["page"],
        has_prev=result["page"] > 1,
        has_next=result["start"] + result["count"] < _total,
        priorities=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        all_agencies=all_agencies,
        all_states=all_states,
        all_categories=ALL_CATEGORIES,
        q=q,
        agency=agency,
        category=category,
        priority=priority,
        days=days or "",
        min_value=min_value or "",
        status=status,
        sort=sort,
        direction=direction,
        state=state,
        discover=discover,
        applyable=applyable,
        watchlist_ids=watchlist_ids,
        pipeline_map=pipeline_map,
        saved_searches=saved_searches,
        filter_chips=active_filter_chips(request.args.to_dict()),
        quick_views=quick_views(),
        active_view=active_view_id(request.args.to_dict()),
        for_my_business=for_my_business,
        in_pipeline=in_pipeline,
        has_profile=profile is not None,
    )


@app.route("/contracts/export.csv")
def contracts_export():
    q = request.args.get("q", "")
    agency = request.args.get("agency", "")
    priority = request.args.get("priority", "")
    days = request.args.get("days", None)
    min_value = request.args.get("min_value", type=float)
    status = request.args.get("status", "")
    if status not in ("", "open", "expired"):
        status = ""
    sort = request.args.get("sort", "recompete_score")
    direction = request.args.get("dir", "desc")

    days_int = int(days) if days else None
    result = get_contracts(
        q=q, agency=agency, priority=priority,
        days=days_int, min_value=min_value, status=status,
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
        checkout = payments.service.create_checkout_session(
            price_id=STRIPE_PRICE_ID,
            success_url=request.host_url.rstrip("/") + "/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + "/cancel",
        )
        return redirect(checkout.url, code=303)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return str(e), 500


@app.route("/success")
def success():
    session_id = request.args.get("session_id", "")
    if session_id:
        try:
            checkout = payments.service.retrieve_checkout_session(session_id)
            details = checkout.get("customer_details") or {}
            email = details.get("email") or ""
            name = details.get("name") or ""
            if email:
                hubspot_service.handle_stripe_checkout(
                    email=email, name=name, stripe_session_id=session_id
                )
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            logging.exception("Could not retrieve Stripe session %s", session_id)
    return "<h1>Payment successful</h1><p>Welcome to Recompete Beta.</p>"


@app.route("/cancel")
def cancel():
    return "<h1>Checkout canceled</h1><p>You were not charged.</p>"


@app.route("/subscribe")
def subscribe():
    expired = request.args.get("expired") == "1"
    return render_template("subscribe.html", expired=expired)


@app.route("/billing/portal", methods=["POST"])
def billing_portal():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        flash("No active subscription found.", "error")
        return redirect(url_for("dashboard"))
    try:
        portal = payments.service.create_billing_portal_session(
            customer_id=stripe_customer_id,
            return_url=request.host_url.rstrip("/") + "/",
        )
        return redirect(portal.url, code=303)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logging.exception("Billing portal error: %s", exc)
        flash("Could not open billing portal. Please try again later.", "error")
        return redirect(url_for("dashboard"))


def _apply_workspace_billing_event(event):
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {}) or {}
    event_id = event.get("id")

    if etype == "checkout.session.completed":
        ref = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("workspace_id")
        if not ref:
            return
        try:
            workspace_id = int(ref)
        except (ValueError, TypeError):
            return
        plan = (obj.get("metadata") or {}).get("plan")
        update_workspace_subscription_status(
            workspace_id,
            "active",
            plan=plan if plan in VALID_PLANS else None,
            stripe_customer_id=obj.get("customer") or None,
            stripe_subscription_id=obj.get("subscription") or None,
        )
        record_workspace_billing_event(workspace_id, etype, event_id, json.dumps(obj, default=str))

    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer = obj.get("customer") or ""
        if not customer:
            return
        workspace = get_workspace_by_stripe_customer(customer)
        if not workspace:
            return
        if etype == "customer.subscription.deleted":
            status = "canceled"
        else:
            status = obj.get("status") or "active"
        update_workspace_subscription_status(
            workspace["id"],
            status,
            stripe_subscription_id=obj.get("id") or None,
        )
        record_workspace_billing_event(workspace["id"], etype, event_id, json.dumps(obj, default=str))


@app.route("/stripe/webhook", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        logging.warning("Stripe webhook received but STRIPE_WEBHOOK_SECRET is not configured")
        return "Webhook secret not configured", 400
    try:
        event = payments.service.construct_webhook_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        logging.warning("Webhook signature error: %s", e)
        return "Bad request", 400
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logging.exception("Unexpected error parsing webhook: %s", exc)
        return "Internal error", 500

    if event["type"] == "checkout.session.completed":
        checkout = event["data"]["object"]
        details = checkout.get("customer_details") or {}
        email = details.get("email") or checkout.get("customer_email") or ""
        name = details.get("name") or ""
        session_id = checkout.get("id") or ""
        stripe_customer_id = checkout.get("customer") or ""
        if email:
            hubspot_service.handle_stripe_checkout(
                email=email, name=name, stripe_session_id=session_id
            )
            user = get_user_by_email(email)
            if user and stripe_customer_id:
                set_subscription(user["id"], stripe_customer_id, "active")

    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        stripe_customer_id = sub.get("customer") or ""
        status = sub.get("status") or "active"
        if stripe_customer_id:
            user = get_user_by_stripe_customer(stripe_customer_id)
            if user:
                set_subscription(user["id"], stripe_customer_id, status)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        stripe_customer_id = sub.get("customer") or ""
        if stripe_customer_id:
            user = get_user_by_stripe_customer(stripe_customer_id)
            if user:
                set_subscription(user["id"], stripe_customer_id, "canceled")

    try:
        _apply_workspace_billing_event(event)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logging.exception("Workspace billing webhook update failed: %s", exc)

    return "", 200


@app.route("/demo", methods=["GET", "POST"])
@limiter.limit("5 per hour", per_method=True, methods=["POST"])
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
@limiter.limit("5 per hour", per_method=True, methods=["POST"])
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
                detect_field_changes(run_date)
                message = f"Imported {len(rows)} contracts from CSV."

        elif action == "api":
            from tasks import run_ingest
            job = run_ingest.delay()
            return jsonify({"status": "started", "task_id": job.id})

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
        sentry_sdk.capture_exception(exc)
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
            sentry_sdk.capture_exception(exc)
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

    from contract_summary import next_step, recommended_action, why_it_matters, contract_timeline, recompete_score_breakdown
    guidance = next_step(row.get("days_remaining"), row.get("priority"))
    action = recommended_action(row)
    matters = why_it_matters(row)
    timeline = contract_timeline(row)
    score_breakdown = recompete_score_breakdown(row)

    # Apply-window staging for the "How to apply" CTA on the detail page.
    stage_key, stage_label, stage_detail = apply_stage(row.get("days_remaining"))
    applyable = is_applyable(row.get("days_remaining"))

    biz_match_score = None
    biz_match_reasons_list = []
    biz_mismatch_reasons_list = []
    pipeline_opp = None
    if g.user:
        biz_profile = get_company_profile(g.user["id"])
        if biz_profile:
            biz_match_score = business_match_score(row, biz_profile)
            biz_match_reasons_list = business_match_reasons(row, biz_profile)
            biz_mismatch_reasons_list = business_mismatch_reasons(row, biz_profile)
        pipeline_opp = get_opportunity_by_contract(g.user["id"], internal_id)

    category = infer_category(
        description=row.get("description") or "",
        naics_code=extract_raw_field(row, "sam_naics") or extract_raw_field(row, "naics_code") or "",
        vendor=row.get("vendor") or "",
    )
    performance_state = (
        row.get("place_of_performance_state")
        or extract_raw_field(row, "performance_state")
        or extract_raw_field(row, "recipient_state")
        or ""
    )
    performance_city = extract_raw_field(row, "performance_city") or ""
    psc_description = extract_raw_field(row, "psc_description") or ""

    return render_template("contract_detail.html", row=row, is_bookmarked=is_bookmarked,
                           notes=notes, next_step=guidance, action=action,
                           why_matters=matters, timeline=timeline,
                           biz_match_score=biz_match_score,
                           biz_match_reasons=biz_match_reasons_list,
                           biz_mismatch_reasons=biz_mismatch_reasons_list,
                           pipeline_opp=pipeline_opp,
                           category=category,
                           performance_state=performance_state,
                           performance_city=performance_city,
                           psc_description=psc_description,
                           stage_key=stage_key,
                           stage_label=stage_label,
                           stage_detail=stage_detail,
                           applyable=applyable,
                           score_breakdown=score_breakdown)


@app.route("/contract/<internal_id>/apply")
def contract_apply(internal_id):
    con = connect()
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    row = con.execute(
        "SELECT * FROM contracts WHERE internal_id=?",
        (internal_id,),
    ).fetchone()
    con.close()

    if not row:
        return redirect("/contracts")

    stage_key, stage_label, stage_detail = apply_stage(row.get("days_remaining"))
    applyable = is_applyable(row.get("days_remaining"))

    # Build a SAM.gov search URL seeded with the incumbent solicitation number
    # (if known) or the agency/work description so the user can find the live notice.
    solicitation_id = row.get("solicitation_id") or extract_raw_field(row, "solicitation_id") or ""
    sam_naics = extract_raw_field(row, "sam_naics") or extract_raw_field(row, "naics_code") or row.get("naics_code") or ""
    if solicitation_id:
        sam_search_url = "https://sam.gov/search/?keywords=" + urllib.parse.quote(str(solicitation_id))
    else:
        terms = " ".join(filter(None, [row.get("agency") or "", row.get("description") or ""]))[:120]
        sam_search_url = "https://sam.gov/search/?keywords=" + urllib.parse.quote(terms)

    category = infer_category(
        description=row.get("description") or "",
        naics_code=sam_naics,
        vendor=row.get("vendor") or "",
    )
    performance_state = (
        row.get("place_of_performance_state")
        or extract_raw_field(row, "performance_state")
        or extract_raw_field(row, "recipient_state")
        or ""
    )

    return render_template(
        "contract_apply.html",
        row=row,
        stage_key=stage_key,
        stage_label=stage_label,
        stage_detail=stage_detail,
        applyable=applyable,
        sam_search_url=sam_search_url,
        sam_naics=sam_naics,
        solicitation_id=solicitation_id,
        category=category,
        performance_state=performance_state,
    )


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


@app.route("/watchlist/add-by-award-id", methods=["POST"])
@csrf.exempt
def watchlist_add_by_award_id():
    """Add a contract to the watchlist by user-facing award_id / PIID.

    Accepts JSON {"award_id": "..."} or form field award_id.
    Looks up the internal_id in the contracts table, then delegates to the
    same user_watchlist insert used by watchlist_add.
    """
    if not g.user:
        return jsonify({"error": "login required"}), 401
    payload = request.get_json(silent=True) or {}
    award_id = (payload.get("award_id") or request.form.get("award_id", "")).strip()
    if not award_id:
        return jsonify({"ok": False, "error": "award_id required"}), 400
    contract = find_contract_by_award_id(award_id)
    if not contract:
        return jsonify({"ok": False, "error": "contract not found", "award_id": award_id}), 404
    internal_id = contract["internal_id"]
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO user_watchlist (user_id, internal_id, added_at) VALUES (:uid, :iid, :ts)"),
                {"uid": g.user["id"], "iid": internal_id, "ts": now},
            )
        return jsonify({"ok": True, "internal_id": internal_id, "vendor": contract.get("vendor")})
    except IntegrityError:
        return jsonify({"ok": True, "already": True, "internal_id": internal_id})


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    """Contact / Help / Feedback form.

    GET  → renders the feedback form (template owned by UI lane).
    POST → stores submission to DB; returns JSON for AJAX or redirects for form POST.
    Accessible without login; authenticated users get email pre-filled.
    """
    user = g.get("user")
    if request.method == "GET":
        return render_template(
            "feedback.html",
            prefill_email=(user or {}).get("email", ""),
        )
    subject = request.form.get("subject", "").strip() or (request.get_json(silent=True) or {}).get("subject", "").strip()
    body = request.form.get("body", "").strip() or (request.get_json(silent=True) or {}).get("body", "").strip()
    email = (request.form.get("email", "") or (request.get_json(silent=True) or {}).get("email", "")).strip()
    if not user:
        email = email
    else:
        email = email or user["email"]
    if not subject or not body:
        if request.is_json:
            return jsonify({"ok": False, "error": "subject and body required"}), 400
        flash("Please fill in both subject and message.", "error")
        return redirect(url_for("feedback"))
    submit_feedback(
        subject=subject,
        body=body,
        user_id=user["id"] if user else None,
        email=email or None,
    )
    if request.is_json:
        return jsonify({"ok": True})
    flash("Thanks — we'll be in touch soon.", "success")
    return redirect(url_for("feedback"))


@app.route("/admin/feedback")
def admin_feedback():
    """Admin-only view of feedback submissions."""
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    admin_emails = {e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    if admin_emails and user["email"] not in admin_emails:
        return "Forbidden", 403
    status_filter = request.args.get("status")
    submissions = get_feedback_submissions(status=status_filter or None)
    return render_template("admin_feedback.html", submissions=submissions, status_filter=status_filter)


def _safe_redirect(fallback="/pipeline"):
    ref = request.referrer or ""
    if ref.startswith(request.host_url):
        return ref
    return fallback


@app.route("/pipeline")
def pipeline():
    stage_filter = request.args.get("stage", "").strip().lower() or None
    try:
        opps = list_opportunities(g.user["id"], stage=stage_filter)
    except ValueError:
        stage_filter = None
        opps = list_opportunities(g.user["id"])
    stage_labels = dict(PIPELINE_STAGES)
    return render_template("pipeline.html", opportunities=opps,
                           stage_labels=stage_labels, pipeline_stages=PIPELINE_STAGES,
                           count=len(opps), current_stage=stage_filter)


@app.route("/pipeline/<int:opp_id>")
def opportunity_detail(opp_id):
    opp = get_opportunity(g.user["id"], opp_id)
    if not opp:
        return redirect("/pipeline")

    con = connect()
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    contract = con.execute(
        "SELECT * FROM contracts WHERE internal_id=?", (opp["internal_id"],)
    ).fetchone()
    con.close()

    biz_match_score = None
    biz_match_reasons_list = []
    biz_mismatch_reasons_list = []
    biz_profile = get_company_profile(g.user["id"])
    if biz_profile and contract:
        biz_match_score = business_match_score(contract, biz_profile)
        biz_match_reasons_list = business_match_reasons(contract, biz_profile)
        biz_mismatch_reasons_list = business_mismatch_reasons(contract, biz_profile)

    return render_template(
        "opportunity_detail.html",
        opp=opp,
        contract=contract,
        pipeline_stages=PIPELINE_STAGES,
        biz_match_score=biz_match_score,
        biz_match_reasons=biz_match_reasons_list,
        biz_mismatch_reasons=biz_mismatch_reasons_list,
        has_profile=biz_profile is not None,
    )


@app.route("/pipeline/<int:opp_id>/status", methods=["POST"])
def pipeline_status(opp_id):
    opp = get_opportunity(g.user["id"], opp_id)
    if not opp:
        flash("Opportunity not found.", "error")
        return redirect("/pipeline")
    stage = request.form.get("stage", "").strip()
    try:
        update_opportunity(g.user["id"], opp_id, {"stage": stage})
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(f"/pipeline/{opp_id}")
    return redirect(_safe_redirect("/pipeline"))


@app.route("/pipeline/add/<internal_id>", methods=["POST"])
def pipeline_add(internal_id):
    _opp_id, created = add_opportunity(g.user["id"], internal_id)
    flash("Added to your pipeline." if created else "Already in your pipeline.", "success")
    return redirect(_safe_redirect(f"/contract/{internal_id}"))


@app.route("/pipeline/remove/<internal_id>", methods=["POST"])
def pipeline_remove(internal_id):
    remove_opportunity(g.user["id"], internal_id)
    flash("Removed from your pipeline.", "success")
    return redirect(_safe_redirect())


@app.route("/pipeline/update/<int:opp_id>", methods=["POST"])
def pipeline_update(opp_id):
    opp = get_opportunity(g.user["id"], opp_id)
    if not opp:
        flash("Opportunity not found.", "error")
        return redirect("/pipeline")
    data = {k: request.form.get(k, "") for k in
            ("stage", "notes", "next_action", "next_action_due", "probability")}
    try:
        update_opportunity(g.user["id"], opp_id, data)
        flash("Pipeline updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(_safe_redirect("/pipeline"))


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


@app.route("/api/health/detailed")
def health_detailed():
    if not g.user:
        return jsonify({"error": "unauthorized"}), 401

    import redis as _redis
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    db_status = "ok"
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        db_status = "error"

    redis_status = "ok"
    try:
        _redis.from_url(redis_url, socket_connect_timeout=2).ping()
    except Exception:
        redis_status = "error"

    last_ingest_at = None
    last_ingest_records = None
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT created_at, record_count FROM ingest_log"
                    " WHERE status = 'success' ORDER BY created_at DESC LIMIT 1"
                )
            ).fetchone()
        if row:
            last_ingest_at = row[0]
            last_ingest_records = row[1]
    except Exception:
        pass

    healthy = db_status == "ok" and redis_status == "ok"
    return jsonify({
        "db": db_status,
        "redis": redis_status,
        "last_ingest_at": last_ingest_at,
        "last_ingest_records": last_ingest_records,
        "ok": healthy,
    }), (200 if healthy else 503)


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


_SET_ASIDE_OPTIONS = [
    ("small_business", "Small Business"),
    ("8a", "8(a)"),
    ("hubzone", "HUBZone"),
    ("wosb", "WOSB — Women-Owned Small Business"),
    ("sdvosb", "SDVOSB — Service-Disabled Veteran-Owned"),
    ("full_open", "Full & Open Competition"),
]

_US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DC", "District of Columbia"),
    ("DE", "Delaware"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"),
    ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
    ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
    ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

_VALID_SET_ASIDES = frozenset(v for v, _ in _SET_ASIDE_OPTIONS)
_VALID_STATE_CODES = frozenset(code for code, _ in _US_STATES)


@app.route("/company-profile", methods=["GET", "POST"])
def company_profile_page():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login", next="/company-profile"))

    engine = get_engine()
    with engine.connect() as conn:
        agency_rows = conn.execute(text(
            "SELECT DISTINCT agency FROM contracts"
            " WHERE agency IS NOT NULL AND agency != '' ORDER BY agency"
        )).fetchall()
    all_agencies = [r[0] for r in agency_rows]

    error = None
    success = None

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        vendor_name = request.form.get("vendor_name", "").strip()
        uei = request.form.get("uei", "").strip()
        cage_code = request.form.get("cage_code", "").strip()
        website = request.form.get("website", "").strip()
        geo_coverage = request.form.get("geo_coverage", "nationwide")
        if geo_coverage not in ("nationwide", "states"):
            geo_coverage = "nationwide"

        raw_naics = request.form.get("naics_codes", "")
        _raw_codes = [
            c.strip()
            for line in raw_naics.splitlines()
            for c in line.split(",")
            if c.strip()
        ]
        naics_codes = [c for c in _raw_codes if re.fullmatch(r"\d{2,6}", c)]

        states = [s for s in request.form.getlist("states") if s in _VALID_STATE_CODES]
        agencies = [a for a in request.form.getlist("agencies") if a in frozenset(all_agencies)]
        set_asides = [s for s in request.form.getlist("set_asides") if s in _VALID_SET_ASIDES]
        keywords_raw = request.form.get("keywords", "")
        keywords = [
            k for part in keywords_raw.replace(",", "\n").splitlines()
            for k in [part.strip()] if k
        ]

        min_val = request.form.get("min_contract_value", "").strip()
        max_val = request.form.get("max_contract_value", "").strip()

        try:
            min_v = float(min_val) if min_val else None
        except ValueError:
            min_v = None
            error = "Minimum contract value must be a number."
        try:
            max_v = float(max_val) if max_val else None
        except ValueError:
            max_v = None
            if not error:
                error = "Maximum contract value must be a number."

        if not error and min_v is not None and max_v is not None and min_v > max_v:
            error = "Minimum contract value cannot exceed maximum."

        if not error:
            save_company_profile(user["id"], {
                "company_name": company_name,
                "vendor_name": vendor_name,
                "uei": uei,
                "cage_code": cage_code,
                "website": website,
                "geo_coverage": geo_coverage,
                "min_contract_value": min_v,
                "max_contract_value": max_v,
                "naics_codes": naics_codes,
                "states": states if geo_coverage == "states" else [],
                "agencies": agencies,
                "set_asides": set_asides,
                "keywords": keywords,
            })
            success = "Profile saved."

    profile = get_company_profile(user["id"])
    p_completion = profile_completeness(profile) if profile else 0

    return render_template(
        "company_profile.html",
        profile=profile,
        all_agencies=all_agencies,
        set_aside_options=_SET_ASIDE_OPTIONS,
        us_states=_US_STATES,
        error=error,
        success=success,
        profile_completion=p_completion,
    )


def _saved_searches_with_urls(user_id):
    items = list_saved_searches(user_id)
    for s in items:
        s["url"] = ("/contracts?" + urllib.parse.urlencode(s["params"])) if s["params"] else "/contracts"
    return items


@app.route("/searches")
def searches():
    searches_list = _saved_searches_with_urls(g.user["id"])
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

    _SLOTS = ["a", "b", "c", "d", "e"]
    raw_ids = [request.args.get(s, "").strip() for s in _SLOTS]
    while raw_ids and not raw_ids[-1]:
        raw_ids.pop()
    while len(raw_ids) < 2:
        raw_ids.append("")

    contracts = [(_fetch(rid) if rid else None, rid) for rid in raw_ids]

    id_a = raw_ids[0] if raw_ids else ""
    id_b = raw_ids[1] if len(raw_ids) > 1 else ""
    a = contracts[0][0] if contracts else None
    b = contracts[1][0] if len(contracts) > 1 else None

    from contract_summary import compare_insights
    found_rows = [c[0] for c in contracts if c[0]]
    compare_insight = compare_insights(found_rows)

    return render_template(
        "compare.html",
        contracts=contracts,
        raw_ids=raw_ids,
        slots=_SLOTS,
        compare_insight=compare_insight,
        a=a, b=b, id_a=id_a, id_b=id_b,
    )


@app.route("/settings/account", methods=["GET", "POST"])
def settings_account():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    error = None
    success = None
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")
        if not verify_password(user["email"], current_pw):
            error = "Current password is incorrect."
        elif len(new_pw) < 8:
            error = "New password must be at least 8 characters."
        elif new_pw != confirm_pw:
            error = "New passwords do not match."
        else:
            update_password(user["id"], new_pw)
            success = "Password updated successfully."
    return render_template("settings_account.html", user=user, error=error, success=success)


@app.route("/settings/account/company", methods=["POST"])
def settings_account_company():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    company_name = request.form.get("company_name", "").strip()
    update_company_name(user["id"], company_name)
    flash("Company name updated.")
    return redirect(url_for("settings_account"))


def _save_workspace_logo(workspace_id, file_storage):
    filename = (file_storage.filename or "").strip()
    if not filename:
        return None, "No file selected."
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        return None, "Logo must be a PNG, JPG, GIF, WEBP, or SVG image."
    os.makedirs(WORKSPACE_LOGO_DIR, exist_ok=True)
    stored_name = secure_filename(f"workspace_{workspace_id}.{ext}")
    abs_path = os.path.join(WORKSPACE_LOGO_DIR, stored_name)
    file_storage.save(abs_path)
    if os.path.getsize(abs_path) == 0:
        os.remove(abs_path)
        return None, "Uploaded file was empty."
    return f"uploads/logos/{stored_name}", None


@app.route("/settings/workspace", methods=["GET", "POST"])
def settings_workspace():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    workspace = get_or_create_workspace_for_user(user["id"])
    error = None
    success = None
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "remove_logo":
            update_workspace(workspace["id"], logo_path="")
            flash("Logo removed.")
            return redirect(url_for("settings_workspace"))

        name = request.form.get("workspace_name", "").strip()
        logo_path = None
        upload = request.files.get("logo")
        if upload and (upload.filename or "").strip():
            logo_path, error = _save_workspace_logo(workspace["id"], upload)
        if not error:
            update_workspace(workspace["id"], name=name, logo_path=logo_path)
            success = "Workspace updated."
            workspace = get_workspace_for_user(user["id"])

    members = list_workspace_members(workspace["id"]) if workspace else []
    return render_template(
        "settings_workspace.html",
        user=user,
        workspace=workspace,
        members=members,
        error=error,
        success=success,
    )


def create_workspace_stripe_customer(workspace):
    billing = get_workspace_billing(workspace["id"])
    if billing and billing.get("stripe_customer_id"):
        return billing["stripe_customer_id"]
    customer = stripe.Customer.create(
        name=workspace.get("name") or f"Workspace {workspace['id']}",
        metadata={"workspace_id": str(workspace["id"])},
    )
    update_workspace_subscription_status(
        workspace["id"],
        billing.get("subscription_status") if billing else "trialing",
        stripe_customer_id=customer["id"],
    )
    return customer["id"]


def create_workspace_checkout_session(workspace, plan, billing_interval="monthly"):
    if billing_interval == "yearly":
        price_id = STRIPE_PRICE_IDS_YEARLY.get(plan) or STRIPE_PRICE_IDS.get(plan)
    else:
        price_id = STRIPE_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"No Stripe price configured for plan '{plan}' ({billing_interval})")
    customer_id = create_workspace_stripe_customer(workspace)
    return stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(workspace["id"]),
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"workspace_id": str(workspace["id"]), "plan": plan, "billing_interval": billing_interval},
        success_url=url_for("settings_billing", _external=True) + "?upgraded=1",
        cancel_url=url_for("settings_billing", _external=True),
    )


def create_workspace_billing_portal_session(workspace):
    billing = get_workspace_billing(workspace["id"])
    customer_id = billing.get("stripe_customer_id") if billing else None
    if not customer_id:
        return None
    return stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=url_for("settings_billing", _external=True),
    )


def _workspace_trial_days_remaining(billing):
    if not billing or not billing.get("trial_end_at"):
        return None
    try:
        trial_end = datetime.fromisoformat(billing["trial_end_at"])
    except (ValueError, TypeError):
        return None
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    delta = trial_end - datetime.now(timezone.utc)
    return max(0, delta.days + (1 if delta.seconds or delta.microseconds else 0))


@app.route("/settings/billing", methods=["GET", "POST"])
def settings_billing():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    workspace = get_or_create_workspace_for_user(user["id"])
    error = None

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "portal":
            try:
                portal = create_workspace_billing_portal_session(workspace)
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                portal = None
            if portal:
                return redirect(portal.url, code=303)
            error = "No billing account yet. Choose a plan to get started."
        elif action == "upgrade":
            plan = request.form.get("plan", "")
            billing_interval = request.form.get("billing_interval", "monthly")
            if billing_interval not in ("monthly", "yearly"):
                billing_interval = "monthly"
            if plan not in VALID_PLANS:
                error = "Unknown plan."
            else:
                try:
                    checkout = create_workspace_checkout_session(workspace, plan, billing_interval)
                    return redirect(checkout.url, code=303)
                except Exception as exc:
                    sentry_sdk.capture_exception(exc)
                    error = "Could not start checkout. Please try again."

    billing = get_workspace_billing(workspace["id"])
    return render_template(
        "settings_billing.html",
        user=user,
        workspace=workspace,
        billing=billing,
        plans=VALID_PLANS,
        plan_catalog=PLAN_CATALOG,
        in_trial=is_workspace_in_trial(workspace["id"]),
        trial_days_remaining=_workspace_trial_days_remaining(billing),
        active=is_workspace_active(workspace["id"]),
        expired=request.args.get("expired") == "1",
        upgraded=request.args.get("upgraded") == "1",
        error=error,
    )


@app.route("/settings/alerts", methods=["GET", "POST"])
def settings_alerts():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    engine = get_engine()
    if request.method == "POST":
        expiry_days = int(request.form.get("expiry_days") or 30)
        enabled = 1 if request.form.get("enabled") else 0
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(text("""
            INSERT INTO alert_preferences (user_id, expiry_days, enabled, updated_at)
            VALUES (:uid, :days, :enabled, :now)
            ON CONFLICT(user_id) DO UPDATE SET
                expiry_days = excluded.expiry_days,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """), {"uid": user["id"], "days": expiry_days, "enabled": enabled, "now": now})
        flash("Alert settings saved.", "success")
        return redirect(url_for("settings_alerts"))
    with engine.connect() as conn:
        prefs = conn.execute(text(
            "SELECT expiry_days, enabled FROM alert_preferences WHERE user_id = :uid"
        ), {"uid": user["id"]}).mappings().fetchone()
    defaults = {"expiry_days": 30, "enabled": 1}
    prefs = dict(prefs) if prefs else defaults
    return render_template("settings_alerts.html", prefs=prefs)


@app.route("/settings/notifications", methods=["GET", "POST"])
def settings_notifications():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        try:
            update_notification_preferences(
                user["id"],
                email_notifications_enabled=bool(request.form.get("email_notifications_enabled")),
                pipeline_digest_enabled=bool(request.form.get("pipeline_digest_enabled")),
                next_action_reminders_enabled=bool(request.form.get("next_action_reminders_enabled")),
                opportunity_alerts_enabled=bool(request.form.get("opportunity_alerts_enabled")),
                digest_frequency=request.form.get("digest_frequency", "weekly"),
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("settings_notifications"))
        flash("Notification settings saved.", "success")
        return redirect(url_for("settings_notifications"))
    prefs = get_notification_preferences(user["id"])
    return render_template("settings_notifications.html", prefs=prefs)


@app.route("/admin")
def admin_dashboard():
    admin_email = os.environ.get("ADMIN_EMAIL", "").lower()
    user = g.get("user")
    if not user or user.get("email", "").lower() != admin_email or not admin_email:
        return "Not found", 404
    engine = get_engine()
    with engine.connect() as conn:
        users_rows = conn.execute(text(
            "SELECT id, email, created_at, subscription_status, trial_ends_at, stripe_customer_id"
            " FROM users WHERE is_active = 1 ORDER BY created_at DESC LIMIT 200"
        )).mappings().fetchall()
        counts = conn.execute(text(
            "SELECT subscription_status, COUNT(*) as n FROM users"
            " WHERE is_active = 1 GROUP BY subscription_status"
        )).mappings().fetchall()
        total_users = conn.execute(text(
            "SELECT COUNT(*) FROM users WHERE is_active = 1"
        )).scalar() or 0
        active_count = sum(r["n"] for r in counts if r["subscription_status"] == "active")
    stats = {r["subscription_status"]: r["n"] for r in counts}
    mrr = active_count * 49
    return render_template(
        "admin.html",
        users=list(users_rows),
        stats=stats,
        total_users=total_users,
        active_count=active_count,
        mrr=mrr,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
