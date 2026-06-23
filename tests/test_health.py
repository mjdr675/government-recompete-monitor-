"""Tests for the /health endpoint — Task 057."""

import json
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
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        yield c


def test_health_returns_200(client):
    rv = client.get("/health")
    assert rv.status_code == 200


def test_health_returns_json_status_ok(client):
    rv = client.get("/health")
    data = json.loads(rv.data)
    assert data == {"status": "ok"}


def test_health_accessible_unauthenticated(client):
    # No login — should still return 200, not a redirect
    rv = client.get("/health")
    assert rv.status_code == 200
    assert rv.status_code != 302


def test_health_content_type_is_json(client):
    rv = client.get("/health")
    assert "application/json" in rv.content_type
