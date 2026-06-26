"""Focused tests for the Lead Intelligence feature.

Covers the pure deterministic module (lead_intelligence.py), the DB import/match
helpers, the migration probe + SQLite self-heal, and the protected route.
"""

import pytest
from sqlalchemy import text

import db as db_module
import lead_intelligence as li
from app import app as flask_app


# ---------------------------------------------------------------------------
# Pure module: inference
# ---------------------------------------------------------------------------

class TestServiceCategoryInference:
    def test_cybersecurity(self):
        assert li.infer_service_category("Offensive cyber and SOC monitoring", "Acme") == "cybersecurity"

    def test_it(self):
        assert li.infer_service_category("Managed help desk and cloud network support", "Acme") == "it"

    def test_janitorial(self):
        assert li.infer_service_category("Commercial janitorial and custodial crews", "Acme") == "janitorial_facilities"

    def test_logistics(self):
        assert li.infer_service_category("Supply chain and warehousing", "Acme") == "logistics"

    def test_health(self):
        assert li.infer_service_category("Clinical nursing staffing", "Acme") == "health"

    def test_partner_fallback(self):
        assert li.infer_service_category("Channel reseller partner", "Acme") == "partner"

    def test_unknown(self):
        assert li.infer_service_category("", "") == "unknown"


class TestStateExtraction:
    def test_em_dash_city_state(self):
        assert li.infer_company_state("Acme Corp — Richmond, VA") == "VA"

    def test_spaced_hyphen(self):
        assert li.infer_company_state("Acme Corp - Austin, TX") == "TX"

    def test_state_before_zip(self):
        assert li.infer_company_state("123 Main St, Arlington VA 22201") == "VA"

    def test_from_notes_fallback(self):
        assert li.infer_company_state("Acme Corp", "HQ in Columbia, MD") == "MD"

    def test_none_when_absent(self):
        assert li.infer_company_state("Acme Corp", "no location here") is None

    def test_rejects_non_state_pair(self):
        # "zz" is not a valid state token in a comma context
        assert li.infer_company_state("Doing, zz work") is None


class TestLikelyCustomerScore:
    def test_strong_prospect_scores_high(self):
        company = {
            "company_name": "FedTech LLC",
            "service_notes": "Federal IT contractor, GSA schedule holder, sells to DoD agencies",
            "state": "VA",
            "email": "sales@fedtech.com",
            "inferred_service_category": "it",
        }
        assert li.score_likely_customer(company) >= 85

    def test_weak_prospect_scores_low(self):
        company = {
            "company_name": "Local Bakery",
            "service_notes": "neighborhood bakery",
            "state": "OR",
            "inferred_service_category": "unknown",
        }
        assert li.score_likely_customer(company) < 30

    def test_score_capped_at_100(self):
        company = {
            "company_name": "MegaFed",
            "service_notes": "federal government contractor GSA DoD partner channel reseller public sector",
            "state": "DC",
            "email": "x@y.com",
            "phone": "555",
            "inferred_service_category": "it",
        }
        assert li.score_likely_customer(company) <= 100


# ---------------------------------------------------------------------------
# Pure module: contract fit scoring
# ---------------------------------------------------------------------------

def _it_company():
    return {"company_name": "Acme IT", "inferred_service_category": "it",
            "state": "VA", "service_notes": "federal IT services"}


def _contract(**kw):
    base = {
        "internal_id": "C1", "award_id": "A1", "vendor": "Incumbent",
        "agency": "Army", "category": "IT", "value": 1_000_000,
        "description": "cloud network and help desk services",
        "place_of_performance_state": "VA", "days_remaining": 180,
        "recompete_score": 50, "naics_code": "541512",
    }
    base.update(kw)
    return base


class TestContractFit:
    def test_same_state_and_service_scores_well(self):
        scores = li.score_contract_fit(_it_company(), _contract())
        assert scores["service_score"] > 0
        assert scores["state_score"] == 25
        assert scores["timing_score"] == 20
        assert scores["match_score"] >= 60

    def test_rewards_same_state_over_other_state(self):
        same = li.score_contract_fit(_it_company(), _contract(place_of_performance_state="VA"))
        other = li.score_contract_fit(_it_company(), _contract(place_of_performance_state="TX",
                                                               internal_id="C2"))
        assert same["match_score"] > other["match_score"]

    def test_rewards_matching_service_category(self):
        it_fit = li.score_contract_fit(_it_company(), _contract())
        cleaning = _contract(category="Cleaning", description="janitorial custodial",
                             naics_code="561720", internal_id="C3")
        cleaning_fit = li.score_contract_fit(_it_company(), cleaning)
        assert it_fit["service_score"] > cleaning_fit["service_score"]

    def test_penalizes_expired_contract(self):
        live = li.score_contract_fit(_it_company(), _contract(days_remaining=180))
        expired = li.score_contract_fit(_it_company(), _contract(days_remaining=-10,
                                                                 internal_id="C4"))
        assert expired["penalty"] > 0
        assert expired["match_score"] < live["match_score"]

    def test_penalizes_too_late_contract(self):
        live = li.score_contract_fit(_it_company(), _contract(days_remaining=180))
        too_late = li.score_contract_fit(_it_company(), _contract(days_remaining=20,
                                                                  internal_id="C5"))
        assert too_late["penalty"] > 0
        assert too_late["match_score"] < live["match_score"]


class TestFindMatching:
    def test_sorts_and_limits(self):
        company = _it_company()
        contracts = [
            _contract(internal_id="good", place_of_performance_state="VA"),
            _contract(internal_id="meh", place_of_performance_state="TX",
                      category="Cleaning", description="janitorial", naics_code="561720"),
            _contract(internal_id="expired", days_remaining=-5),
        ]
        matches = li.find_matching_contracts(company, contracts, limit=2)
        assert len(matches) <= 2
        assert matches[0]["contract"]["internal_id"] == "good"

    def test_outreach_angle_mentions_top_contract(self):
        company = _it_company()
        matches = li.find_matching_contracts(company, [_contract(agency="Navy")], limit=3)
        angle = li.generate_outreach_angle(company, matches)
        assert "Navy" in angle

    def test_outreach_angle_handles_no_matches(self):
        angle = li.generate_outreach_angle(_it_company(), [])
        assert isinstance(angle, str) and angle


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

class TestCsvParsing:
    # Company / Name fields contain commas, so they are quoted as a real CSV
    # export would be.
    CSV = (
        "Rank,Company,Name / Title,Phone,Email,Contact Type,Notes\n"
        '1,"Acme IT — Arlington, VA","Jane Doe / VP Sales",555-1212,jane@acme.com,Prospect,'
        "Federal IT managed services and help desk\n"
        '2,"CleanCo — Austin, TX",Bob Smith,555-3434,bob@cleanco.com,Lead,Janitorial and custodial\n'
    )

    def test_parses_company_and_state(self):
        leads = li.parse_leads_csv(self.CSV)
        assert len(leads) == 2
        acme = leads[0]
        assert acme["company_name"] == "Acme IT"
        assert acme["state"] == "VA"
        assert acme["company_location"] == "Acme IT — Arlington, VA"

    def test_splits_name_title(self):
        acme = li.parse_leads_csv(self.CSV)[0]
        assert acme["contact_name"] == "Jane Doe"
        assert acme["contact_title"] == "VP Sales"

    def test_infers_category_and_score(self):
        leads = li.parse_leads_csv(self.CSV)
        assert leads[0]["inferred_service_category"] == "it"
        assert leads[1]["inferred_service_category"] == "janitorial_facilities"
        assert leads[0]["likely_customer_score"] > 0

    def test_empty_input(self):
        assert li.parse_leads_csv("") == []
        assert li.parse_leads_csv("   ") == []


# ---------------------------------------------------------------------------
# DB layer + migration probe / self-heal
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    yield db_path
    db_module._cached_engine.cache_clear()


def _tables(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()
    return {r[0] for r in rows}


class TestMigrationAndSelfHeal:
    def test_migration_probe_registered(self):
        assert "020_lead_intelligence.sql" in db_module._MIGRATION_PROBES
        assert "lead_companies" in db_module._MIGRATION_PROBES["020_lead_intelligence.sql"]

    def test_self_heal_creates_tables_on_fresh_sqlite(self, sqlite_db):
        db_module.init_lead_intelligence_tables()
        tables = _tables(db_module.get_engine())
        assert "lead_companies" in tables
        assert "lead_contract_matches" in tables

    def test_init_db_creates_lead_tables(self, sqlite_db):
        db_module.init_db()
        assert "lead_companies" in _tables(db_module.get_engine())

    def test_idempotent(self, sqlite_db):
        db_module.init_lead_intelligence_tables()
        db_module.init_lead_intelligence_tables()  # must not raise

    def test_021_probe_registered(self):
        assert "021_lead_outreach_tracking.sql" in db_module._MIGRATION_PROBES
        assert "contacted_status" in db_module._MIGRATION_PROBES["021_lead_outreach_tracking.sql"]

    def test_legacy_table_gets_new_columns_and_preserves_rows(self, sqlite_db):
        """A pre-021 lead_companies table self-heals without losing prospects."""
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE lead_companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL UNIQUE,
                    likely_customer_score INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.execute(text(
                "INSERT INTO lead_companies (company_name, likely_customer_score) "
                "VALUES ('Legacy Co', 55)"
            ))
        cols = {r[1] for r in engine.connect().execute(text("PRAGMA table_info(lead_companies)"))}
        assert "contacted_status" not in cols

        db_module.init_lead_intelligence_tables()

        cols = {r[1] for r in engine.connect().execute(text("PRAGMA table_info(lead_companies)"))}
        assert {"contacted_status", "outreach_notes", "normalized_name"} <= cols
        # Existing prospect row preserved, defaulting to not_contacted.
        row = engine.connect().execute(text(
            "SELECT company_name, contacted_status FROM lead_companies WHERE company_name='Legacy Co'"
        )).fetchone()
        assert row[0] == "Legacy Co"
        assert row[1] == "not_contacted"


class TestImportAndMatch:
    def test_import_upserts_and_matches(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "X1", "vendor": "OldVendor", "agency": "Army",
            "category": "IT", "description": "cloud network help desk services",
            "value": 1_000_000, "place_of_performance_state": "VA",
            "days_remaining": 180, "recompete_score": 70, "naics_code": "541512",
        })
        leads = li.parse_leads_csv(TestCsvParsing.CSV)
        result = db_module.import_leads(leads)
        assert result["new"] == 2
        assert result["updated"] == 0

        overview = db_module.get_lead_intelligence_overview()
        names = {c["company_name"] for c in overview}
        assert "Acme IT" in names
        acme = next(c for c in overview if c["company_name"] == "Acme IT")
        assert acme["matches"], "Acme IT (federal IT, VA) should match the VA IT contract"
        assert acme["matches"][0]["internal_id"] == "X1"

    def test_reimport_is_idempotent_on_company(self, sqlite_db):
        db_module.init_db()
        leads = li.parse_leads_csv(TestCsvParsing.CSV)
        db_module.import_leads(leads)
        db_module.import_leads(leads)
        overview = db_module.get_lead_intelligence_overview()
        assert len([c for c in overview if c["company_name"] == "Acme IT"]) == 1


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(sqlite_db, monkeypatch):
    db_module.init_db()
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.secret_key = "test-secret-key"
    # Lead Intelligence is admin-only (global data); make the test user an admin.
    monkeypatch.setenv("ADMIN_EMAILS", "leadtest@example.com")
    with flask_app.test_client() as c:
        c.post("/register", data={
            "email": "leadtest@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


class TestRoute:
    def test_requires_login(self):
        flask_app.config["TESTING"] = True
        with flask_app.test_client() as c:
            resp = c.get("/lead-intelligence")
            assert resp.status_code in (301, 302)
            assert "/login" in resp.headers.get("Location", "")

    def test_renders_for_authenticated_user(self, client):
        resp = client.get("/lead-intelligence")
        assert resp.status_code == 200
        assert b"Lead Intelligence" in resp.data

    def test_non_admin_forbidden(self, sqlite_db, monkeypatch):
        """A logged-in non-admin must not see global lead data (admin-only)."""
        db_module.init_db()
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        flask_app.secret_key = "test-secret-key"
        monkeypatch.setenv("ADMIN_EMAILS", "someone-else@example.com")
        with flask_app.test_client() as c:
            c.post("/register", data={
                "email": "regular@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
            with c.session_transaction() as sess:
                sess["onboarding_skipped"] = "1"
            resp = c.get("/lead-intelligence")
            assert resp.status_code == 403
            resp2 = c.post("/lead-intelligence/import", data={"csv_text": "Company\nAcme"})
            assert resp2.status_code == 403

    def test_import_flow(self, client, sqlite_db):
        db_module.upsert_contract({
            "internal_id": "X1", "vendor": "OldVendor", "agency": "Army",
            "category": "IT", "description": "cloud network help desk services",
            "value": 1_000_000, "place_of_performance_state": "VA",
            "days_remaining": 180, "recompete_score": 70, "naics_code": "541512",
        })
        resp = client.post("/lead-intelligence/import", data={
            "csv_text": TestCsvParsing.CSV,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Acme IT" in resp.data


# ---------------------------------------------------------------------------
# Workbench: filter / sort / next-action / skipped-count flash
# ---------------------------------------------------------------------------

class TestWorkbench:
    """Tests for the compact workbench layout added on top of the base MVP."""

    def test_compact_layout_has_no_table_element(self, client):
        resp = client.get("/lead-intelligence")
        assert resp.status_code == 200
        body = resp.data.decode()
        # The new workbench uses card layout, not a wide <table>
        assert "<table>" not in body

    def test_filter_params_accepted_without_error(self, client):
        resp = client.get("/lead-intelligence?service=it&state=VA&likelihood=40&confidence=high&sort=state")
        assert resp.status_code == 200

    def test_sort_params_accepted_without_error(self, client):
        for sort in ("score", "service", "state"):
            resp = client.get(f"/lead-intelligence?sort={sort}")
            assert resp.status_code == 200

    def test_clear_filters_link_present_when_filter_active(self, client):
        resp = client.get("/lead-intelligence?service=it")
        body = resp.data.decode()
        assert "Clear filters" in body

    def test_no_clear_filters_link_when_no_filter(self, client):
        resp = client.get("/lead-intelligence")
        body = resp.data.decode()
        assert "Clear filters" not in body

    def test_import_flash_shows_skipped_count(self, client, sqlite_db):
        db_module.upsert_contract({
            "internal_id": "WB1", "vendor": "Vendor", "agency": "DoD",
            "category": "IT", "description": "cloud services",
            "value": 500_000, "place_of_performance_state": "VA",
            "days_remaining": 200, "recompete_score": 70, "naics_code": "541512",
        })
        csv = "Company,Email\nGood Corp,g@g.com\n,blank@x.com\n"
        resp = client.post("/lead-intelligence/import", data={"csv_text": csv},
                           follow_redirects=True)
        body = resp.data.decode()
        assert "Skipped 1 row" in body

    def test_import_flash_imported_count(self, client, sqlite_db):
        db_module.upsert_contract({
            "internal_id": "WB2", "vendor": "Vendor", "agency": "DoD",
            "category": "IT", "description": "cloud services",
            "value": 500_000, "place_of_performance_state": "VA",
            "days_remaining": 200, "recompete_score": 70, "naics_code": "541512",
        })
        csv = "Company,Email\nAlpha Corp,a@a.com\nBeta Corp,b@b.com\n"
        resp = client.post("/lead-intelligence/import", data={"csv_text": csv},
                           follow_redirects=True)
        body = resp.data.decode()
        assert "Imported 2 prospects" in body

    def test_next_action_badge_present(self, client, sqlite_db):
        db_module.upsert_contract({
            "internal_id": "WB3", "vendor": "Vendor", "agency": "DoD",
            "category": "IT", "description": "cloud network help desk services",
            "value": 1_000_000, "place_of_performance_state": "VA",
            "days_remaining": 200, "recompete_score": 80, "naics_code": "541512",
        })
        client.post("/lead-intelligence/import", data={
            "csv_text": "Company,Email,State\nFedTech LLC,cto@fedtech.com,VA\n"
        }, follow_redirects=True)
        resp = client.get("/lead-intelligence")
        body = resp.data.decode()
        assert ("Contact now" in body or "Research first" in body or "Low confidence" in body)

    def test_top_contract_preview_visible(self, client, sqlite_db):
        db_module.upsert_contract({
            "internal_id": "WB4", "vendor": "Incumbent Co", "agency": "Army",
            "category": "IT", "description": "cloud network services",
            "value": 800_000, "place_of_performance_state": "VA",
            "days_remaining": 180, "recompete_score": 75, "naics_code": "541512",
        })
        client.post("/lead-intelligence/import", data={
            "csv_text": "Company,Email,State\nCloud IT Corp,x@x.com,VA\n"
        }, follow_redirects=True)
        resp = client.get("/lead-intelligence")
        body = resp.data.decode()
        assert "Top contract" in body

    def test_empty_state_shows_import_prompt(self, client):
        resp = client.get("/lead-intelligence")
        body = resp.data.decode()
        # Either has prospects or shows the empty state / import accordion
        assert "Import Prospects" in body or "No prospects yet" in body


class TestNormalizeCompanyName:
    """Unit tests for the dedupe normalization key."""

    def test_strips_case_and_whitespace(self):
        assert li.normalize_company_name("  Acme  ") == li.normalize_company_name("acme")

    def test_strips_legal_suffixes(self):
        base = li.normalize_company_name("Acme")
        assert li.normalize_company_name("Acme Inc") == base
        assert li.normalize_company_name("Acme, Inc.") == base
        assert li.normalize_company_name("Acme LLC") == base
        assert li.normalize_company_name("Acme L.L.C.") == base
        assert li.normalize_company_name("ACME CORP") == base
        assert li.normalize_company_name("Acme Corporation") == base

    def test_strips_leading_the(self):
        assert li.normalize_company_name("The Acme Co") == li.normalize_company_name("Acme")

    def test_distinct_names_stay_distinct(self):
        assert li.normalize_company_name("Acme IT") != li.normalize_company_name("Acme Health")

    def test_suffix_only_name_not_empty(self):
        assert li.normalize_company_name("LLC") != ""


class TestDedupeAndPersistence:
    """Dedupe-safe imports + status/notes persistence (DB layer)."""

    def _import_one(self, company, **extra):
        import csv as _csv
        import io as _io
        buf = _io.StringIO()
        cols = ["Company"] + list(extra.keys())
        writer = _csv.writer(buf)
        writer.writerow(cols)
        writer.writerow([company] + list(extra.values()))
        return db_module.import_leads(li.parse_leads_csv(buf.getvalue()))

    def test_same_company_twice_no_duplicate(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        self._import_one("Acme Federal IT")
        overview = db_module.get_lead_intelligence_overview()
        assert len(overview) == 1

    def test_suffix_variants_dedupe(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT Inc")
        self._import_one("Acme Federal IT, LLC")
        self._import_one("acme federal it")
        overview = db_module.get_lead_intelligence_overview()
        assert len(overview) == 1

    def test_import_summary_new_then_updated(self, sqlite_db):
        db_module.init_db()
        first = self._import_one("Acme Federal IT")
        assert first["new"] == 1 and first["updated"] == 0
        second = self._import_one("Acme Federal IT")
        assert second["new"] == 0 and second["updated"] == 1

    def test_reimport_updates_safe_fields(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        self._import_one("Acme Federal IT", Email="new@acme.com", Phone="555-9000")
        company = db_module.get_lead_companies()[0]
        assert company["email"] == "new@acme.com"
        assert company["phone"] == "555-9000"

    def test_reimport_does_not_blank_existing_fields(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT", Email="keep@acme.com")
        # Re-import the same company with NO email — must not wipe it.
        self._import_one("Acme Federal IT")
        company = db_module.get_lead_companies()[0]
        assert company["email"] == "keep@acme.com"

    def test_contacted_status_persists(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        cid = db_module.get_lead_companies()[0]["id"]
        db_module.set_lead_contacted_status(cid, "contacted")
        # Reload from DB
        company = db_module.get_lead_companies()[0]
        assert company["contacted_status"] == "contacted"

    def test_invalid_status_falls_back(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        cid = db_module.get_lead_companies()[0]["id"]
        db_module.set_lead_contacted_status(cid, "bogus")
        assert db_module.get_lead_companies()[0]["contacted_status"] == "not_contacted"

    def test_notes_persist(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        cid = db_module.get_lead_companies()[0]["id"]
        db_module.set_lead_notes(cid, "Called 6/26, follow up next week")
        company = db_module.get_lead_companies()[0]
        assert "follow up next week" in company["outreach_notes"]

    def test_status_and_notes_survive_reimport(self, sqlite_db):
        db_module.init_db()
        self._import_one("Acme Federal IT")
        cid = db_module.get_lead_companies()[0]["id"]
        db_module.set_lead_contacted_status(cid, "contacted")
        db_module.set_lead_notes(cid, "important note")
        # Re-import the same company (with new contact info) — must preserve both.
        self._import_one("Acme Federal IT, Inc.", Email="fresh@acme.com")
        company = db_module.get_lead_companies()[0]
        assert len(db_module.get_lead_companies()) == 1
        assert company["contacted_status"] == "contacted"
        assert company["outreach_notes"] == "important note"
        assert company["email"] == "fresh@acme.com"

    def test_matches_preserved_after_status_change(self, sqlite_db):
        db_module.init_db()
        db_module.upsert_contract({
            "internal_id": "MX1", "vendor": "Inc Co", "agency": "Army",
            "category": "IT", "description": "cloud network help desk services",
            "value": 1_000_000, "place_of_performance_state": "VA",
            "days_remaining": 180, "recompete_score": 70, "naics_code": "541512",
        })
        db_module.import_leads(li.parse_leads_csv(
            "Company,Email,State\nAcme IT,it@acme.com,VA\n"))
        cid = db_module.get_lead_companies()[0]["id"]
        db_module.set_lead_contacted_status(cid, "contacted")
        matches = db_module.get_matches_for_company(cid)
        assert matches  # status change does not delete match records


class TestOutreachUI:
    """Route-level tests for status/notes endpoints and the outreach filter."""

    def _setup_company(self, client):
        client.post("/lead-intelligence/import", data={
            "csv_text": "Company,Email,State\nAcme Federal IT,it@acme.com,VA\n"
        }, follow_redirects=True)
        return db_module.get_lead_companies()[0]["id"]

    def test_status_selector_rendered(self, client):
        self._setup_company(client)
        body = client.get("/lead-intelligence").data.decode()
        assert "Not contacted" in body and "Outreach status" in body

    def test_notes_textarea_rendered(self, client):
        self._setup_company(client)
        body = client.get("/lead-intelligence").data.decode()
        assert "Outreach notes" in body
        assert 'name="outreach_notes"' in body

    def test_set_status_via_route_persists(self, client):
        cid = self._setup_company(client)
        client.post(f"/lead-intelligence/{cid}/status",
                    data={"contacted_status": "contacted"}, follow_redirects=True)
        body = client.get("/lead-intelligence").data.decode()
        assert "✓ Contacted" in body

    def test_set_notes_via_route_persists(self, client):
        cid = self._setup_company(client)
        client.post(f"/lead-intelligence/{cid}/notes",
                    data={"outreach_notes": "ring back Tuesday"}, follow_redirects=True)
        body = client.get("/lead-intelligence").data.decode()
        assert "ring back Tuesday" in body

    def test_outreach_filter_works(self, client):
        cid = self._setup_company(client)
        # Add a second company that stays not-contacted.
        client.post("/lead-intelligence/import", data={
            "csv_text": "Company,Email\nBeta Cleaning,b@beta.com\n"
        }, follow_redirects=True)
        client.post(f"/lead-intelligence/{cid}/status",
                    data={"contacted_status": "contacted"}, follow_redirects=True)

        contacted = client.get("/lead-intelligence?contacted=contacted").data.decode()
        assert "Acme Federal IT" in contacted
        assert "Beta Cleaning" not in contacted

        not_contacted = client.get("/lead-intelligence?contacted=not_contacted").data.decode()
        assert "Beta Cleaning" in not_contacted
        assert "Acme Federal IT" not in not_contacted

    def test_status_endpoint_admin_only(self, sqlite_db, monkeypatch):
        db_module.init_db()
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        flask_app.secret_key = "test-secret-key"
        monkeypatch.setenv("ADMIN_EMAILS", "admin-only@example.com")
        with flask_app.test_client() as c:
            c.post("/register", data={
                "email": "intruder@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
            with c.session_transaction() as sess:
                sess["onboarding_skipped"] = "1"
            assert c.post("/lead-intelligence/1/status",
                          data={"contacted_status": "contacted"}).status_code == 403
            assert c.post("/lead-intelligence/1/notes",
                          data={"outreach_notes": "x"}).status_code == 403


class TestLeadNextAction:
    """Unit tests for _lead_next_action helper (imported from app module)."""

    def _company(self, **kw):
        base = {
            "likely_customer_score": 70,
            "inferred_service_category": "it",
            "email": "x@x.com",
            "phone": "555",
            "matches": [{"match_score": 65}],
        }
        base.update(kw)
        return base

    def _action(self, **kw):
        from app import _lead_next_action
        return _lead_next_action(self._company(**kw))

    def test_high_score_with_contact_and_matches_is_contact_now(self):
        assert self._action() == "Contact now"

    def test_unknown_category_is_low_confidence(self):
        assert self._action(inferred_service_category="unknown") == "Low confidence"

    def test_low_score_is_low_confidence(self):
        assert self._action(likely_customer_score=30) == "Low confidence"

    def test_no_contact_info_is_research_first(self):
        assert self._action(email="", phone="") == "Research first"

    def test_no_matches_with_ok_score_is_research_first(self):
        assert self._action(matches=[]) == "Research first"

    def test_score_40_to_60_without_matches_is_research_first(self):
        assert self._action(likely_customer_score=50, matches=[]) == "Research first"
