"""Tests for the Open/Active status filter on the contracts list.

Lets contractors hide expired opportunities and focus on live ones:
  status=open    → days_remaining > 0
  status=expired → days_remaining <= 0
  status=""      → all (default; unchanged behavior, incl. unknown/NULL days)
"""
import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path):
    original = db_module.DB_PATH
    db_module.DB_PATH = str(tmp_path / "test.db")
    db_module.init_db()
    with db_module.connect() as con:
        rows = [
            ("OPEN1", "Acme Corp", "DOD", 120, 80),
            ("OPEN2", "Beta LLC", "DHS", 5, 70),
            ("EXP1", "Gamma Inc", "DOE", -30, 60),   # expired
            ("EXP0", "Delta Co", "GSA", 0, 55),       # ends today → expired
            ("UNK", "Echo Ltd", "VA", None, 50),      # unknown
        ]
        for iid, vendor, agency, dr, score in rows:
            con.execute(
                "INSERT INTO contracts (internal_id, vendor, agency, days_remaining, "
                "recompete_score, value, priority) VALUES (?,?,?,?,?,?,?)",
                (iid, vendor, agency, dr, score, 1_000_000, "HIGH"),
            )
        con.commit()
    yield db_module.DB_PATH
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


def _ids(result):
    return sorted(r["internal_id"] for r in result["contracts"])


# ── db layer ────────────────────────────────────────────────────────────────────
class TestGetContractsStatus:
    def test_default_returns_all_including_expired(self, test_db):
        assert db_module.get_contracts()["total"] == 5

    def test_open_only_live_opportunities(self, test_db):
        assert _ids(db_module.get_contracts(status="open")) == ["OPEN1", "OPEN2"]

    def test_expired_includes_zero_and_negative(self, test_db):
        assert _ids(db_module.get_contracts(status="expired")) == ["EXP0", "EXP1"]

    def test_unknown_days_only_in_all(self, test_db):
        # NULL days_remaining is neither open nor expired
        assert "UNK" not in _ids(db_module.get_contracts(status="open"))
        assert "UNK" not in _ids(db_module.get_contracts(status="expired"))
        assert "UNK" in _ids(db_module.get_contracts())

    def test_invalid_status_is_ignored(self, test_db):
        assert db_module.get_contracts(status="garbage")["total"] == 5

    def test_status_combines_with_other_filters(self, test_db):
        r = db_module.get_contracts(status="open", agency="DOD")
        assert _ids(r) == ["OPEN1"]


# ── route + UI ──────────────────────────────────────────────────────────────────
class TestContractsRouteStatus:
    def test_open_filter_hides_expired(self, client):
        # applyable=0 isolates the status filter from the default actionable
        # floor, so the small-positive Beta LLC (5 days) is still evaluated.
        body = client.get("/contracts?status=open&applyable=0").get_data(as_text=True)
        assert "Acme Corp" in body and "Beta LLC" in body
        assert "Gamma Inc" not in body and "Delta Co" not in body

    def test_status_dropdown_rendered_and_selected(self, client):
        body = client.get("/contracts?status=open").get_data(as_text=True)
        assert 'name="status"' in body
        assert 'value="open" selected' in body

    def test_default_excludes_expired_and_too_late(self, client):
        # Canonical rule: default actionable discovery excludes Expired / Too
        # Late (< 30 days). Only Acme Corp (120 days) is actionable; the rest
        # are hidden unless the user opts in (applyable=0).
        body = client.get("/contracts").get_data(as_text=True)
        assert "Acme Corp" in body
        assert "Gamma Inc" not in body      # expired — hidden by default
        assert "Delta Co" not in body       # ends today — hidden by default
        assert "Beta LLC" not in body       # 5 days — Too Late, hidden

    def test_expired_reachable_via_explicit_include(self, client):
        body = client.get("/contracts?applyable=0").get_data(as_text=True)
        assert "Gamma Inc" in body          # expired visible on explicit opt-in

    def test_invalid_status_sanitized_not_error(self, client):
        resp = client.get("/contracts?status=evil")
        assert resp.status_code == 200      # not a 400/500
        assert "Acme Corp" in resp.get_data(as_text=True)

    def test_export_csv_honors_status(self, client):
        body = client.get("/contracts/export.csv?status=open").get_data(as_text=True)
        assert "OPEN1" in body and "OPEN2" in body
        assert "EXP1" not in body and "EXP0" not in body
