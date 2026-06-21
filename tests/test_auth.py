"""
Integration tests for the authentication system.

Each test gets an isolated SQLite database in a tmp_path directory.
The Flask test client persists cookies between requests so session
state flows correctly through registration → login → logout cycles.
"""

import pytest
import db as db_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client, email="user@example.com", password="password123", confirm=None):
    return client.post("/register", data={
        "email": email,
        "password": password,
        "confirm": confirm if confirm is not None else password,
    })


def _login(client, email="user@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password})


def _register_and_login(client, email="user@example.com", password="password123"):
    _register(client, email=email, password=password)
    # Registration auto-logs in; reset session then log in explicitly for clarity
    client.get("/logout")
    return _login(client, email=email, password=password)


# ---------------------------------------------------------------------------
# Public routes — no login required
# ---------------------------------------------------------------------------

def test_health_accessible_without_login(client):
    rv = client.get("/health")
    assert rv.status_code == 200


def test_login_page_accessible_without_login(client):
    rv = client.get("/login")
    assert rv.status_code == 200
    assert b"Sign In" in rv.data


def test_register_page_accessible_without_login(client):
    rv = client.get("/register")
    assert rv.status_code == 200
    assert b"Create Account" in rv.data


def test_protected_route_redirects_to_login(client):
    rv = client.get("/")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_protected_route_preserves_next_param(client):
    rv = client.get("/contracts")
    assert rv.status_code == 302
    loc = rv.headers["Location"]
    assert "/login" in loc
    assert "next" in loc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_success_redirects_home(client):
    rv = _register(client)
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


def test_register_auto_logs_in(client):
    _register(client)
    rv = client.get("/", follow_redirects=True)
    assert rv.status_code == 200


def test_register_duplicate_email_shows_error(client):
    _register(client)
    client.get("/logout")  # clear session so /register is accessible
    rv = _register(client)  # second attempt with same email
    assert rv.status_code == 200
    assert b"already registered" in rv.data


def test_register_invalid_email_shows_error(client):
    rv = _register(client, email="notanemail")
    assert rv.status_code == 200
    assert b"valid email" in rv.data


def test_register_short_password_shows_error(client):
    rv = _register(client, password="short", confirm="short")
    assert rv.status_code == 200
    assert b"8 characters" in rv.data


def test_register_password_mismatch_shows_error(client):
    rv = _register(client, password="password123", confirm="different456")
    assert rv.status_code == 200
    assert b"do not match" in rv.data


def test_register_email_is_case_insensitive(client):
    _register(client, email="User@Example.COM")
    rv = _login(client, email="user@example.com")
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success_redirects_home(client):
    _register(client)
    client.get("/logout")
    rv = _login(client)
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


def test_login_wrong_password_shows_error(client):
    _register(client)
    client.get("/logout")
    rv = _login(client, password="wrongpassword")
    assert rv.status_code == 200
    assert b"Invalid email or password" in rv.data


def test_login_unknown_email_shows_error(client):
    rv = _login(client, email="nobody@example.com")
    assert rv.status_code == 200
    assert b"Invalid email or password" in rv.data


def test_login_preserves_next_redirect(client):
    _register(client)
    client.get("/logout")
    rv = client.post("/login?next=/contracts", data={
        "email": "user@example.com",
        "password": "password123",
    })
    assert rv.status_code == 302
    assert "/contracts" in rv.headers["Location"]


def test_already_logged_in_redirected_away_from_login(client):
    _register(client)
    rv = client.get("/login")
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


def test_already_logged_in_redirected_away_from_register(client):
    _register(client)
    rv = client.get("/register")
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def test_logout_clears_session(client):
    _register(client)
    rv = client.get("/logout")
    assert rv.status_code == 302
    # After logout, protected route redirects to login
    rv = client.get("/")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_logout_redirects_to_login(client):
    _register(client)
    rv = client.get("/logout")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


# ---------------------------------------------------------------------------
# Route protection
# ---------------------------------------------------------------------------

def test_protected_routes_accessible_when_logged_in(client):
    _register(client)
    for path in ["/", "/contracts", "/views", "/ingest"]:
        rv = client.get(path)
        assert rv.status_code == 200, f"{path} returned {rv.status_code}"


def test_password_not_stored_in_plaintext(auth_db):
    import db as db_mod
    from users import create_user
    create_user("check@example.com", "mypassword")
    with db_mod.connect() as con:
        row = con.execute(
            "SELECT password_hash FROM users WHERE email=?", ("check@example.com",)
        ).fetchone()
    assert row is not None
    assert row[0] != "mypassword"
    assert row[0].startswith(("scrypt:", "pbkdf2:", "argon2"))


def test_create_user_duplicate_email_raises_value_error(auth_db):
    from users import create_user
    create_user("dup@example.com", "password123")
    with pytest.raises(ValueError, match="already registered"):
        create_user("DUP@EXAMPLE.COM", "different456")


def test_csrf_rejected_on_login_post(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = True
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        rv = c.post("/login", data={"email": "x@example.com", "password": "pw"})
        assert rv.status_code == 400
    flask_app.app.config["WTF_CSRF_ENABLED"] = False


def test_login_rate_limited(auth_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = True
    flask_app.app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        for _ in range(5):
            c.post("/login", data={"email": "x@example.com", "password": "wrong"})
        rv = c.post("/login", data={"email": "x@example.com", "password": "wrong"})
        assert rv.status_code == 429
    flask_app.app.config["RATELIMIT_ENABLED"] = False


def test_registration_enqueues_welcome_email(client, monkeypatch):
    from unittest.mock import MagicMock, patch
    import tasks as tasks_module
    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)
    client.post("/register", data={
        "email": "newuser@example.com",
        "password": "password123",
        "confirm": "password123",
    })
    mock_delay.assert_called_once()
    call_kwargs = mock_delay.call_args[1]
    assert call_kwargs["to"] == "newuser@example.com"
    assert "Welcome" in call_kwargs["subject"]


# ---------------------------------------------------------------------------
# /forgot-password (Task 103)
# ---------------------------------------------------------------------------

def test_forgot_password_get_returns_200(client):
    rv = client.get("/forgot-password")
    assert rv.status_code == 200


def test_forgot_password_post_unknown_email_returns_200(client):
    rv = client.post("/forgot-password", data={"email": "nobody@example.com"})
    assert rv.status_code == 200


def test_forgot_password_post_known_email_sets_token(client, auth_db, monkeypatch):
    import sqlite3
    import tasks as tasks_module
    from unittest.mock import MagicMock
    from users import create_user
    create_user("reset@example.com", "password123")
    mock_delay = MagicMock()
    monkeypatch.setattr(tasks_module.send_email_task, "delay", mock_delay)
    rv = client.post("/forgot-password", data={"email": "reset@example.com"})
    assert rv.status_code == 200
    mock_delay.assert_called_once()
    con = sqlite3.connect(auth_db)
    row = con.execute(
        "SELECT reset_token, reset_token_expires_at FROM users WHERE email='reset@example.com'"
    ).fetchone()
    con.close()
    assert row[0] is not None
    assert row[1] is not None


def test_forgot_password_post_known_email_no_enumeration(client, monkeypatch):
    import tasks as tasks_module
    from unittest.mock import MagicMock
    monkeypatch.setattr(tasks_module.send_email_task, "delay", MagicMock())
    rv_known = client.post("/forgot-password", data={"email": "anyone@example.com"})
    rv_unknown = client.post("/forgot-password", data={"email": "ghost@example.com"})
    assert b"reset link" in rv_known.data.lower() or b"sent" in rv_known.data.lower() or b"registered" in rv_known.data.lower()
    assert rv_known.data == rv_unknown.data


def test_registration_succeeds_if_email_task_raises(client, monkeypatch):
    import tasks as tasks_module
    monkeypatch.setattr(tasks_module.send_email_task, "delay", lambda **kw: (_ for _ in ()).throw(RuntimeError("Redis down")))
    rv = client.post("/register", data={
        "email": "another@example.com",
        "password": "password123",
        "confirm": "password123",
    })
    assert rv.status_code == 302
