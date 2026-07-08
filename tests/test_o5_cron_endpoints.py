"""O5 / Gate 3 — cron-endpoint pattern for watchlist alerts + trial emails.

These endpoints (/alerts/run, /trials/run) let Railway cron services trigger the
formerly-dead beat jobs without a shared Postgres or Celery worker/beat — the job
runs inside `web`, which owns the SQLite volume. Mirrors /ingest/run's auth model.

Hermetic: the task functions are mocked, so no real DB scan or email is sent; a
threading.Event confirms the background thread invoked the right task. The
railway.toml checks are a static parse.
"""
import threading
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import db as db_module
import tasks as tasks_module

ROOT = Path(__file__).resolve().parent.parent
RAILWAY_TOML = ROOT / "railway.toml"


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


def _mk_client(test_db, monkeypatch, secret):
    import app as flask_app
    monkeypatch.setattr(flask_app, "_CRON_SECRET", secret)
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    flask_app.limiter.reset()
    return flask_app, flask_app.app.test_client()


@pytest.fixture()
def client(test_db, monkeypatch):
    _, c = _mk_client(test_db, monkeypatch, "test-secret-xyz")
    return c


@pytest.fixture()
def client_no_secret(test_db, monkeypatch):
    _, c = _mk_client(test_db, monkeypatch, "")
    return c


ENDPOINTS = [
    ("/alerts/run", "check_watchlist_alerts"),
    ("/trials/run", "send_trial_emails"),
]


# ── auth (mirrors /ingest/run) ────────────────────────────────────────────────
@pytest.mark.parametrize("path,_task", ENDPOINTS)
def test_missing_auth_returns_401(client, path, _task):
    assert client.post(path).status_code == 401


@pytest.mark.parametrize("path,_task", ENDPOINTS)
def test_wrong_secret_returns_401(client, path, _task):
    assert client.post(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("path,task_name", ENDPOINTS)
def test_correct_secret_starts_job(client, monkeypatch, path, task_name):
    done = threading.Event()
    mock = MagicMock(side_effect=lambda *a, **k: done.set())
    monkeypatch.setattr(tasks_module, task_name, mock)
    rv = client.post(path, headers={"Authorization": "Bearer test-secret-xyz"})
    assert rv.status_code == 202
    assert rv.get_json()["status"] == "started"
    assert done.wait(5), f"{task_name} was not invoked by the background thread"
    mock.assert_called_once()


@pytest.mark.parametrize("path,task_name", ENDPOINTS)
def test_no_secret_configured_allows_request(client_no_secret, monkeypatch, path, task_name):
    done = threading.Event()
    monkeypatch.setattr(tasks_module, task_name, MagicMock(side_effect=lambda *a, **k: done.set()))
    rv = client_no_secret.post(path)
    assert rv.status_code == 202
    assert done.wait(5)


# ── overlap guard ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("path,job", [("/alerts/run", "alerts"), ("/trials/run", "trials")])
def test_overlap_returns_409(test_db, monkeypatch, path, job):
    import app as flask_app
    _, c = _mk_client(test_db, monkeypatch, "test-secret-xyz")
    monkeypatch.setitem(flask_app._cron_running, job, True)  # pretend a run is in flight
    rv = c.post(path, headers={"Authorization": "Bearer test-secret-xyz"})
    assert rv.status_code == 409
    assert rv.get_json()["status"] == "already_running"


# ── railway.toml services (static) ────────────────────────────────────────────
def test_railway_has_alerts_and_trials_cron_services():
    with open(RAILWAY_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    svc = {s["name"]: s for s in cfg.get("services", [])}
    assert {"web", "daily-ingest", "alerts-cron", "trials-cron"} <= set(svc)

    alerts = svc["alerts-cron"]["deploy"]
    assert alerts["cronSchedule"] == "0 7 * * *"
    assert "/alerts/run" in alerts["startCommand"] and "$CRON_SECRET" in alerts["startCommand"]

    trials = svc["trials-cron"]["deploy"]
    assert trials["cronSchedule"] == "0 9 * * *"
    assert "/trials/run" in trials["startCommand"] and "$CRON_SECRET" in trials["startCommand"]

    # The overlap-guard 409 must be treated as success (not a crashed cron run):
    # each command captures the HTTP code and exits 0 on 2xx OR 409.
    for dep in (alerts, trials):
        cmd = dep["startCommand"]
        assert "%{http_code}" in cmd, "cron must capture the HTTP status"
        assert "409" in cmd, "cron must treat the overlap-guard 409 as success"

    # worker/beat must still NOT be active services (Postgres path unchanged).
    assert "worker" not in svc and "beat" not in svc
