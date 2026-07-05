"""Tests for recipient_uei normalization on write + one-time backfill.

Addresses CodeRabbit finding on PR #37: my_current_contracts() does an exact
recipient_uei match against a normalized profile UEI, but save_snapshot() used
to store raw values and there was no backfill for pre-existing rows. Result:
contract rows persisted before the fix silently missed UEI matches.

These two tests lock in that:
  1. New snapshots go in already normalized (strip whitespace + upper).
  2. The _ensure_ci_columns() migration path backfills raw rows in place, so
     a legacy DB starts matching immediately on next startup.

Isolated file; does not exercise app.py or the Flask stack.
"""

import pytest
from sqlalchemy import text

import db as db_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


# ---------------------------------------------------------------------------
# save_snapshot writes normalized recipient_uei
# ---------------------------------------------------------------------------

def test_save_snapshot_normalizes_recipient_uei_on_write(db):
    """A raw recipient_uei (mixed case + surrounding whitespace) must be
    stored normalized so my_current_contracts()' exact-match SQL against a
    normalized profile UEI still hits."""
    raw = "  abc123def456  "
    db_module.save_snapshot("2026-06-19", [
        {
            "internal_id": "UEI-NORM-001",
            "vendor": "Acme Corp",
            "agency": "GSA",
            "award_id": "AW-UEI-001",
            "value": 100_000,
            "recompete_score": 60,
            "priority": "MEDIUM",
            "recipient_uei": raw,
        },
    ])

    engine = db_module.get_engine()
    with engine.connect() as conn:
        stored = conn.execute(text(
            "SELECT recipient_uei FROM contracts WHERE internal_id = :i"
        ), {"i": "UEI-NORM-001"}).scalar()

    # Expect strip-all-whitespace + upper.
    assert stored == "ABC123DEF456"
    # An exact-match SQL against the same normalized value must hit.
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM contracts WHERE recipient_uei = :u"
        ), {"u": "ABC123DEF456"}).scalar()
    assert n == 1


# ---------------------------------------------------------------------------
# _ensure_ci_columns() backfills raw pre-existing rows in place
# ---------------------------------------------------------------------------

def test_ensure_ci_columns_backfills_raw_recipient_uei(db):
    """Simulate a row written before normalization existed on write: insert a
    raw recipient_uei directly, then trigger the migration path (which is
    called on every startup / init_db) and confirm the value is now
    normalized, so my_current_contracts()' exact match starts hitting it."""
    engine = db_module.get_engine()

    # Bypass save_snapshot to simulate a "legacy" row with a raw UEI stored
    # before the normalize-on-write fix landed.
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO contracts (
                internal_id, award_id, vendor, agency, sub_agency,
                value, start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json,
                recipient_uei
            ) VALUES (
                :internal_id, :award_id, :vendor, :agency, :sub_agency,
                :value, :start_date, :end_date, :days_remaining, :competition_type,
                :solicitation_id, :recompete_score, :priority, :raw_json,
                :recipient_uei
            )
        """), {
            "internal_id": "UEI-LEGACY-001", "award_id": "AW-LEG-001",
            "vendor": "Legacy LLC", "agency": "DOD", "sub_agency": None,
            "value": 250_000.0, "start_date": None, "end_date": None,
            "days_remaining": 0, "competition_type": None,
            "solicitation_id": None, "recompete_score": 50, "priority": "LOW",
            "raw_json": "{}",
            "recipient_uei": "  legacy0001abc  ",  # raw: lowercase + whitespace
        })

    # Confirm it's genuinely raw before the migration runs.
    with engine.connect() as conn:
        pre = conn.execute(text(
            "SELECT recipient_uei FROM contracts WHERE internal_id = :i"
        ), {"i": "UEI-LEGACY-001"}).scalar()
    assert pre == "  legacy0001abc  "

    # Trigger the migration path in place. _ensure_ci_columns() runs during
    # init_db() and is idempotent — running it again does the backfill.
    db_module._ensure_ci_columns()

    with engine.connect() as conn:
        post = conn.execute(text(
            "SELECT recipient_uei FROM contracts WHERE internal_id = :i"
        ), {"i": "UEI-LEGACY-001"}).scalar()
    assert post == "LEGACY0001ABC", (
        f"backfill did not normalize raw recipient_uei; got {post!r}"
    )

    # And re-running the migration must be a no-op (idempotent).
    db_module._ensure_ci_columns()
    with engine.connect() as conn:
        again = conn.execute(text(
            "SELECT recipient_uei FROM contracts WHERE internal_id = :i"
        ), {"i": "UEI-LEGACY-001"}).scalar()
    assert again == "LEGACY0001ABC"
