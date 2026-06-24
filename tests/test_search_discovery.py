"""Tests for search + data-discovery features.

Covers: category inference, category/state storage at ingest, category/state
filters in get_contracts(), fuzzy FTS search, discover mode (exclude_ids),
list_contract_states(), the /contracts route, and the contract detail page.
"""
import os

import pytest

import db as db_module


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fresh_db(tmp_path):
    """Point db_module at a fresh isolated SQLite file, reinitialise schema."""
    db_path = str(tmp_path / "test.db")
    db_module._cached_engine.cache_clear()
    db_module.DB_PATH = db_path
    db_module.init_db()
    return db_module


def _insert(db, **kwargs):
    """Insert a minimal contract row via upsert_contract."""
    defaults = {
        "internal_id": "C1",
        "award_id": "A1",
        "vendor": "Test Vendor",
        "agency": "TEST AGENCY",
        "description": "",
        "value": 100000,
        "days_remaining": 90,
        "recompete_score": 50,
        "priority": "MEDIUM",
    }
    defaults.update(kwargs)
    db.upsert_contract(defaults)


# ---------------------------------------------------------------------------
# TestCategoryInference
# ---------------------------------------------------------------------------

class TestCategoryInference:
    def test_janitorial_keyword(self):
        assert db_module.infer_category(description="janitorial services") == "Cleaning"

    def test_cleaning_keyword(self):
        assert db_module.infer_category(description="office cleaning contract") == "Cleaning"

    def test_custodial_keyword(self):
        assert db_module.infer_category(description="custodial support") == "Cleaning"

    def test_landscaping_keyword(self):
        assert db_module.infer_category(description="landscaping and grounds maintenance") == "Grounds"

    def test_lawn_keyword(self):
        assert db_module.infer_category(description="lawn mowing services") == "Grounds"

    def test_it_keyword(self):
        assert db_module.infer_category(description="information technology support") == "IT"

    def test_helpdesk_keyword(self):
        assert db_module.infer_category(description="help desk and desktop support") == "IT"

    def test_cybersecurity_keyword(self):
        assert db_module.infer_category(description="cybersecurity operations center") == "Cybersecurity"

    def test_facilities_keyword(self):
        assert db_module.infer_category(description="building facility maintenance contract") == "Facilities"

    def test_construction_keyword(self):
        assert db_module.infer_category(description="road construction and paving") == "Construction"

    def test_security_guard_keyword(self):
        assert db_module.infer_category(description="security guard services at federal building") == "Security"

    def test_logistics_keyword(self):
        assert db_module.infer_category(description="logistics and supply chain management") == "Logistics"

    def test_naics_561720_cleaning(self):
        assert db_module.infer_category(naics_code="561720") == "Cleaning"

    def test_naics_561730_grounds(self):
        assert db_module.infer_category(naics_code="561730") == "Grounds"

    def test_naics_541512_it(self):
        assert db_module.infer_category(naics_code="541512") == "IT"

    def test_description_beats_naics(self):
        """Keyword in description takes priority over NAICS code."""
        assert db_module.infer_category(
            description="cybersecurity operations", naics_code="541512"
        ) == "Cybersecurity"

    def test_unknown_returns_other(self):
        assert db_module.infer_category(description="miscellaneous government services") == "Other"


# ---------------------------------------------------------------------------
# TestCategoryStoredAtIngest
# ---------------------------------------------------------------------------

class TestCategoryStoredAtIngest:
    def test_upsert_infers_and_stores_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C1", description="janitorial cleaning services")
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT category FROM contracts WHERE internal_id = 'C1'")
            ).fetchone()
        assert row[0] == "Cleaning"

    def test_save_snapshot_infers_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        db.save_snapshot("2024-01-01", [{
            "internal_id": "C2",
            "vendor": "Grounds Co",
            "agency": "USDA",
            "description": "landscaping and grounds maintenance",
            "value": 200000,
            "days_remaining": 60,
            "recompete_score": 70,
            "priority": "HIGH",
        }])
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT category FROM contracts WHERE internal_id = 'C2'")
            ).fetchone()
        assert row[0] == "Grounds"

    def test_pop_state_stored(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C3", place_of_performance_state="TX")
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT place_of_performance_state FROM contracts WHERE internal_id = 'C3'")
            ).fetchone()
        assert row[0] == "TX"

    def test_naics_code_stored(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C4", naics_code="561720")
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT naics_code FROM contracts WHERE internal_id = 'C4'")
            ).fetchone()
        assert row[0] == "561720"


# ---------------------------------------------------------------------------
# TestCategoryFilter
# ---------------------------------------------------------------------------

class TestCategoryFilter:
    def _setup(self, db):
        _insert(db, internal_id="C1", description="janitorial cleaning services", value=100000)
        _insert(db, internal_id="C2", description="landscaping grounds maintenance", value=200000)
        _insert(db, internal_id="C3", description="information technology support", value=300000)

    def test_filter_by_cleaning(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" in ids
        assert "C2" not in ids

    def test_filter_by_grounds(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(category="Grounds")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C2" in ids
        assert "C1" not in ids

    def test_filter_by_it(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(category="IT")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C3" in ids
        assert "C1" not in ids

    def test_no_category_returns_all(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts()
        assert result["total"] == 3

    def test_nonexistent_category_returns_empty(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(category="Nonexistent")
        assert result["total"] == 0

    def test_category_combined_with_search(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        _insert(db, internal_id="C4", description="janitorial cleaning DOD", agency="DEFENSE", value=400000)
        result = db.get_contracts(q="DOD", category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C4" in ids
        assert "C1" not in ids


# ---------------------------------------------------------------------------
# TestStateFilter
# ---------------------------------------------------------------------------

class TestStateFilter:
    def _setup(self, db):
        _insert(db, internal_id="C1", place_of_performance_state="TX", description="cleaning Texas", value=100000)
        _insert(db, internal_id="C2", place_of_performance_state="VA", description="IT Virginia", value=200000)
        _insert(db, internal_id="C3", place_of_performance_state="TX", description="grounds Texas", value=300000)

    def test_filter_by_state_tx(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(state="TX")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" in ids
        assert "C3" in ids
        assert "C2" not in ids

    def test_filter_by_state_va(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(state="VA")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C2" in ids
        assert "C1" not in ids

    def test_state_case_insensitive(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(state="tx")
        assert result["total"] == 2

    def test_state_and_category_combined(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(state="TX", category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" in ids
        assert "C3" not in ids

    def test_no_state_returns_all(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts()
        assert result["total"] == 3

    def test_nonexistent_state_returns_empty(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(state="ZZ")
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# TestFuzzySearchWithContext
# ---------------------------------------------------------------------------

class TestFuzzySearchWithContext:
    def _setup(self, db):
        _insert(db, internal_id="C1", description="janitorial cleaning services for federal buildings", vendor="Clean Co", value=100000)
        _insert(db, internal_id="C2", description="landscaping grounds maintenance lawn mowing", vendor="Grounds LLC", value=200000)
        _insert(db, internal_id="C3", description="information technology helpdesk support", vendor="Tech Corp", value=300000)
        _insert(db, internal_id="C4", description="cybersecurity operations center monitoring", vendor="SecureSys", value=400000)
        _insert(db, internal_id="C5", agency="DEPARTMENT OF DEFENSE", description="facility maintenance", vendor="Fac Services", value=500000)

    def test_search_cleaning(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" in ids

    def test_search_landscaping(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="landscaping")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C2" in ids

    def test_search_partial_prefix(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="cybersec")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C4" in ids

    def test_search_agency(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="defense")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C5" in ids

    def test_search_vendor(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="Clean")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" in ids

    def test_search_state_in_fts(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C10", place_of_performance_state="TX", description="services", value=100000)
        result = db.get_contracts(q="TX")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C10" in ids

    def test_empty_query_returns_all(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="")
        assert result["total"] == 5

    def test_punctuation_only_query_returns_nothing(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(q="&&&")
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# TestDiscoveryMode
# ---------------------------------------------------------------------------

class TestDiscoveryMode:
    def _setup(self, db):
        for i in range(1, 6):
            _insert(db, internal_id=f"C{i}", description=f"contract {i}", value=i * 100000)

    def test_exclude_ids_removes_pipeline_contracts(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(exclude_ids=["C1", "C2"])
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "C1" not in ids
        assert "C2" not in ids
        assert "C3" in ids

    def test_exclude_ids_empty_list_returns_all(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(exclude_ids=[])
        assert result["total"] == 5

    def test_exclude_ids_none_returns_all(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(exclude_ids=None)
        assert result["total"] == 5

    def test_exclude_all_returns_empty(self, tmp_path):
        db = _fresh_db(tmp_path)
        self._setup(db)
        result = db.get_contracts(exclude_ids=["C1", "C2", "C3", "C4", "C5"])
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# TestListContractStates
# ---------------------------------------------------------------------------

class TestListContractStates:
    def test_returns_distinct_states(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C1", place_of_performance_state="TX")
        _insert(db, internal_id="C2", place_of_performance_state="VA")
        _insert(db, internal_id="C3", place_of_performance_state="TX")
        states = db.list_contract_states()
        assert states == ["TX", "VA"]

    def test_excludes_null_and_empty(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C1", place_of_performance_state=None)
        _insert(db, internal_id="C2", place_of_performance_state="")
        _insert(db, internal_id="C3", place_of_performance_state="MD")
        states = db.list_contract_states()
        assert states == ["MD"]

    def test_sorted_alphabetically(self, tmp_path):
        db = _fresh_db(tmp_path)
        for s in ["TX", "AK", "MD", "CA"]:
            _insert(db, internal_id=f"C{s}", place_of_performance_state=s)
        states = db.list_contract_states()
        assert states == sorted(states)

    def test_empty_db_returns_empty_list(self, tmp_path):
        db = _fresh_db(tmp_path)
        assert db.list_contract_states() == []


# ---------------------------------------------------------------------------
# Shared fixture for route tests (auth required)
# ---------------------------------------------------------------------------

@pytest.fixture()
def _route_client(tmp_path):
    """Isolated db + logged-in Flask test client for route tests."""
    import app as flask_app

    db_module._cached_engine.cache_clear()
    db_module.DB_PATH = str(tmp_path / "test.db")
    db_module.init_db()

    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"

    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "tester@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        yield c


# ---------------------------------------------------------------------------
# TestContractsRoute
# ---------------------------------------------------------------------------

class TestContractsRoute:
    def test_contracts_page_loads(self, _route_client):
        rv = _route_client.get("/contracts")
        assert rv.status_code == 200

    def test_category_filter_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?category=Cleaning")
        assert rv.status_code == 200

    def test_state_filter_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?state=TX")
        assert rv.status_code == 200

    def test_discover_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?discover=1")
        assert rv.status_code == 200

    def test_search_query_accepted(self, _route_client):
        rv = _route_client.get("/contracts?q=cleaning+contracts+in+Texas")
        assert rv.status_code == 200


# ---------------------------------------------------------------------------
# TestContractDetailPage
# ---------------------------------------------------------------------------

class TestContractDetailPage:
    @pytest.fixture()
    def detail_client(self, tmp_path):
        import app as flask_app

        db_module._cached_engine.cache_clear()
        db_module.DB_PATH = str(tmp_path / "test.db")
        db_module.init_db()

        _insert(db_module,
                internal_id="DETAIL1",
                description="janitorial cleaning services for federal building",
                naics_code="561720",
                place_of_performance_state="VA",
                vendor="Clean Co",
                agency="GSA",
                value=250000)

        flask_app.app.config["TESTING"] = True
        flask_app.app.config["WTF_CSRF_ENABLED"] = False
        flask_app.app.config["RATELIMIT_ENABLED"] = False
        flask_app.app.secret_key = "test-secret-key"

        with flask_app.app.test_client() as c:
            c.post("/register", data={
                "email": "detail@example.com",
                "password": "password123",
                "confirm": "password123",
            })
            yield c

    def test_detail_page_loads(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert rv.status_code == 200

    def test_detail_shows_description(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert b"janitorial cleaning services" in rv.data

    def test_detail_shows_state(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert b"VA" in rv.data

    def test_detail_shows_naics(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert b"561720" in rv.data

    def test_detail_shows_category(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert b"Cleaning" in rv.data

    def test_detail_shows_vendor(self, detail_client):
        rv = detail_client.get("/contract/DETAIL1")
        assert b"Clean Co" in rv.data


# ---------------------------------------------------------------------------
# TestMigrationProbes
# ---------------------------------------------------------------------------

class TestMigrationProbes:
    def test_010_discovery_probe_exists(self):
        assert "010_discovery_columns.sql" in db_module._MIGRATION_PROBES

    def test_015_location_probe_exists(self):
        assert "015_location_columns.sql" in db_module._MIGRATION_PROBES

    def test_all_known_migrations_have_probes(self):
        import glob
        from pathlib import Path
        migrations_dir = Path(__file__).parent.parent / "migrations"
        sql_files = {Path(f).name for f in glob.glob(str(migrations_dir / "*.sql"))}
        for f in sql_files:
            assert f in db_module._MIGRATION_PROBES, f"Missing probe for {f}"


# ---------------------------------------------------------------------------
# TestNlQueryParser
# ---------------------------------------------------------------------------

class TestNlQueryParser:
    def test_lawn_care_maps_to_grounds(self):
        r = db_module.parse_nl_query("lawn care contracts")
        assert r.get("category") == "Grounds"

    def test_janitorial_services_maps_to_cleaning(self):
        r = db_module.parse_nl_query("janitorial services")
        assert r.get("category") == "Cleaning"

    def test_cybersecurity_maps_to_cybersecurity(self):
        r = db_module.parse_nl_query("cybersecurity contracts DOD")
        assert r.get("category") == "Cybersecurity"

    def test_it_support_maps_to_it(self):
        r = db_module.parse_nl_query("help desk it support services")
        assert r.get("category") == "IT"

    def test_grounds_maintenance_maps_to_grounds(self):
        r = db_module.parse_nl_query("grounds maintenance")
        assert r.get("category") == "Grounds"

    def test_state_name_extracted(self):
        r = db_module.parse_nl_query("cleaning contracts in Texas")
        assert r.get("state") == "TX"
        assert r.get("category") == "Cleaning"

    def test_state_name_without_in(self):
        r = db_module.parse_nl_query("Virginia landscaping")
        assert r.get("state") == "VA"
        assert r.get("category") == "Grounds"

    def test_multiword_state(self):
        r = db_module.parse_nl_query("contracts in New York")
        assert r.get("state") == "NY"

    def test_west_virginia_not_confused_with_virginia(self):
        r = db_module.parse_nl_query("contracts in West Virginia")
        assert r.get("state") == "WV"

    def test_q_remainder_strips_category_and_state(self):
        r = db_module.parse_nl_query("lawn care contracts in Virginia")
        assert r.get("category") == "Grounds"
        assert r.get("state") == "VA"
        assert r.get("q_remainder") == ""

    def test_q_remainder_preserves_non_category_terms(self):
        r = db_module.parse_nl_query("cybersecurity DOD")
        assert r.get("category") == "Cybersecurity"
        assert "dod" in r.get("q_remainder", "")

    def test_empty_query(self):
        r = db_module.parse_nl_query("")
        assert r.get("q_remainder") == ""
        assert "category" not in r
        assert "state" not in r

    def test_no_match_returns_original_q(self):
        r = db_module.parse_nl_query("defense contracts")
        assert "category" not in r
        assert "state" not in r


# ---------------------------------------------------------------------------
# TestCategoryFilterFixed (regression for double-AND bug)
# ---------------------------------------------------------------------------

class TestCategoryFilterFixed:
    """Regression tests for the double category filter bug.

    Previously get_contracts(category=X) applied TWO AND conditions:
    description LIKE AND c.category = X. This caused NAICS-classified contracts
    (category set but no keyword in description) to return 0 results.
    """

    def test_naics_classified_contract_found_by_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        # Insert contract classified via NAICS — description has NO lawn/grounds keyword
        _insert(db, internal_id="N1", description="Exterior property services",
                naics_code="561730", value=300000)
        result = db.get_contracts(category="Grounds")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "N1" in ids

    def test_keyword_classified_contract_found_by_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="K1", description="janitorial cleaning services", value=100000)
        result = db.get_contracts(category="Cleaning")
        assert result["total"] >= 1
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "K1" in ids

    def test_category_filter_does_not_return_wrong_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C1", description="janitorial cleaning services", value=100000)
        _insert(db, internal_id="G1", description="grounds maintenance", value=200000)
        cleaning = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in cleaning["contracts"]]
        assert "C1" in ids
        assert "G1" not in ids


# ---------------------------------------------------------------------------
# TestCategoryFilterCaseSensitivity
# ---------------------------------------------------------------------------

class TestCategoryFilterCaseSensitivity:
    """Regression for PostgreSQL LIKE case-sensitivity.

    USASpending returns descriptions in ALL-CAPS ("JANITORIAL SERVICES FOR
    FEDERAL BUILDINGS"). In SQLite LIKE is case-insensitive for ASCII, but this
    test verifies the filter logic handles uppercase descriptions correctly so
    the same path works on both SQLite (dev) and PostgreSQL (prod).
    """

    def test_uppercase_description_cleaning(self, tmp_path):
        db = _fresh_db(tmp_path)
        # Force category to NULL so only description LIKE kicks in
        _insert(db, internal_id="U1", description="JANITORIAL SERVICES FOR FEDERAL BUILDINGS",
                value=100000)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "U1" in ids, "Uppercase JANITORIAL description must match Cleaning filter"

    def test_uppercase_description_grounds(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="U2", description="GROUNDS MAINTENANCE AND LANDSCAPING",
                value=200000)
        result = db.get_contracts(category="Grounds")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "U2" in ids, "Uppercase GROUNDS description must match Grounds filter"

    def test_uppercase_description_it(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="U3", description="INFORMATION TECHNOLOGY HELP DESK SUPPORT",
                value=300000)
        result = db.get_contracts(category="IT")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "U3" in ids

    def test_mixed_case_description_cleaning(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="U4", description="Custodial Services - Building 7",
                value=150000)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "U4" in ids

    def test_cleaning_nonzero_rows_when_data_exists(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="NZ1", description="JANITORIAL AND CUSTODIAL SERVICES", value=100000)
        _insert(db, internal_id="NZ2", description="LANDSCAPING SERVICES", value=200000)
        result = db.get_contracts(category="Cleaning")
        assert result["total"] >= 1, "Category=Cleaning must return nonzero rows when matching data exists"

    def test_category_alias_cleaning_janitorial(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="A1", description="janitorial cleaning services", value=100000)
        result = db.get_contracts(category="Cleaning / Janitorial")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "A1" in ids, "Alias 'Cleaning / Janitorial' must resolve to Cleaning"

    def test_category_alias_janitorial_alone(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="A2", description="janitorial services for offices", value=100000)
        result = db.get_contracts(category="Janitorial")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "A2" in ids, "Alias 'Janitorial' must resolve to Cleaning"

    def test_category_combined_with_state(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="CS1", description="JANITORIAL SERVICES", place_of_performance_state="VA", value=100000)
        _insert(db, internal_id="CS2", description="JANITORIAL SERVICES", place_of_performance_state="TX", value=100000)
        result = db.get_contracts(category="Cleaning", state="VA")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "CS1" in ids
        assert "CS2" not in ids

    def test_naics_cleaning_found_by_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        # NAICS 5617 = Cleaning; description does not contain any keyword
        _insert(db, internal_id="NC1", description="Federal building services", naics_code="561720", value=100000)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "NC1" in ids, "NAICS 5617x contract must match Cleaning filter"

    def test_no_double_min_value_filter(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="MV1", description="janitorial cleaning", value=500000)
        _insert(db, internal_id="MV2", description="janitorial cleaning", value=1500000)
        result = db.get_contracts(category="Cleaning", min_value=1000000)
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "MV1" not in ids
        assert "MV2" in ids


# ---------------------------------------------------------------------------
# TestLocationColumns
# ---------------------------------------------------------------------------

class TestLocationColumns:
    def test_city_stored_at_ingest(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="L1", performance_city="Arlington", place_of_performance_state="VA")
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT place_of_performance_city FROM contracts WHERE internal_id = 'L1'")
            ).fetchone()
        assert row[0] == "Arlington"

    def test_zip_stored_at_ingest(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="L2", performance_zip="22201", place_of_performance_state="VA")
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT place_of_performance_zip FROM contracts WHERE internal_id = 'L2'")
            ).fetchone()
        assert row[0] == "22201"

    def test_city_zip_via_save_snapshot(self, tmp_path):
        db = _fresh_db(tmp_path)
        db.save_snapshot("2024-01-01", [{
            "internal_id": "L3",
            "vendor": "City Vendor",
            "agency": "GSA",
            "description": "cleaning services",
            "value": 150000,
            "days_remaining": 60,
            "recompete_score": 55,
            "priority": "MEDIUM",
            "performance_city": "Denver",
            "performance_zip": "80202",
            "place_of_performance_state": "CO",
        }])
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT place_of_performance_city, place_of_performance_zip FROM contracts WHERE internal_id = 'L3'")
            ).fetchone()
        assert row[0] == "Denver"
        assert row[1] == "80202"

    def test_city_searchable_via_fts(self, tmp_path):
        db = _fresh_db(tmp_path)
        db.save_snapshot("2024-01-01", [{
            "internal_id": "L4",
            "vendor": "Arlington Cleaning",
            "agency": "GSA",
            "description": "cleaning services",
            "value": 200000,
            "days_remaining": 90,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "performance_city": "Springfield",
            "place_of_performance_state": "VA",
        }])
        result = db.get_contracts(q="Springfield")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "L4" in ids
