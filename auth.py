import functools

from flask import (Blueprint, g, redirect, render_template,
                   request, session, url_for)

from users import create_user, get_user_by_id, verify_password

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
    user_id = session.get("user_id")
    g.user = get_user_by_id(user_id) if user_id else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect("/")
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = verify_password(email, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            next_url = request.args.get("next") or "/"
            return redirect(next_url)
        error = "Invalid email or password."
    return render_template("login.html", error=error)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect("/")
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not email or "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            try:
                user = create_user(email, password)
                session.clear()
                session["user_id"] = user["id"]
                session["user_email"] = user["email"]
                return redirect("/")
            except ValueError as exc:
                error = str(exc)
    return render_template("register.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
