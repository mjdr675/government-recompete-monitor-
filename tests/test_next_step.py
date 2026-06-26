"""Contract-detail recompete timing + recommended next step.

Pure helper (`recompete_report.next_step`) from existing fields only — no DB, no
external/AI calls — plus the detail-page integration.
"""
import pytest

import db as db_module
from contract_summary import next_step


# ── pure helper ─────────────────────────────────────────────────────────────────
class TestNextStep:
    def test_unknown_when_days_none(self):
        r = next_step(None)
        assert r["timing"] == "Timing unknown"
        assert "end date" in r["action"].lower()

    def test_expired(self):
        for d in (0, -1, -400):
            r = next_step(d)
            assert r["timing"] == "Expired"
            assert "sam.gov" in r["action"].lower()

    def test_within_six_months(self):
        # 120 days = active pursuit window
        r = next_step(120)
        assert r["timing"] == "Expiring within ~6 months"
        assert "proposal" in r["action"].lower() or "solicitation" in r["action"].lower()

    def test_shape_opportunity_window(self):
        # 300 days = shape opportunity
        r = next_step(300)
        assert r["timing"] == "Shape Opportunity"
        assert "agency" in r["action"].lower() or "shape" in r["action"].lower()

    def test_best_pursuit_window(self):
        # 400 days = best pursuit window
        r = next_step(400)
        assert r["timing"] == "Best Pursuit Window"

    def test_more_than_a_year_watch_stage(self):
        # > 540 days = watch/early stage
        r = next_step(800)
        assert r["timing"] == "More than a year out"

    def test_string_days_are_coerced(self):
        # 450 days = best pursuit window
        assert next_step("450")["timing"] == "Best Pursuit Window"

    def test_garbage_days_treated_as_unknown(self):
        assert next_step("soon")["timing"] == "Timing unknown"

    def test_high_priority_adds_urgency_for_future(self):
        assert next_step(120, "CRITICAL")["action"].startswith("High-priority")
        assert next_step(300, "HIGH")["action"].startswith("High-priority")

    def test_no_urgency_nudge_for_expired_or_low(self):
        assert not next_step(-5, "CRITICAL")["action"].startswith("High-priority")
        assert not next_step(120, "LOW")["action"].startswith("High-priority")

    def test_always_returns_all_keys(self):
        for d in (None, -5, 90, 300, 900):
            r = next_step(d)
            assert set(r) == {"timing", "detail", "action"}
            assert all(isinstance(v, str) and v for v in r.values())


# ── detail-page integration ─────────────────────────────────────────────────────
@pytest.fixture()
def test_db(tmp_path):
    original = db_module.DB_PATH
    db_module.DB_PATH = str(tmp_path / "test.db")
    db_module.init_db()
    with db_module.connect() as con:
        con.execute(
            "INSERT INTO contracts (internal_id, vendor, agency, value, end_date, "
            "days_remaining, priority, recompete_score) VALUES (?,?,?,?,?,?,?,?)",
            ("DET-1", "Acme Corp", "DEFENSE", 2_000_000, "2026-09-30", 120, "CRITICAL", 92),
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
        c.post("/register", data={"email": "nx@example.com",
                                  "password": "password123", "confirm": "password123"})
        yield c


class TestDetailPage:
    def test_detail_shows_timing_and_next_step(self, client):
        body = client.get("/contract/DET-1").get_data(as_text=True)
        assert "Recompete timing:" in body
        assert "Expiring within ~6 months" in body
        assert "Suggested approach:" in body
        # CRITICAL + future-dated → urgency nudge surfaces
        assert "High-priority opportunity" in body

    def test_detail_requires_login(self, test_db):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as anon:
            assert anon.get("/contract/DET-1").status_code == 302
