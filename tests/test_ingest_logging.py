"""Tests for ingest logging and /ingest/status route — Task 058."""

import os
import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db, tmp_path, monkeypatch):
    import app as flask_app
    # Point ingest log to a temp path so tests are isolated
    log_path = str(tmp_path / "ingest.log")
    monkeypatch.setattr(flask_app, "INGEST_LOG_PATH", log_path)
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


@pytest.fixture()
def anon_client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# /ingest/status route tests
# ---------------------------------------------------------------------------

def test_ingest_status_returns_200_when_authenticated(client):
    rv = client.get("/ingest/status")
    assert rv.status_code == 200


def test_ingest_status_content_type_is_text_plain(client):
    rv = client.get("/ingest/status")
    assert "text/plain" in rv.content_type


def test_ingest_status_unauthenticated_redirects(anon_client):
    rv = anon_client.get("/ingest/status")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_ingest_status_no_log_file_returns_message(client):
    rv = client.get("/ingest/status")
    assert rv.status_code == 200
    text = rv.data.decode("utf-8")
    assert "no" in text.lower() or "not found" in text.lower() or "no log" in text.lower()


def test_ingest_status_reads_log_content(client, tmp_path, monkeypatch):
    import app as flask_app
    log_path = str(tmp_path / "ingest.log")
    monkeypatch.setattr(flask_app, "INGEST_LOG_PATH", log_path)
    with open(log_path, "w") as f:
        f.write("line 1\nline 2\nline 3\n")
    rv = client.get("/ingest/status")
    text = rv.data.decode("utf-8")
    assert "line 1" in text
    assert "line 2" in text


def test_ingest_status_returns_at_most_50_lines(client, tmp_path, monkeypatch):
    import app as flask_app
    log_path = str(tmp_path / "ingest.log")
    monkeypatch.setattr(flask_app, "INGEST_LOG_PATH", log_path)
    with open(log_path, "w") as f:
        for i in range(100):
            f.write(f"log line {i}\n")
    rv = client.get("/ingest/status")
    text = rv.data.decode("utf-8")
    lines = [l for l in text.splitlines() if l.strip()]
    assert len(lines) <= 50


def test_ingest_status_returns_last_lines(client, tmp_path, monkeypatch):
    import app as flask_app
    log_path = str(tmp_path / "ingest.log")
    monkeypatch.setattr(flask_app, "INGEST_LOG_PATH", log_path)
    with open(log_path, "w") as f:
        for i in range(100):
            f.write(f"log line {i}\n")
    rv = client.get("/ingest/status")
    text = rv.data.decode("utf-8")
    # Last line should be line 99
    assert "log line 99" in text
    # First line (line 0) should not be present
    assert "log line 0\n" not in text


# ---------------------------------------------------------------------------
# Ingest logger setup tests
# ---------------------------------------------------------------------------

def test_ingest_logger_exists():
    import app as flask_app
    import logging
    assert flask_app._ingest_logger is not None
    assert isinstance(flask_app._ingest_logger, logging.Logger)


def test_ingest_log_path_defined():
    import app as flask_app
    assert hasattr(flask_app, "INGEST_LOG_PATH")
    assert flask_app.INGEST_LOG_PATH.endswith("ingest.log")


def test_rotating_file_handler_configured():
    from logging.handlers import RotatingFileHandler
    import app as flask_app
    logger = flask_app._ingest_logger
    rh = next((h for h in logger.handlers if isinstance(h, RotatingFileHandler)), None)
    assert rh is not None
    assert rh.maxBytes == 1_000_000
    assert rh.backupCount == 3


# ---------------------------------------------------------------------------
# ingest.html template tests
# ---------------------------------------------------------------------------

def test_ingest_page_has_view_log_link(client):
    rv = client.get("/ingest")
    assert rv.status_code == 200
    assert b"/ingest/status" in rv.data


def test_ingest_page_has_view_log_text(client):
    rv = client.get("/ingest")
    assert b"View log" in rv.data
