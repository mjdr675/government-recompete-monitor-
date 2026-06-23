"""Tests for PostgreSQL provision and get_connection() — Task 061."""

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
import db as db_module


# ---------------------------------------------------------------------------
# get_connection — SQLite fallback (no DATABASE_URL)
# ---------------------------------------------------------------------------

class TestGetConnectionSQLite:
    def test_returns_sqlite_connection_when_no_database_url(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        conn = db_module.get_connection()
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()

    def test_sqlite_connection_uses_db_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_path = str(tmp_path / "custom.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        conn = db_module.get_connection()
        conn.close()
        assert os.path.exists(db_path)

    def test_connect_alias_returns_sqlite(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        conn = db_module.connect()
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# get_connection — PostgreSQL (DATABASE_URL set)
# ---------------------------------------------------------------------------

class TestGetConnectionPostgreSQL:
    def test_returns_psycopg2_connection_when_database_url_set(self, monkeypatch):
        mock_conn = MagicMock()
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            conn = db_module.get_connection()

        mock_psycopg2.connect.assert_called_once_with("postgresql://user:pass@localhost/testdb")
        assert conn is mock_conn

    def test_raises_runtime_error_when_psycopg2_not_installed(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        with patch.dict("sys.modules", {"psycopg2": None}):
            with pytest.raises((RuntimeError, ImportError)):
                db_module.get_connection()

    def test_connect_alias_uses_psycopg2_when_database_url_set(self, monkeypatch):
        mock_conn = MagicMock()
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            conn = db_module.connect()

        assert conn is mock_conn


# ---------------------------------------------------------------------------
# init_db — behavior with DATABASE_URL set
# ---------------------------------------------------------------------------

class TestInitDbWithDatabaseUrl:
    def test_init_db_returns_early_when_database_url_set(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        # Should not raise even though psycopg2 may not have a real server
        with patch.dict("sys.modules", {"psycopg2": MagicMock()}):
            db_module.init_db()  # must not raise

    def test_init_db_runs_normally_without_database_url(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        db_module.init_db()
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        table_names = [t[0] for t in tables]
        assert "contracts" in table_names


# ---------------------------------------------------------------------------
# App starts without error (health route)
# ---------------------------------------------------------------------------

class TestAppStartsWithDatabaseUrl:
    def test_health_returns_200_with_database_url_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
        db_module.init_db()  # no-op when DATABASE_URL set

        import app as flask_app
        flask_app.app.config["TESTING"] = True
        flask_app.app.secret_key = "test-secret-key"
        with flask_app.app.test_client() as c:
            rv = c.get("/health")
        assert rv.status_code == 200

    def test_health_returns_200_without_database_url(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        original = db_module.DB_PATH
        db_module.DB_PATH = str(tmp_path / "test.db")
        db_module.init_db()

        import app as flask_app
        flask_app.app.config["TESTING"] = True
        flask_app.app.secret_key = "test-secret-key"
        with flask_app.app.test_client() as c:
            rv = c.get("/health")
        db_module.DB_PATH = original
        assert rv.status_code == 200
