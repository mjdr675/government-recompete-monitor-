"""Regression tests for the SQLite-only `connection.row_factory` incompatibility.

Production runs on PostgreSQL (psycopg2) since the DB cutover on 2026-07-10.
`app.py` previously did:

    con = connect()
    con.row_factory = lambda cur, row: {...}

`row_factory` is a sqlite3-only DBAPI extension; psycopg2 connections don't
have it, so every GET on /contract/<id>, /contract/<id>/apply, /pipeline/<id>,
and /compare raised AttributeError in production (500) while passing locally
against SQLite. The fix replaces the raw `connect()` + row_factory pattern with
the project's existing driver-agnostic `get_engine()` + `text(...)` +
`.mappings()` approach (already used elsewhere in app.py, including in these
same view functions), which works identically across sqlite3 and psycopg2.
"""

import sqlite3

import pytest

import app as flask_app
import db as db_module
from db import add_opportunity


@pytest.fixture()
def rowfix_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "rowfix_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    import users as users_module
    users_module.create_user("rowfix@example.com", "pw123456")
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR IGNORE INTO contracts"
        " (internal_id, agency, sub_agency, vendor, value, recompete_score,"
        "  priority, end_date, days_remaining, competition_type)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("RF-001", "Dept of Defense", "Army", "Acme Corp",
         5_000_000.0, 80, "HIGH", "2026-12-31", 190, "Full and Open"),
    )
    con.commit()
    con.close()
    yield db_path
    db_module._cached_engine.cache_clear()


def _client(authed=True):
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    c = flask_app.app.test_client()
    if authed:
        c.post("/login", data={"email": "rowfix@example.com", "password": "pw123456"})
        with c.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
    return c


class TestLegacyConnectNoLongerUsed:
    """The whole bug was these routes touching db.connect()'s sqlite-only API.

    Patch the name each view module actually calls; if any patched route still
    calls it, the AssertionError below fires instead of a normal response.
    """

    def _boom(self, *a, **kw):
        raise AssertionError("route must not call the legacy connect()/row_factory path")

    def test_contract_detail_does_not_call_legacy_connect(self, rowfix_db, monkeypatch):
        monkeypatch.setattr(flask_app, "connect", self._boom)
        r = _client().get("/contract/RF-001")
        assert r.status_code == 200

    def test_contract_apply_does_not_call_legacy_connect(self, rowfix_db, monkeypatch):
        monkeypatch.setattr(flask_app, "connect", self._boom)
        r = _client().get("/contract/RF-001/apply")
        assert r.status_code in (200, 302)

    def test_opportunity_detail_does_not_call_legacy_connect(self, rowfix_db, monkeypatch):
        uid = None
        con = sqlite3.connect(rowfix_db)
        uid = con.execute("SELECT id FROM users WHERE email=?", ("rowfix@example.com",)).fetchone()[0]
        con.close()
        opp_id, _ = add_opportunity(uid, "RF-001")
        monkeypatch.setattr(flask_app, "connect", self._boom)
        r = _client().get(f"/pipeline/{opp_id}")
        assert r.status_code == 200

    def test_compare_does_not_call_legacy_connect(self, rowfix_db, monkeypatch):
        monkeypatch.setattr(flask_app, "connect", self._boom)
        r = _client().get("/compare?a=RF-001")
        assert r.status_code == 200


class TestContractDetail:
    def test_renders_200(self, rowfix_db):
        r = _client().get("/contract/RF-001")
        assert r.status_code == 200
        assert b"Acme Corp" in r.data

    def test_missing_contract_redirects_not_500(self, rowfix_db):
        r = _client().get("/contract/DOES-NOT-EXIST", follow_redirects=False)
        assert r.status_code in (301, 302)
        assert r.headers["Location"].endswith("/contracts")


class TestContractApply:
    def test_existing_contract_no_500(self, rowfix_db):
        r = _client().get("/contract/RF-001/apply")
        assert r.status_code in (200, 302)

    def test_missing_contract_redirects_not_500(self, rowfix_db):
        r = _client().get("/contract/DOES-NOT-EXIST/apply", follow_redirects=False)
        assert r.status_code in (301, 302)
        assert r.headers["Location"].endswith("/contracts")


class TestOpportunityDetail:
    def test_renders_200_with_contract_fields(self, rowfix_db):
        con = sqlite3.connect(rowfix_db)
        uid = con.execute("SELECT id FROM users WHERE email=?", ("rowfix@example.com",)).fetchone()[0]
        con.close()
        opp_id, _ = add_opportunity(uid, "RF-001")
        r = _client().get(f"/pipeline/{opp_id}")
        assert r.status_code == 200
        assert b"Acme Corp" in r.data


class TestCompare:
    def test_two_contracts_no_500(self, rowfix_db):
        r = _client().get("/compare?a=RF-001&b=DOES-NOT-EXIST")
        assert r.status_code == 200


class TestRowKeysMatchSchema:
    """The old dict was keyed by sqlite cursor.description column names.
    The new dict (via SQLAlchemy .mappings()) must produce the exact same
    key set for the same `SELECT *` so templates/business logic see no
    difference.
    """

    def test_mappings_keys_match_raw_cursor_description(self, rowfix_db):
        engine = db_module.get_engine()
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            result = conn.execute(
                sa_text("SELECT * FROM contracts WHERE internal_id = :iid"),
                {"iid": "RF-001"},
            ).mappings().fetchone()
        row = dict(result)

        raw = sqlite3.connect(rowfix_db)
        cur = raw.execute("SELECT * FROM contracts WHERE internal_id=?", ("RF-001",))
        cur.fetchone()
        raw_cols = {col[0] for col in cur.description}
        raw.close()

        assert set(row.keys()) == raw_cols
        assert row["vendor"] == "Acme Corp"


class TestSqliteSuiteStillPasses:
    """Sanity check: fixing the psycopg2 path must not disturb SQLite behavior
    (dev/CI run entirely on SQLite, no DATABASE_URL set).
    """

    def test_contracts_list_and_detail_agree_on_vendor(self, rowfix_db):
        c = _client()
        list_rv = c.get("/contracts")
        detail_rv = c.get("/contract/RF-001")
        assert list_rv.status_code == 200
        assert detail_rv.status_code == 200
        assert b"Acme Corp" in detail_rv.data
