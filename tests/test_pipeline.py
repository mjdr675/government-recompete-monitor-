"""Tests for Opportunity Pipeline data layer (Commit 1).

Covers:
- PIPELINE_STAGES constant shape and content
- opportunities table + indexes exist after init_db()
- add_opportunity: create, idempotent duplicate, invalid stage
- remove_opportunity: delete, no-op on missing
- get_opportunity: found / not found / wrong owner (IDOR)
- get_opportunity_by_contract: found / not found
- list_opportunities: all, stage filter, LEFT JOIN orphan tolerance
- update_opportunity: stage, probability, next_action/due, notes,
  invalid stage, wrong owner, probability clamping
- migration 007 file is present and parseable
"""

import sqlite3
import pytest
import db as db_module
from db import (
    PIPELINE_STAGES,
    PIPELINE_TERMINAL_STAGES,
    add_opportunity,
    remove_opportunity,
    get_opportunity,
    get_opportunity_by_contract,
    list_opportunities,
    update_opportunity,
)
import users as users_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pipeline_db(tmp_path, monkeypatch):
    """Fresh isolated DB with two users pre-created."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    users_module.create_user("alice@example.com", "password123")
    users_module.create_user("bob@example.com", "password123")
    yield db_path
    db_module._cached_engine.cache_clear()


def _uid(db_path, email):
    con = sqlite3.connect(db_path)
    uid = con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    con.close()
    return uid


def _insert_contract(db_path, internal_id="CTR-001", agency="DoD", value=5_000_000.0):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR IGNORE INTO contracts (internal_id, agency, value, recompete_score)"
        " VALUES (?, ?, ?, ?)",
        (internal_id, agency, value, 80),
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# PIPELINE_STAGES constant
# ---------------------------------------------------------------------------

class TestPipelineStagesConstant:
    def test_is_list_of_tuples(self):
        assert isinstance(PIPELINE_STAGES, list)
        for item in PIPELINE_STAGES:
            assert isinstance(item, tuple) and len(item) == 2

    def test_contains_required_stages(self):
        values = [v for v, _ in PIPELINE_STAGES]
        for stage in ("new", "interested", "researching", "capturing",
                      "proposal", "submitted", "awarded", "lost"):
            assert stage in values

    def test_terminal_stages_subset(self):
        values = frozenset(v for v, _ in PIPELINE_STAGES)
        assert PIPELINE_TERMINAL_STAGES.issubset(values)
        assert "awarded" in PIPELINE_TERMINAL_STAGES
        assert "lost" in PIPELINE_TERMINAL_STAGES
        assert "new" not in PIPELINE_TERMINAL_STAGES


# ---------------------------------------------------------------------------
# Schema: table + indexes exist after init_db()
# ---------------------------------------------------------------------------

class TestSchemaExists:
    def test_opportunities_table_exists(self, pipeline_db):
        con = sqlite3.connect(pipeline_db)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        con.close()
        assert "opportunities" in tables

    def test_required_columns_exist(self, pipeline_db):
        con = sqlite3.connect(pipeline_db)
        cols = {r[1] for r in con.execute("PRAGMA table_info(opportunities)").fetchall()}
        con.close()
        required = {
            "id", "user_id", "internal_id", "stage", "probability",
            "next_action", "next_action_due", "notes",
            "created_by_user_id", "last_updated_by_user_id",
            "created_at", "updated_at",
        }
        assert required.issubset(cols)

    def test_unique_constraint_user_internal_id(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        con = sqlite3.connect(pipeline_db)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        con.execute(
            "INSERT INTO opportunities"
            " (user_id, internal_id, stage, created_by_user_id,"
            "  last_updated_by_user_id, created_at, updated_at)"
            " VALUES (?, ?, 'new', ?, ?, ?, ?)",
            (uid, "CTR-DUP", uid, uid, now, now),
        )
        con.commit()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO opportunities"
                " (user_id, internal_id, stage, created_by_user_id,"
                "  last_updated_by_user_id, created_at, updated_at)"
                " VALUES (?, ?, 'new', ?, ?, ?, ?)",
                (uid, "CTR-DUP", uid, uid, now, now),
            )
        con.close()

    def test_indexes_exist(self, pipeline_db):
        con = sqlite3.connect(pipeline_db)
        indexes = {r[1] for r in con.execute(
            "SELECT * FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        con.close()
        assert "idx_opportunities_user" in indexes
        assert "idx_opportunities_user_stage" in indexes
        assert "idx_opportunities_user_due" in indexes


# ---------------------------------------------------------------------------
# add_opportunity
# ---------------------------------------------------------------------------

class TestAddOpportunity:
    def test_creates_row_returns_id(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, created = add_opportunity(uid, "CTR-001")
        assert isinstance(opp_id, int) and opp_id > 0
        assert created is True

    def test_default_stage_is_new(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        opp = get_opportunity(uid, opp_id)
        assert opp["stage"] == "new"

    def test_explicit_stage_stored(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001", stage="capturing")
        opp = get_opportunity(uid, opp_id)
        assert opp["stage"] == "capturing"

    def test_duplicate_is_idempotent(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        id1, created1 = add_opportunity(uid, "CTR-001")
        id2, created2 = add_opportunity(uid, "CTR-001")
        assert id1 == id2
        assert created1 is True
        assert created2 is False

    def test_duplicate_does_not_change_stage(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001", stage="proposal")
        add_opportunity(uid, "CTR-001", stage="new")  # second add ignored
        opp = get_opportunity(uid, opp_id)
        assert opp["stage"] == "proposal"

    def test_invalid_stage_raises(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        with pytest.raises(ValueError, match="Invalid pipeline stage"):
            add_opportunity(uid, "CTR-001", stage="nonsense")

    def test_two_users_same_contract_independent(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        id_a, _ = add_opportunity(alice, "CTR-001")
        id_b, _ = add_opportunity(bob,   "CTR-001")
        assert id_a != id_b

    def test_created_by_user_id_set(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        opp = get_opportunity(uid, opp_id)
        assert opp["created_by_user_id"] == uid
        assert opp["last_updated_by_user_id"] == uid


# ---------------------------------------------------------------------------
# remove_opportunity
# ---------------------------------------------------------------------------

class TestRemoveOpportunity:
    def test_removes_existing(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        add_opportunity(uid, "CTR-001")
        remove_opportunity(uid, "CTR-001")
        assert get_opportunity_by_contract(uid, "CTR-001") is None

    def test_noop_on_missing(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        remove_opportunity(uid, "NONEXISTENT")  # must not raise

    def test_only_removes_own(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        add_opportunity(alice, "CTR-001")
        add_opportunity(bob,   "CTR-001")
        remove_opportunity(alice, "CTR-001")
        assert get_opportunity_by_contract(alice, "CTR-001") is None
        assert get_opportunity_by_contract(bob,   "CTR-001") is not None


# ---------------------------------------------------------------------------
# get_opportunity
# ---------------------------------------------------------------------------

class TestGetOpportunity:
    def test_returns_dict(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        opp = get_opportunity(uid, opp_id)
        assert isinstance(opp, dict)
        assert opp["id"] == opp_id
        assert opp["internal_id"] == "CTR-001"

    def test_returns_none_when_not_found(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        assert get_opportunity(uid, 99999) is None

    def test_returns_none_for_wrong_owner(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        opp_id, _ = add_opportunity(alice, "CTR-001")
        assert get_opportunity(bob, opp_id) is None


# ---------------------------------------------------------------------------
# get_opportunity_by_contract
# ---------------------------------------------------------------------------

class TestGetOpportunityByContract:
    def test_returns_opp_when_exists(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        opp = get_opportunity_by_contract(uid, "CTR-001")
        assert opp is not None
        assert opp["id"] == opp_id

    def test_returns_none_when_not_in_pipeline(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        assert get_opportunity_by_contract(uid, "CTR-NONE") is None

    def test_scoped_to_user(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        add_opportunity(alice, "CTR-001")
        assert get_opportunity_by_contract(bob, "CTR-001") is None


# ---------------------------------------------------------------------------
# list_opportunities
# ---------------------------------------------------------------------------

class TestListOpportunities:
    def test_returns_list(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        assert list_opportunities(uid) == []

    def test_returns_all_user_opportunities(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        add_opportunity(uid, "CTR-001")
        add_opportunity(uid, "CTR-002")
        add_opportunity(uid, "CTR-003")
        result = list_opportunities(uid)
        assert len(result) == 3

    def test_excludes_other_users(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        add_opportunity(alice, "CTR-001")
        add_opportunity(bob,   "CTR-002")
        assert len(list_opportunities(alice)) == 1
        assert len(list_opportunities(bob))   == 1

    def test_stage_filter(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        add_opportunity(uid, "CTR-001", stage="proposal")
        add_opportunity(uid, "CTR-002", stage="capturing")
        add_opportunity(uid, "CTR-003", stage="proposal")
        result = list_opportunities(uid, stage="proposal")
        assert len(result) == 2
        assert all(r["stage"] == "proposal" for r in result)

    def test_invalid_stage_filter_raises(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        with pytest.raises(ValueError):
            list_opportunities(uid, stage="invalid")

    def test_includes_contract_columns_when_joined(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        _insert_contract(pipeline_db, "CTR-001", agency="NASA", value=1_000_000)
        add_opportunity(uid, "CTR-001")
        result = list_opportunities(uid)
        assert result[0]["agency"] == "NASA"
        assert result[0]["value"] == 1_000_000.0

    def test_tolerates_orphaned_contract(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        # Add opportunity for a contract that does not exist in contracts table
        add_opportunity(uid, "CTR-ORPHAN")
        result = list_opportunities(uid)
        assert len(result) == 1
        # Contract columns are None (LEFT JOIN)
        assert result[0]["agency"] is None
        assert result[0]["value"] is None


# ---------------------------------------------------------------------------
# update_opportunity
# ---------------------------------------------------------------------------

class TestUpdateOpportunity:
    def test_update_stage(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"stage": "capturing"})
        assert updated["stage"] == "capturing"

    def test_update_notes(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"notes": "Key incumbent is retiring."})
        assert updated["notes"] == "Key incumbent is retiring."

    def test_clear_notes_with_empty_string(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"notes": "Initial"})
        updated = update_opportunity(uid, opp_id, {"notes": ""})
        assert updated["notes"] is None

    def test_update_probability_integer(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"probability": 75})
        assert updated["probability"] == 75

    def test_probability_clamped_low(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"probability": -10})
        assert updated["probability"] == 0

    def test_probability_clamped_high(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"probability": 150})
        assert updated["probability"] == 100

    def test_probability_non_numeric_ignored(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"probability": "abc"})
        assert updated["probability"] is None

    def test_update_next_action(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {
            "next_action": "Call CO",
            "next_action_due": "2026-07-15",
        })
        assert updated["next_action"] == "Call CO"
        assert updated["next_action_due"] == "2026-07-15"

    def test_clear_next_action_due(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"next_action_due": "2026-07-15"})
        updated = update_opportunity(uid, opp_id, {"next_action_due": ""})
        assert updated["next_action_due"] is None

    def test_partial_update_leaves_other_fields(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        update_opportunity(uid, opp_id, {"notes": "Saved note", "probability": 60})
        updated = update_opportunity(uid, opp_id, {"stage": "proposal"})
        assert updated["notes"] == "Saved note"
        assert updated["probability"] == 60
        assert updated["stage"] == "proposal"

    def test_invalid_stage_raises(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        with pytest.raises(ValueError, match="Invalid pipeline stage"):
            update_opportunity(uid, opp_id, {"stage": "garbage"})

    def test_wrong_owner_raises_lookup_error(self, pipeline_db):
        alice = _uid(pipeline_db, "alice@example.com")
        bob   = _uid(pipeline_db, "bob@example.com")
        opp_id, _ = add_opportunity(alice, "CTR-001")
        with pytest.raises(LookupError):
            update_opportunity(bob, opp_id, {"stage": "proposal"})

    def test_last_updated_by_user_id_updated(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        updated = update_opportunity(uid, opp_id, {"stage": "proposal"},
                                     updated_by_user_id=uid)
        assert updated["last_updated_by_user_id"] == uid

    def test_updated_at_advances(self, pipeline_db):
        uid = _uid(pipeline_db, "alice@example.com")
        opp_id, _ = add_opportunity(uid, "CTR-001")
        before = get_opportunity(uid, opp_id)["updated_at"]
        import time; time.sleep(0.01)
        update_opportunity(uid, opp_id, {"notes": "Changed"})
        after = get_opportunity(uid, opp_id)["updated_at"]
        assert after >= before


# ---------------------------------------------------------------------------
# Migration file
# ---------------------------------------------------------------------------

class TestMigrationFile:
    def test_007_file_exists(self):
        from pathlib import Path
        p = Path(__file__).parent.parent / "migrations" / "007_opportunities.sql"
        assert p.exists(), "migrations/007_opportunities.sql not found"

    def test_007_file_contains_create_table(self):
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "007_opportunities.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS opportunities" in sql

    def test_007_file_contains_indexes(self):
        from pathlib import Path
        sql = (Path(__file__).parent.parent / "migrations" / "007_opportunities.sql").read_text()
        assert "idx_opportunities_user_stage" in sql
        assert "idx_opportunities_user_due" in sql

    def test_007_probe_registered(self):
        from db import _MIGRATION_PROBES
        assert "007_opportunities.sql" in _MIGRATION_PROBES
        assert "opportunities" in _MIGRATION_PROBES["007_opportunities.sql"]
