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


# ---------------------------------------------------------------------------
# TestPscDescriptionFilter
# ---------------------------------------------------------------------------

class TestPscDescriptionFilter:
    """Tests that psc_description is used for category inference and filtering.

    Many USASpending contracts have vague descriptions ("DORM MANAGEMENT
    SERVICES") but a clear PSC product/service code description
    ("HOUSEKEEPING- CUSTODIAL JANITORIAL"). Without psc_description in the
    filter these contracts return 0 results for category=Cleaning.
    """

    def test_infer_category_from_psc_description(self):
        result = db_module.infer_category(
            description="DORM MANAGEMENT SERVICES",
            psc_description="HOUSEKEEPING- CUSTODIAL JANITORIAL",
        )
        assert result == "Cleaning"

    def test_infer_category_psc_overrides_other_when_description_vague(self):
        assert db_module.infer_category(
            description="SUPPORT SERVICES CONTRACT",
            psc_description="CUSTODIAL SERVICES FEDERAL BUILDING",
        ) == "Cleaning"

    def test_infer_category_psc_grounds(self):
        assert db_module.infer_category(
            description="SITE SERVICES BASE SUPPORT",
            psc_description="GROUNDS MAINTENANCE AND LANDSCAPING SERVICES",
        ) == "Grounds"

    def test_psc_description_stored_as_column(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="P1",
                description="DORM MANAGEMENT SERVICES",
                psc_description="HOUSEKEEPING- CUSTODIAL JANITORIAL",
                value=100000)
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT psc_description FROM contracts WHERE internal_id = 'P1'")
            ).fetchone()
        assert row[0] == "HOUSEKEEPING- CUSTODIAL JANITORIAL"

    def test_psc_description_stored_via_save_snapshot(self, tmp_path):
        db = _fresh_db(tmp_path)
        db.save_snapshot("2024-01-01", [{
            "internal_id": "P2",
            "vendor": "Federal Cleaning Inc",
            "agency": "GSA",
            "description": "DORM MANAGEMENT SERVICES",
            "psc_description": "HOUSEKEEPING- CUSTODIAL JANITORIAL",
            "value": 200000,
            "days_remaining": 90,
            "recompete_score": 60,
            "priority": "MEDIUM",
        }])
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT psc_description, category FROM contracts WHERE internal_id = 'P2'")
            ).fetchone()
        assert row[0] == "HOUSEKEEPING- CUSTODIAL JANITORIAL"
        assert row[1] == "Cleaning"

    def test_category_filter_finds_contract_by_psc_description_column(self, tmp_path):
        """Contract with vague description but psc_description='JANITORIAL...' must match Cleaning."""
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="P3",
                description="DORM MANAGEMENT SERVICES",
                psc_description="HOUSEKEEPING- CUSTODIAL JANITORIAL",
                value=100000)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "P3" in ids, "Contract with cleaning PSC description must match category=Cleaning"

    def test_category_filter_excludes_non_cleaning_psc(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="P4",
                description="IT SUPPORT SERVICES",
                psc_description="INFORMATION TECHNOLOGY SUPPORT",
                value=100000)
        result = db.get_contracts(category="Cleaning")
        ids = [r["internal_id"] for r in result["contracts"]]
        assert "P4" not in ids

    def test_category_inferred_from_psc_at_ingest(self, tmp_path):
        """When description is vague but psc_description has cleaning keyword,
        infer_category should classify the contract as Cleaning at upsert time."""
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="P5",
                description="BASE SUPPORT SERVICES",
                psc_description="CUSTODIAL SERVICES - BARRACKS",
                value=150000)
        with db.get_engine().connect() as conn:
            row = conn.execute(
                db.text("SELECT category FROM contracts WHERE internal_id = 'P5'")
            ).fetchone()
        assert row[0] == "Cleaning", "infer_category must use psc_description to classify as Cleaning"


# ---------------------------------------------------------------------------
# TestMinDaysLeftFilter
# ---------------------------------------------------------------------------

class TestMinDaysLeftFilter:
    """get_contracts(min_days_left=N) filters to contracts with days_remaining >= N.

    Combines cleanly with the existing ``days`` (expiring_within) parameter so
    callers can express a range: 90 <= days_remaining <= 365.
    """

    @pytest.fixture()
    def db(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="C10", days_remaining=20)
        _insert(db, internal_id="C60", days_remaining=60)
        _insert(db, internal_id="C90", days_remaining=90)
        _insert(db, internal_id="C180", days_remaining=180)
        _insert(db, internal_id="C365", days_remaining=365)
        return db

    def _ids(self, result):
        return {r["internal_id"] for r in result["contracts"]}

    def test_no_filter_returns_all(self, db):
        result = db.get_contracts(min_days_left=None)
        assert self._ids(result) == {"C10", "C60", "C90", "C180", "C365"}

    def test_min_30_excludes_short_runway(self, db):
        result = db.get_contracts(min_days_left=30)
        ids = self._ids(result)
        assert "C10" not in ids
        assert {"C60", "C90", "C180", "C365"}.issubset(ids)

    def test_min_90_exact_boundary_included(self, db):
        result = db.get_contracts(min_days_left=90)
        ids = self._ids(result)
        assert "C10" not in ids
        assert "C60" not in ids
        assert "C90" in ids
        assert "C180" in ids
        assert "C365" in ids

    def test_min_365_returns_only_longest(self, db):
        result = db.get_contracts(min_days_left=365)
        assert self._ids(result) == {"C365"}

    def test_min_days_combined_with_expiring_within(self, db):
        # min_days_left=90 + days=365 → contracts with 90 <= days_remaining <= 365
        result = db.get_contracts(min_days_left=90, days=365)
        ids = self._ids(result)
        assert "C10" not in ids
        assert "C60" not in ids
        assert "C90" in ids
        assert "C180" in ids
        assert "C365" in ids

    def test_impossible_range_returns_empty(self, db):
        # min=365 and expiring_within=90 → no contract can have 365 <= d <= 90
        result = db.get_contracts(min_days_left=365, days=90)
        assert result["total"] == 0

    def test_min_zero_returns_all(self, db):
        result = db.get_contracts(min_days_left=0)
        assert self._ids(result) == {"C10", "C60", "C90", "C180", "C365"}


class TestMinDaysLeftRoute:
    """Route-level tests for the min_days_left query parameter."""

    def test_min_days_left_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?min_days_left=90")
        assert rv.status_code == 200

    def test_min_days_left_zero_accepted(self, _route_client):
        rv = _route_client.get("/contracts?min_days_left=0")
        assert rv.status_code == 200

    def test_min_days_left_negative_returns_400(self, _route_client):
        rv = _route_client.get("/contracts?min_days_left=-1")
        assert rv.status_code == 400

    def test_min_days_left_combined_with_days(self, _route_client):
        rv = _route_client.get("/contracts?min_days_left=90&days=365")
        assert rv.status_code == 200

    def test_min_days_left_in_page_html(self, _route_client):
        rv = _route_client.get("/contracts?min_days_left=90")
        assert b"min_days_left" in rv.data

    def test_state_dropdown_renders(self, _route_client):
        rv = _route_client.get("/contracts")
        assert b"All states" in rv.data

    def test_state_dropdown_empty_shows_no_data_hint(self, _route_client):
        # Empty DB → no state options → should show the "No state data yet" hint
        rv = _route_client.get("/contracts")
        assert b"No state data yet" in rv.data

    def test_state_dropdown_shows_options_when_contracts_have_state(self, _route_client):
        # Insert a contract with a state; dropdown must show that state as an option.
        db_module.upsert_contract({
            "internal_id": "STATE-VA",
            "award_id": "AW-STATE-VA",
            "vendor": "Virginia Services LLC",
            "agency": "GSA",
            "value": 200000,
            "days_remaining": 180,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "place_of_performance_state": "VA",
        })
        rv = _route_client.get("/contracts")
        assert b'value="VA"' in rv.data
        assert b"No state data yet" not in rv.data

    def test_state_dropdown_selected_value_preserved(self, _route_client):
        # When state=VA is in the URL, the VA option must be marked selected.
        db_module.upsert_contract({
            "internal_id": "STATE-VA2",
            "award_id": "AW-STATE-VA2",
            "vendor": "Virginia Services LLC",
            "agency": "GSA",
            "value": 200000,
            "days_remaining": 180,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "place_of_performance_state": "VA",
        })
        rv = _route_client.get("/contracts?state=VA")
        assert b'value="VA" selected' in rv.data or b"VA" in rv.data
        assert rv.status_code == 200

    def test_state_filter_param_preserved_in_response(self, _route_client):
        rv = _route_client.get("/contracts?state=TX")
        assert rv.status_code == 200


# ---------------------------------------------------------------------------
# TestNaicsFilter
# ---------------------------------------------------------------------------

class TestNaicsFilter:
    """get_contracts(naics_code=X) filters by prefix match on c.naics_code."""

    @pytest.fixture()
    def db(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="N561720", naics_code="561720", description="janitorial services")
        _insert(db, internal_id="N561730", naics_code="561730", description="lawn mowing")
        _insert(db, internal_id="N541512", naics_code="541512", description="it support")
        _insert(db, internal_id="NNONE",   naics_code=None,     description="misc services")
        return db

    def _ids(self, result):
        return {r["internal_id"] for r in result["contracts"]}

    def test_exact_naics_match(self, db):
        result = db.get_contracts(naics_code="561720")
        assert self._ids(result) == {"N561720"}

    def test_prefix_4digit_matches_6digit(self, db):
        result = db.get_contracts(naics_code="5617")
        assert {"N561720", "N561730"}.issubset(self._ids(result))
        assert "N541512" not in self._ids(result)

    def test_prefix_3digit(self, db):
        result = db.get_contracts(naics_code="561")
        ids = self._ids(result)
        assert "N561720" in ids
        assert "N561730" in ids
        assert "N541512" not in ids

    def test_no_naics_filter_returns_all(self, db):
        result = db.get_contracts(naics_code="")
        assert result["total"] == 4

    def test_nonexistent_naics_returns_empty(self, db):
        result = db.get_contracts(naics_code="999999")
        assert result["total"] == 0

    def test_naics_combined_with_state(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="NS1", naics_code="561720", place_of_performance_state="VA")
        _insert(db, internal_id="NS2", naics_code="561720", place_of_performance_state="TX")
        result = db.get_contracts(naics_code="561720", state="VA")
        ids = self._ids(result)
        assert "NS1" in ids
        assert "NS2" not in ids

    def test_naics_combined_with_category(self, tmp_path):
        db = _fresh_db(tmp_path)
        _insert(db, internal_id="NC1", naics_code="561720", description="janitorial cleaning")
        _insert(db, internal_id="NC2", naics_code="541512", description="it support services")
        result = db.get_contracts(naics_code="5617", category="Cleaning")
        ids = self._ids(result)
        assert "NC1" in ids
        assert "NC2" not in ids

    def test_naics_null_not_matched_by_prefix(self, db):
        result = db.get_contracts(naics_code="561720")
        assert "NNONE" not in self._ids(result)


class TestNaicsFilterRoute:
    """Route-level smoke tests for /contracts?naics_code=..."""

    def test_naics_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=561720")
        assert rv.status_code == 200

    def test_naics_input_rendered_in_page(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=561720")
        assert b"561720" in rv.data

    def test_naics_empty_param_accepted(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=")
        assert rv.status_code == 200

    def test_naics_combined_with_state(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=5617&state=VA")
        assert rv.status_code == 200

    def test_naics_chip_shown_when_active(self, _route_client):
        db_module.upsert_contract({
            "internal_id": "NAICS-CHIP",
            "award_id": "AW-NAICS-CHIP",
            "vendor": "Test Vendor",
            "agency": "GSA",
            "value": 200000,
            "days_remaining": 180,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "naics_code": "561720",
        })
        rv = _route_client.get("/contracts?naics_code=561720")
        assert b"NAICS" in rv.data

    def test_empty_naics_produces_no_chip(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=")
        assert rv.status_code == 200
        # No chip should appear for blank NAICS
        html = rv.data.decode()
        # The active-filter-chip label "NAICS:" only appears when the chip is present
        assert "NAICS: <strong>" not in html

    def test_naics_combined_with_q_and_category(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=5617&q=cleaning&category=Cleaning")
        assert rv.status_code == 200

    def test_naics_combined_with_status_and_sort(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=541512&status=open&sort=value&dir=desc")
        assert rv.status_code == 200

    def test_naics_preserved_in_for_my_business_url(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=561720")
        assert rv.status_code == 200
        html = rv.data.decode()
        # For My Business toggle link must carry naics_code forward
        assert "naics_code=561720" in html

    def test_naics_preserved_in_sort_links(self, _route_client):
        rv = _route_client.get("/contracts?naics_code=561720")
        assert rv.status_code == 200
        html = rv.data.decode()
        # Sort column links must include naics_code so it survives a sort change
        assert "naics_code=561720" in html


# ---------------------------------------------------------------------------
# TestNaicsChipLogic (unit tests against views.active_filter_chips)
# ---------------------------------------------------------------------------

class TestNaicsChipLogic:
    """Unit tests for chip building and remove-URL logic for naics_code."""

    def test_naics_chip_built_when_present(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": "561720"})
        assert any(c["key"] == "naics_code" for c in chips)

    def test_naics_chip_label(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": "561720"})
        chip = next(c for c in chips if c["key"] == "naics_code")
        assert chip["label"] == "NAICS"
        assert chip["value"] == "561720"

    def test_naics_chip_remove_url_drops_naics_only(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": "561720", "state": "VA", "category": "Cleaning"})
        chip = next(c for c in chips if c["key"] == "naics_code")
        # remove_url must not contain naics_code
        assert "naics_code" not in chip["remove_url"]
        # but must still contain the other filters
        assert "state=VA" in chip["remove_url"]
        assert "category=Cleaning" in chip["remove_url"]

    def test_removing_state_chip_preserves_naics(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": "561720", "state": "VA"})
        state_chip = next(c for c in chips if c["key"] == "state")
        assert "naics_code=561720" in state_chip["remove_url"]
        assert "state" not in state_chip["remove_url"]

    def test_empty_naics_produces_no_chip(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": ""})
        assert not any(c["key"] == "naics_code" for c in chips)

    def test_whitespace_naics_produces_no_chip(self):
        from views import active_filter_chips
        chips = active_filter_chips({"naics_code": "  "})
        assert not any(c["key"] == "naics_code" for c in chips)
