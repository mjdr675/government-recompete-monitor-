import functools
import logging
import os

from flask import (Blueprint, flash, g, redirect, render_template,
                   request, session, url_for)

from users import (clear_reset_token, create_user, get_user_by_id,
                   get_user_by_reset_token, set_reset_token, set_trial,
                   update_password, verify_password)

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

_PUBLIC_PATHS = frozenset({"/health", "/login", "/register"})


def login_required(f):
    """Decorator for routes that require an authenticated session."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


@bp.before_app_request
def load_logged_in_user() -> None:
    """Populate g.user for every request so templates can reference it."""
    from db import get_engine
    from sqlalchemy import text as sa_text
    user_id = session.get("user_id")
    g.user = get_user_by_id(user_id) if user_id else None
    if g.user:
        with get_engine().connect() as conn:
            row = conn.execute(
                sa_text("SELECT COUNT(*) FROM user_watchlist WHERE user_id = :uid"),
                {"uid": g.user["id"]},
            ).fetchone()
            g.watchlist_count = row[0] if row else 0
    else:
        g.watchlist_count = 0


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect("/dashboard")
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = verify_password(email, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            next_url = request.args.get("next") or "/dashboard"
            return redirect(next_url)
        error = "Invalid email or password."
    return render_template("login.html", error=error)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect("/dashboard")
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        company_name = request.form.get("company_name", "").strip()
        if not email or "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            try:
                user = create_user(email, password, company_name=company_name)
                set_trial(user["id"], days=14)
                session.clear()
                session["user_id"] = user["id"]
                session["user_email"] = user["email"]
                try:
                    from tasks import send_email_task
                    app_url = os.environ.get("APP_URL", "https://govrecompete.com")
                    html_body = render_template("email/welcome.html", user_email=email, app_url=app_url)
                    text_body = render_template("email/welcome.txt", user_email=email, app_url=app_url)
                    send_email_task.delay(
                        to=email,
                        subject="Welcome to Gov Recompete Monitor",
                        html_body=html_body,
                        text_body=text_body,
                    )
                except Exception as exc:
                    logger.warning("Could not enqueue welcome email for %s: %s", email, exc)
                return redirect("/dashboard")
            except ValueError as exc:
                error = str(exc)
    return render_template("register.html", error=error)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")
    email = request.form.get("email", "").strip()
    token = set_reset_token(email)
    if token:
        try:
            from tasks import send_email_task
            app_url = os.environ.get("APP_URL", "https://govrecompete.com")
            reset_url = f"{app_url}/reset-password?token={token}"
            try:
                html_body = render_template(
                    "email/password_reset.html", reset_url=reset_url, app_url=app_url
                )
                text_body = render_template(
                    "email/password_reset.txt", reset_url=reset_url, app_url=app_url
                )
            except Exception:
                html_body = (
                    f'<p>Click to reset your password: <a href="{reset_url}">{reset_url}</a></p>'
                )
                text_body = f"Reset your password: {reset_url}"
            send_email_task.delay(
                to=email,
                subject="Reset your Gov Recompete Monitor password",
                html_body=html_body,
                text_body=text_body,
            )
        except Exception as exc:
            logger.warning("Could not enqueue reset email for %s: %s", email, exc)
    return render_template("forgot_password.html", sent=True)


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        token = request.args.get("token", "")
        user = get_user_by_reset_token(token)
        if not user:
            return render_template("reset_password.html", error="Invalid or expired link.")
        return render_template("reset_password.html", token=token)

    token = request.form.get("token", "")
    user = get_user_by_reset_token(token)
    if not user:
        return render_template("reset_password.html", error="Invalid or expired link.", token=token), 400
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    if len(password) < 8:
        return render_template("reset_password.html", token=token,
                               error="Password must be at least 8 characters.")
    if password != confirm:
        return render_template("reset_password.html", token=token,
                               error="Passwords do not match.")
    update_password(user["id"], password)
    clear_reset_token(user["id"])
    flash("Password updated. Please log in.")
    return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
