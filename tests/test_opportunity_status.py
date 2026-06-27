"""Tests for opportunity_status() — actionability classification.

Validates every bucket: open_now, solicitation_unconfirmed, presolicitation,
awarded, solicitation_on_file, expired, too_late, watch, prepare_recompete, unknown.
Also covers db column persistence and the contracts-page filter.
"""
import pytest
from datetime import date, timedelta

from contract_summary import opportunity_status
import db as db_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kw):
    """Build a minimal contract row; keyword args override defaults."""
    base = {
        "internal_id": "TEST001",
        "days_remaining": 180,
        "sam_url": "",
        "sam_type": "",
        "sam_due_date": "",
    }
    base.update(kw)
    return base


def _future(days=30):
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


def _past(days=10):
    return (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Days-remaining fallback (no SAM data)
# ---------------------------------------------------------------------------

class TestDaysBasedClassification:
    def test_expired_zero_days(self):
        s = opportunity_status(_row(days_remaining=0))
        assert s["status"] == "expired"
        assert s["can_bid"] is False

    def test_expired_negative_days(self):
        s = opportunity_status(_row(days_remaining=-30))
        assert s["status"] == "expired"
        assert s["can_bid"] is False

    def test_too_late_under_30(self):
        s = opportunity_status(_row(days_remaining=15))
        assert s["status"] == "too_late"
        assert s["can_bid"] is False
        assert "15 day" in s["reason"]

    def test_too_late_boundary_29(self):
        s = opportunity_status(_row(days_remaining=29))
        assert s["status"] == "too_late"

    def test_prepare_recompete_at_30(self):
        # 30 days is the boundary: not too_late, not expired
        s = opportunity_status(_row(days_remaining=30))
        assert s["status"] == "prepare_recompete"
        assert s["can_bid"] is False

    def test_prepare_recompete_typical(self):
        s = opportunity_status(_row(days_remaining=180))
        assert s["status"] == "prepare_recompete"
        assert s["can_bid"] is False
        assert "awarded contract" in s["reason"].lower()

    def test_prepare_recompete_at_540(self):
        s = opportunity_status(_row(days_remaining=540))
        assert s["status"] == "prepare_recompete"

    def test_watch_over_540(self):
        s = opportunity_status(_row(days_remaining=541))
        assert s["status"] == "watch"
        assert s["can_bid"] is False

    def test_watch_far_out(self):
        s = opportunity_status(_row(days_remaining=900))
        assert s["status"] == "watch"

    def test_none_days_is_unknown(self):
        s = opportunity_status(_row(days_remaining=None))
        assert s["status"] == "unknown"
        assert s["can_bid"] is None


# ---------------------------------------------------------------------------
# SAM.gov type-based classification
# ---------------------------------------------------------------------------

class TestSamTypeClassification:
    def test_open_solicitation_with_future_due(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/1234",
            sam_type="Solicitation",
            sam_due_date=_future(30),
            days_remaining=180,
        ))
        assert s["status"] == "open_now"
        assert s["can_bid"] is True
        assert "Solicitation" in s["reason"]

    def test_combined_synopsis_open(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/xyz",
            sam_type="Combined Synopsis/Solicitation",
            sam_due_date=_future(14),
            days_remaining=120,
        ))
        assert s["status"] == "open_now"
        assert s["can_bid"] is True

    def test_rfq_open(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/rfq",
            sam_type="RFQ",
            sam_due_date=_future(7),
            days_remaining=90,
        ))
        assert s["status"] == "open_now"

    def test_solicitation_past_due_date(self):
        """Solicitation exists but due date is past → unconfirmed."""
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/1234",
            sam_type="Solicitation",
            sam_due_date=_past(5),
            days_remaining=30,
        ))
        assert s["status"] == "solicitation_unconfirmed"
        assert s["can_bid"] is None

    def test_solicitation_no_due_date(self):
        """Solicitation type but no due_date → unconfirmed."""
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/1234",
            sam_type="Solicitation",
            sam_due_date="",
            days_remaining=120,
        ))
        assert s["status"] == "solicitation_unconfirmed"
        assert s["can_bid"] is None

    def test_sources_sought_is_presolicitation(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/ss",
            sam_type="Sources Sought",
            days_remaining=300,
        ))
        assert s["status"] == "presolicitation"
        assert s["can_bid"] is False

    def test_presolicitation_type(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/ps",
            sam_type="Presolicitation",
            days_remaining=270,
        ))
        assert s["status"] == "presolicitation"

    def test_award_notice_is_not_open(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/aw",
            sam_type="Award Notice",
            days_remaining=200,
        ))
        assert s["status"] == "awarded"
        assert s["can_bid"] is False
        assert "award notice" in s["reason"].lower()

    def test_justification_type_is_awarded(self):
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/jus",
            sam_type="Justification",
            days_remaining=150,
        ))
        assert s["status"] == "awarded"

    def test_unknown_sam_type_with_url(self):
        """SAM URL present but type we don't recognise → solicitation_on_file."""
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/xyz",
            sam_type="Something New",
            days_remaining=90,
        ))
        assert s["status"] == "solicitation_on_file"
        assert s["can_bid"] is None

    def test_empty_sam_type_with_url(self):
        """Legacy row: SAM URL stored but type not yet fetched."""
        s = opportunity_status(_row(
            sam_url="https://sam.gov/opp/legacy",
            sam_type="",
            days_remaining=90,
        ))
        assert s["status"] == "solicitation_on_file"
        assert s["can_bid"] is None


# ---------------------------------------------------------------------------
# Priority correction: "Critical" must not fire for <30 days without open sol
# ---------------------------------------------------------------------------

class TestCriticalPriorityNotForTooLate:
    def test_3_days_left_is_too_late_not_critical(self):
        s = opportunity_status(_row(days_remaining=3, sam_type="", sam_url=""))
        assert s["status"] == "too_late"
        assert s["can_bid"] is False

    def test_3_days_with_open_solicitation_is_open_now(self):
        """If there IS an active solicitation even at 3 days, it can be bid."""
        s = opportunity_status(_row(
            days_remaining=3,
            sam_url="https://sam.gov/opp/urgent",
            sam_type="Solicitation",
            sam_due_date=_future(3),
        ))
        assert s["status"] == "open_now"
        assert s["can_bid"] is True


# ---------------------------------------------------------------------------
# Return structure always complete
# ---------------------------------------------------------------------------

class TestReturnStructure:
    REQUIRED_KEYS = {"status", "label", "can_bid", "reason", "next_action"}

    def test_all_keys_present_for_all_statuses(self):
        cases = [
            _row(days_remaining=None),
            _row(days_remaining=-5),
            _row(days_remaining=3),
            _row(days_remaining=30),
            _row(days_remaining=180),
            _row(days_remaining=541),
            _row(sam_url="https://sam.gov/1", sam_type="Solicitation", sam_due_date=_future(10), days_remaining=180),
            _row(sam_url="https://sam.gov/1", sam_type="Award Notice", days_remaining=180),
            _row(sam_url="https://sam.gov/1", sam_type="Sources Sought", days_remaining=300),
        ]
        for c in cases:
            result = opportunity_status(c)
            assert self.REQUIRED_KEYS.issubset(result.keys()), f"Missing keys for: {c}"

    def test_can_bid_is_bool_or_none(self):
        for days in (None, -5, 3, 30, 180, 541):
            result = opportunity_status(_row(days_remaining=days))
            assert result["can_bid"] in (True, False, None)

    def test_label_is_non_empty_string(self):
        for days in (None, -5, 3, 30, 180, 541):
            result = opportunity_status(_row(days_remaining=days))
            assert isinstance(result["label"], str) and result["label"]

    def test_reason_is_non_empty_string(self):
        for days in (None, -5, 3, 30, 180, 541):
            result = opportunity_status(_row(days_remaining=days))
            assert isinstance(result["reason"], str) and result["reason"]


# ---------------------------------------------------------------------------
# db: sam_type and sam_due_date persisted via upsert_contract
# ---------------------------------------------------------------------------

@pytest.fixture()
def sam_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "sam_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield db_path


def test_upsert_contract_persists_sam_type(sam_db):
    db_module.upsert_contract({
        "internal_id": "SAM001",
        "vendor": "Vendor A",
        "agency": "DoD",
        "value": 500_000,
        "days_remaining": 120,
        "priority": "HIGH",
        "recompete_score": 70,
        "sam_url": "https://sam.gov/opp/1",
        "sam_type": "Solicitation",
        "sam_due_date": "2027-03-01",
    })
    with db_module.get_engine().connect() as conn:
        from sqlalchemy import text
        row = conn.execute(
            text("SELECT sam_type, sam_due_date FROM contracts WHERE internal_id = 'SAM001'")
        ).fetchone()
    assert row[0] == "Solicitation"
    assert row[1] == "2027-03-01"


def test_upsert_contract_defaults_empty_sam_fields(sam_db):
    db_module.upsert_contract({
        "internal_id": "SAM002",
        "vendor": "Vendor B",
        "agency": "DHS",
        "value": 200_000,
        "days_remaining": 200,
        "priority": "MEDIUM",
        "recompete_score": 55,
    })
    with db_module.get_engine().connect() as conn:
        from sqlalchemy import text
        row = conn.execute(
            text("SELECT sam_type, sam_due_date FROM contracts WHERE internal_id = 'SAM002'")
        ).fetchone()
    assert row[0] == ""
    assert row[1] == ""


def test_ensure_sam_enrichment_columns_idempotent(sam_db):
    """Calling _ensure_sam_enrichment_columns multiple times must not error."""
    db_module._ensure_sam_enrichment_columns()
    db_module._ensure_sam_enrichment_columns()


# ---------------------------------------------------------------------------
# /contracts route: actionability filter param accepted
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "app_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    db_module.upsert_contract({
        "internal_id": "C001", "vendor": "VendorX", "agency": "Army",
        "value": 1_000_000, "days_remaining": 180,
        "priority": "HIGH", "recompete_score": 75,
        "sam_type": "", "sam_due_date": "",
    })
    yield db_path


@pytest.fixture()
def client(app_db, monkeypatch):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-opp-status"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "os@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        yield c


def test_contracts_page_renders_without_actionability_filter(client):
    rv = client.get("/contracts")
    assert rv.status_code == 200
    assert b"Contracts" in rv.data


def test_contracts_page_actionability_filter_accepted(client):
    rv = client.get("/contracts?actionability=prepare_recompete")
    assert rv.status_code == 200


def test_contracts_page_invalid_actionability_ignored(client):
    rv = client.get("/contracts?actionability=invalid_value")
    assert rv.status_code == 200


def test_contracts_page_open_now_filter(client):
    rv = client.get("/contracts?actionability=open_now")
    assert rv.status_code == 200


def test_contracts_page_too_late_filter(client):
    rv = client.get("/contracts?actionability=too_late")
    assert rv.status_code == 200


def test_contract_detail_shows_can_i_bid_section(client, app_db):
    rv = client.get("/contract/C001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Can I bid on this now?" in body


def test_contract_detail_shows_no_for_awarded_no_sol(client, app_db):
    """Contract with no SAM data and 180 days → Not open, Prepare for recompete."""
    rv = client.get("/contract/C001")
    body = rv.data.decode()
    assert "No" in body or "Prepare for recompete" in body


def test_contract_detail_open_now_shows_yes(app_db, monkeypatch):
    """Contract with active solicitation → can bid = Yes."""
    from datetime import date, timedelta
    due = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
    db_module.upsert_contract({
        "internal_id": "OPEN001", "vendor": "Open Vendor", "agency": "Navy",
        "value": 500_000, "days_remaining": 90, "priority": "HIGH",
        "recompete_score": 80,
        "sam_url": "https://sam.gov/opp/open1",
        "sam_type": "Solicitation",
        "sam_due_date": due,
    })
    monkeypatch.setenv("ADMIN_EMAILS", "")
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-open-now"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "opentest@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        rv = c.get("/contract/OPEN001")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "Can I bid on this now?" in body
    assert "Yes" in body or "Open" in body
