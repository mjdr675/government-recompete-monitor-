"""Tests for psc_code and place_of_performance_country schema additions.

Both columns are added to the CREATE TABLE definition and also via a
_ensure_richer_location_columns() self-heal so existing Railway databases
without these columns get them on next startup without data loss.
"""

import pytest
from sqlalchemy import text

import db as db_module


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


def _cols(engine):
    with engine.connect() as conn:
        return [r[1] for r in conn.execute(text("PRAGMA table_info(contracts)"))]


def _drop_col(engine, col):
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE contracts DROP COLUMN {col}"))


class TestRicherLocationColumns:
    def test_brand_new_db_has_psc_code(self, sqlite_db):
        db_module.init_db()
        assert "psc_code" in _cols(db_module.get_engine())

    def test_brand_new_db_has_performance_country(self, sqlite_db):
        db_module.init_db()
        assert "place_of_performance_country" in _cols(db_module.get_engine())

    def test_self_heal_adds_psc_code_to_existing_db(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        _drop_col(engine, "psc_code")
        assert "psc_code" not in _cols(engine)

        db_module.init_db()
        assert "psc_code" in _cols(engine)

    def test_self_heal_adds_country_to_existing_db(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        _drop_col(engine, "place_of_performance_country")
        assert "place_of_performance_country" not in _cols(engine)

        db_module.init_db()
        assert "place_of_performance_country" in _cols(engine)

    def test_existing_rows_survive_self_heal(self, sqlite_db):
        db_module.init_db()
        engine = db_module.get_engine()
        db_module.upsert_contract({
            "internal_id": "KEEP_ME",
            "award_id": "AWD-KEEP",
            "vendor": "Acme Corp",
            "agency": "GSA",
        })
        _drop_col(engine, "psc_code")
        _drop_col(engine, "place_of_performance_country")

        db_module.init_db()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT vendor, psc_code, place_of_performance_country"
                " FROM contracts WHERE internal_id = 'KEEP_ME'"
            )).fetchone()
        assert row[0] == "Acme Corp"
        assert row[1] is None
        assert row[2] is None

    def test_self_heal_is_idempotent(self, sqlite_db):
        db_module.init_db()
        db_module.init_db()
        db_module.init_db()
        cols = _cols(db_module.get_engine())
        assert cols.count("psc_code") == 1
        assert cols.count("place_of_performance_country") == 1


class TestPscCodeAndCountryPersistence:
    def test_upsert_contract_saves_psc_code(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "AWD_PSC",
            "vendor": "Globex",
            "agency": "DoD",
            "psc_code": "S201",
            "psc_description": "HOUSEKEEPING SERVICES",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT psc_code, psc_description FROM contracts WHERE internal_id = 'AWD_PSC'"
            )).fetchone()
        assert row[0] == "S201"
        assert row[1] == "HOUSEKEEPING SERVICES"

    def test_upsert_contract_saves_performance_country(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "AWD_CTRY",
            "vendor": "Overseas Vendor",
            "agency": "State Dept",
            "performance_country": "GERMANY",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT place_of_performance_country FROM contracts WHERE internal_id = 'AWD_CTRY'"
            )).scalar()
        assert val == "GERMANY"

    def test_save_snapshot_saves_psc_code_and_country(self, sqlite_db):
        from datetime import date
        db_module.init_db()
        rows = [{
            "internal_id": "SNAP_PSC",
            "generated_internal_id": "SNAP_PSC",
            "award_id": "AWD-SNAP",
            "vendor": "Test Vendor",
            "agency": "DoD",
            "value": 500000,
            "start_date": "2024-01-01",
            "end_date": "2026-12-31",
            "days_remaining": 189,
            "recompete_score": 55,
            "priority": "MEDIUM",
            "psc_code": "R499",
            "psc_description": "SUPPORT SERVICES",
            "performance_country": "JAPAN",
        }]
        db_module.save_snapshot(str(date.today()), rows)
        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT psc_code, place_of_performance_country"
                " FROM contracts WHERE internal_id = 'SNAP_PSC'"
            )).fetchone()
        assert row[0] == "R499"
        assert row[1] == "JAPAN"

    def test_missing_psc_code_stored_as_null(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "NO_PSC",
            "vendor": "Acme",
            "agency": "GSA",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT psc_code FROM contracts WHERE internal_id = 'NO_PSC'"
            )).scalar()
        assert val is None

    def test_us_country_code_variants_are_saved(self, sqlite_db):
        """US country string comes through as-is — display layer filters it out, not DB."""
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "US_CTRY",
            "vendor": "US Vendor",
            "agency": "VA",
            "performance_country": "UNITED STATES",
        })
        engine = db_module.get_engine()
        with engine.connect() as conn:
            val = conn.execute(text(
                "SELECT place_of_performance_country FROM contracts WHERE internal_id = 'US_CTRY'"
            )).scalar()
        assert val == "UNITED STATES"


class TestDetailPageFields:
    """Smoke-test that the contract_detail route extracts and passes new fields."""

    @pytest.fixture()
    def authed_client(self, sqlite_db):
        import app as app_module
        app_module.app.config["TESTING"] = True
        app_module.app.config["WTF_CSRF_ENABLED"] = False
        db_module.init_db()
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT OR IGNORE INTO users (email, password_hash, created_at, is_active)"
                " VALUES ('u@t.com', 'x', '2025-01-01', 1)"
            ))
            user_id = conn.execute(text(
                "SELECT id FROM users WHERE email = 'u@t.com'"
            )).scalar()
        with app_module.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = user_id
            yield client

    def test_detail_page_renders_psc_description(self, authed_client, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "DETAIL_PSC",
            "award_id": "AWD-DETAIL",
            "vendor": "Test Vendor",
            "agency": "DoD",
            "value": 750000,
            "end_date": "2027-06-01",
            "days_remaining": 340,
            "priority": "MEDIUM",
            "recompete_score": 60,
            "psc_code": "S201",
            "psc_description": "HOUSEKEEPING SERVICES",
        })
        resp = authed_client.get("/contract/DETAIL_PSC")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "HOUSEKEEPING SERVICES" in body
        assert "S201" in body

    def test_detail_page_shows_country_for_non_us(self, authed_client, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "DETAIL_CTRY",
            "award_id": "AWD-CTRY",
            "vendor": "Overseas Corp",
            "agency": "State",
            "value": 200000,
            "end_date": "2027-01-01",
            "days_remaining": 190,
            "priority": "LOW",
            "recompete_score": 30,
            "performance_country": "GERMANY",
        })
        resp = authed_client.get("/contract/DETAIL_CTRY")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "GERMANY" in body

    def test_detail_page_omits_country_for_us(self, authed_client, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "DETAIL_US",
            "award_id": "AWD-US",
            "vendor": "Domestic Corp",
            "agency": "DoD",
            "value": 500000,
            "end_date": "2027-06-01",
            "days_remaining": 340,
            "priority": "MEDIUM",
            "recompete_score": 55,
            "performance_country": "UNITED STATES",
        })
        resp = authed_client.get("/contract/DETAIL_US")
        assert resp.status_code == 200
        body = resp.data.decode()
        # "UNITED STATES" should NOT appear as a country annotation in the location row
        assert "UNITED STATES" not in body
