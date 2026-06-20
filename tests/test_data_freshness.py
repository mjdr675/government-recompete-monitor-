"""Tests for GET /api/data-freshness."""

import pytest
import db as db_module
from datetime import datetime, timezone, timedelta


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.test_client() as c:
        yield c


def _insert_ingest_row(test_db, status="success", hours_ago=6):
    import sqlite3
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    con = sqlite3.connect(test_db)
    con.execute(
        "INSERT INTO ingest_log (run_date, source, record_count, duration_seconds, status, created_at)"
        " VALUES (?, 'usaspending', 100, 1.5, ?, ?)",
        (ts[:10], status, ts),
    )
    con.commit()
    con.close()


def test_no_ingest_returns_null_fields(client):
    rv = client.get("/api/data-freshness")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["last_ingest"] is None
    assert data["hours_ago"] is None
    assert data["record_count"] == 0


def test_with_ingest_row_returns_fields(client, test_db):
    _insert_ingest_row(test_db, hours_ago=6)
    rv = client.get("/api/data-freshness")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["last_ingest"] is not None
    assert data["source"] == "usaspending"
    assert data["record_count"] == 0  # no contracts in test DB


def test_hours_ago_is_approximately_correct(client, test_db):
    _insert_ingest_row(test_db, hours_ago=4)
    rv = client.get("/api/data-freshness")
    data = rv.get_json()
    assert data["hours_ago"] is not None
    assert 3.5 <= data["hours_ago"] <= 4.5


def test_failure_row_not_returned(client, test_db):
    _insert_ingest_row(test_db, status="failure", hours_ago=1)
    rv = client.get("/api/data-freshness")
    data = rv.get_json()
    assert data["last_ingest"] is None


def test_unauthenticated_request_returns_200(client):
    rv = client.get("/api/data-freshness")
    assert rv.status_code == 200
    assert rv.content_type.startswith("application/json")
