"""Tests for Task 062 — SQLAlchemy Core schema migration."""

import os
import sqlite3
import pytest
from sqlalchemy import create_engine, text, inspect
import db as db_module


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    yield db_module.get_engine()
    db_module._cached_engine.cache_clear()


# ---------------------------------------------------------------------------
# get_engine — returns SQLAlchemy Engine
# ---------------------------------------------------------------------------

class TestGetEngine:
    def test_returns_sqlalchemy_engine(self, engine):
        from sqlalchemy.engine import Engine
        assert isinstance(engine, Engine)

    def test_sqlite_dialect_when_no_database_url(self, engine):
        assert engine.dialect.name == "sqlite"

    def test_same_engine_returned_for_same_url(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "same.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        e1 = db_module.get_engine()
        e2 = db_module.get_engine()
        assert e1 is e2
        db_module._cached_engine.cache_clear()

    def test_engine_url_uses_db_path(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "url_test.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        eng = db_module.get_engine()
        assert db_path in str(eng.url)
        db_module._cached_engine.cache_clear()


# ---------------------------------------------------------------------------
# init_db — creates tables via SQLAlchemy
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_contracts_table_exists(self, engine):
        insp = inspect(engine)
        assert "contracts" in insp.get_table_names()

    def test_users_table_exists(self, engine):
        insp = inspect(engine)
        assert "users" in insp.get_table_names()

    def test_contracts_columns_present(self, engine):
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("contracts")}
        required = {"internal_id", "award_id", "vendor", "agency", "sub_agency",
                    "value", "start_date", "end_date", "days_remaining",
                    "competition_type", "solicitation_id", "recompete_score",
                    "priority", "raw_json", "updated_at"}
        assert required <= cols

    def test_idempotent_double_call(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "idem.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db_module._cached_engine.cache_clear()
        db_module.init_db()
        db_module.init_db()  # second call must not raise
        db_module._cached_engine.cache_clear()

    def test_fts_virtual_table_exists(self, engine):
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='contracts_fts'"
            )).fetchone()
        assert result is not None

    def test_postgresql_init_db_returns_early(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/testdb")
        db_module.init_db()  # must not raise even without a real PG server


# ---------------------------------------------------------------------------
# text() queries — :param style reaches the DB correctly
# ---------------------------------------------------------------------------

class TestNamedParams:
    def test_insert_and_read_via_engine(self, engine):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO contracts (internal_id, vendor, agency, value, priority, recompete_score)
                VALUES (:id, :vendor, :agency, :value, :priority, :score)
            """), {
                "id": "SA-001", "vendor": "NamedParam Corp", "agency": "DOD",
                "value": 500_000, "priority": "HIGH", "score": 75,
            })

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT vendor FROM contracts WHERE internal_id = :id"),
                {"id": "SA-001"},
            ).fetchone()
        assert row is not None
        assert row[0] == "NamedParam Corp"

    def test_row_mapping_key_access(self, engine):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO contracts (internal_id, vendor, agency, priority, recompete_score)
                VALUES (:id, :vendor, :agency, :priority, :score)
            """), {"id": "SA-002", "vendor": "Acme", "agency": "GSA",
                   "priority": "MEDIUM", "score": 50})

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM contracts WHERE internal_id = :id"),
                {"id": "SA-002"},
            ).mappings().fetchone()
        assert row["vendor"] == "Acme"
        assert row["agency"] == "GSA"


# ---------------------------------------------------------------------------
# get_contracts — SQLAlchemy-backed query
# ---------------------------------------------------------------------------

class TestGetContractsSQLAlchemy:
    @pytest.fixture(autouse=True)
    def seed(self, engine):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO contracts
                (internal_id, vendor, agency, value, priority, recompete_score, days_remaining)
                VALUES
                ('C1', 'Alpha Inc', 'DOD', 1000000, 'HIGH', 80, 60),
                ('C2', 'Beta LLC', 'DHS', 2000000, 'CRITICAL', 95, 30),
                ('C3', 'Gamma Corp', 'DOD', 500000, 'MEDIUM', 50, 120)
            """))

    def test_returns_all_contracts(self, engine):
        result = db_module.get_contracts()
        assert result["total"] == 3

    def test_priority_filter(self, engine):
        result = db_module.get_contracts(priority="CRITICAL")
        assert result["total"] == 1
        assert result["contracts"][0]["vendor"] == "Beta LLC"

    def test_agency_filter(self, engine):
        result = db_module.get_contracts(agency="DOD")
        assert result["total"] == 2

    def test_min_value_filter(self, engine):
        result = db_module.get_contracts(min_value=900_000)
        assert result["total"] == 2

    def test_days_filter(self, engine):
        result = db_module.get_contracts(days=60)
        assert result["total"] == 2

    def test_row_supports_key_access(self, engine):
        result = db_module.get_contracts()
        row = result["contracts"][0]
        assert "vendor" in row
        assert "agency" in row
        assert "priority" in row


# ---------------------------------------------------------------------------
# migrations/001_initial_pg.sql — file existence and basic content
# ---------------------------------------------------------------------------

class TestMigrationFile:
    def test_migration_file_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        assert os.path.exists(path)

    def test_migration_file_contains_create_extension_vector(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        content = open(path).read()
        assert "CREATE EXTENSION IF NOT EXISTS vector" in content

    def test_migration_file_contains_contracts_table(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        content = open(path).read()
        assert "CREATE TABLE IF NOT EXISTS contracts" in content

    def test_migration_file_contains_search_vector(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        content = open(path).read()
        assert "search_vector" in content
        assert "tsvector" in content

    def test_migration_file_contains_all_tables(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        content = open(path).read()
        for table in ["contracts", "contract_snapshots", "changes", "users",
                      "demo_requests", "early_access"]:
            assert table in content

    def test_migration_file_is_idempotent_keywords(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "001_initial_pg.sql"
        )
        content = open(path).read()
        # Every CREATE should have IF NOT EXISTS
        import re
        creates = re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|EXTENSION)", content, re.IGNORECASE)
        assert len(creates) > 0, "Migration should have CREATE statements"
        for match in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|EXTENSION)\b", content, re.IGNORECASE):
            start = match.start()
            chunk = content[start:start + 80]
            assert "IF NOT EXISTS" in chunk, f"Missing IF NOT EXISTS near: {chunk!r}"
