"""Query-layer tests: lifecycle floor + procurement-status filter/counts.

The canonical actionable window must be enforced in the query/service layer
(get_contracts), not merely hidden in the template, so counts and pagination
agree with what is shown. Also covers the independent procurement-status filter
and status counts, and route-level rendering of both concepts + CTA labels.
"""

from datetime import date, timedelta

import pytest

import db as db_module


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


def _seed(iid, days, priority="CRITICAL", score=95, value=1_000_000,
          sam_type="", sam_url="", generated_internal_id=None, solicitation_id=""):
    today = date.today()
    db_module.upsert_contract({
        "internal_id": iid,
        "generated_internal_id": generated_internal_id,
        "award_id": iid,
        "vendor": f"Vendor {iid}",
        "agency": "DEFENSE",
        "description": "janitorial services",
        "value": value,
        "start_date": "2024-01-01",
        "end_date": (today + timedelta(days=days)).isoformat(),
        "days_remaining": days,
        "priority": priority,
        "recompete_score": score,
        "competition_type": "FULL AND OPEN COMPETITION",
        "sam_type": sam_type,
        "sam_url": sam_url,
        "solicitation_id": solicitation_id,
    })


# ── Lifecycle floor in the query layer (PM decision D) ────────────────────────

class TestLifecycleFloor:
    def test_default_actionable_excludes_too_late_and_expired(self, test_db):
        _seed("D3", days=3)
        _seed("D4", days=4)
        _seed("D29", days=29)
        _seed("D30", days=30)
        _seed("D540", days=540)
        _seed("D541", days=541)
        _seed("EXP", days=-5)
        res = db_module.get_contracts(applyable=True, limit=100)
        ids = {r["internal_id"] for r in res["contracts"]}
        assert ids == {"D30", "D540"}
        # Counts reflect the filtered query, not post-render removal.
        assert res["total"] == 2

    def test_boundaries_30_and_540_inclusive(self, test_db):
        _seed("LO", days=30)
        _seed("HI", days=540)
        _seed("UNDER", days=29)
        _seed("OVER", days=541)
        res = db_module.get_contracts(applyable=True, limit=100)
        ids = {r["internal_id"] for r in res["contracts"]}
        assert "LO" in ids and "HI" in ids
        assert "UNDER" not in ids and "OVER" not in ids

    def test_explicit_include_returns_too_late(self, test_db):
        _seed("D3", days=3)
        _seed("D200", days=200)
        res = db_module.get_contracts(applyable=False, limit=100)
        ids = {r["internal_id"] for r in res["contracts"]}
        assert "D3" in ids and "D200" in ids

    def test_internal_ids_curated_set_exempt_from_floor(self, test_db):
        # A watchlist/pipeline id list is curated, not discovery — the floor is
        # not applied so a tracked contract that slipped under 30 days still shows.
        _seed("WATCHED", days=5)
        res = db_module.get_contracts(applyable=True, internal_ids=["WATCHED"], limit=100)
        ids = {r["internal_id"] for r in res["contracts"]}
        assert "WATCHED" in ids


# ── Procurement-status filter + counts (independent of lifecycle) ─────────────

class TestProcurementFilter:
    def test_open_and_closed_filter(self, test_db):
        _seed("OPEN1", days=200, sam_type="Solicitation", sam_url="https://sam.gov/opp/1")
        _seed("AWARDED1", days=200, sam_type="")
        _seed("AWARDNOTICE", days=200, sam_type="Award Notice")

        res_open = db_module.get_contracts(applyable=True, procurement="open", limit=100)
        assert {r["internal_id"] for r in res_open["contracts"]} == {"OPEN1"}

        res_closed = db_module.get_contracts(applyable=True, procurement="closed", limit=100)
        assert {r["internal_id"] for r in res_closed["contracts"]} == {"AWARDED1", "AWARDNOTICE"}

    def test_status_counts_report_both_buckets(self, test_db):
        _seed("OPEN1", days=200, sam_type="Solicitation", sam_url="https://sam.gov/opp/1")
        _seed("AWARDED1", days=200, sam_type="")
        # status_counts are computed before the procurement filter is applied.
        res = db_module.get_contracts(applyable=True, procurement="open",
                                      with_status_counts=True, limit=100)
        assert res["status_counts"] == {"open": 1, "closed": 1}
        # The shown list is still filtered to Open.
        assert res["total"] == 1


# ── Route-level rendering: both concepts, CTA labels, source-aware link ───────

@pytest.fixture()
def client(test_db):
    from unittest.mock import MagicMock, patch
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    flask_app.limiter.reset()
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=None)
    with flask_app.app.test_client() as c:
        with patch("tasks.send_email_task", mock_task):
            c.post("/register", data={
                "email": "fixture@example.com",
                "password": "testpass123",
                "confirm": "testpass123",
            })
        yield c


class TestRouteRendering:
    def test_n6274219f0181_links_to_usaspending_not_sam(self, client, test_db):
        _seed("310807250", days=200, sam_type="",
              generated_internal_id="CONT_AWD_N6274219F0181_9700_N6274215D1818_9700",
              solicitation_id="N6274214R1888")
        rv = client.get("/contract/310807250")
        assert rv.status_code == 200
        assert b"usaspending.gov/award/CONT_AWD_N6274219F0181_9700_N6274215D1818_9700" in rv.data
        assert b"View Award on USAspending" in rv.data

    def test_card_shows_both_status_and_priority(self, client, test_db):
        _seed("AWARDED1", days=200, sam_type="", priority="CRITICAL")
        rv = client.get("/contracts")
        assert rv.status_code == 200
        # Procurement status badge (Closed) AND lifecycle priority both present.
        assert b"proc-badge" in rv.data
        assert b"Procurement status: Closed (Awarded)" in rv.data

    def test_procurement_filter_hides_closed(self, client, test_db):
        _seed("OPEN1", days=200, sam_type="Solicitation", sam_url="https://sam.gov/opp/1")
        _seed("AWARDED1", days=200, sam_type="")
        rv = client.get("/contracts?procurement=open")
        assert b"Vendor OPEN1" in rv.data
        assert b"Vendor AWARDED1" not in rv.data

    def test_too_late_row_never_high_or_critical_in_listing(self, client, test_db):
        # Even when surfaced (explicit applyable=0), a 3-day stale-CRITICAL row
        # must not render a High/Critical priority badge.
        _seed("D3", days=3, priority="CRITICAL")
        rv = client.get("/contracts?applyable=0")
        assert b"Vendor D3" in rv.data
        # The row's own priority badge (an anchor with this title) must be
        # downgraded — never High/Critical for a Too Late row.
        assert b'Recompete priority (lifecycle)">LOW' in rv.data
        assert b'Recompete priority (lifecycle)">CRITICAL' not in rv.data
        assert b'Recompete priority (lifecycle)">HIGH' not in rv.data
