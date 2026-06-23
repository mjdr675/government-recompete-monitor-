"""Tests that the janitorial ingest pipeline persists to the database.

Regression coverage for the bug where ``janitorial_recompete_report.main()``
(invoked by the scheduled ``tasks.run_ingest`` job) only wrote a CSV and never
touched the contracts database. The pipeline must (a) populate ``contracts``,
(b) write a point-in-time row to ``contract_snapshots``, and (c) be safe to
rerun without duplicating rows.
"""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import text

import db as db_module


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module._cached_engine.cache_clear()
    db_module.init_db()
    # Run inside tmp_path so the CSV write lands in a scratch dir, not the repo.
    monkeypatch.chdir(tmp_path)
    yield db_path
    db_module._cached_engine.cache_clear()


_FAKE_AWARDS = [
    {
        "Award ID": "AWD-1",
        "Recipient Name": "Acme Janitorial",
        "Award Amount": "500000",
        "Start Date": "2025-01-01",
        "End Date": "2026-09-01",
        "Awarding Agency": "DEFENSE",
        "Awarding Sub Agency": "ARMY",
        "Description": "Custodial services",
        "generated_internal_id": "CONT_AWD_1",
    },
    {
        "Award ID": "AWD-2",
        "Recipient Name": "Beta Facilities",
        "Award Amount": "1200000",
        "Start Date": "2025-02-01",
        "End Date": "2026-10-15",
        "Awarding Agency": "VETERANS AFFAIRS",
        "Awarding Sub Agency": "VHA",
        "Description": "Grounds maintenance",
        "generated_internal_id": "CONT_AWD_2",
    },
]


def _count(table):
    with db_module.get_engine().connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def test_main_persists_contracts_to_db(test_db):
    import janitorial_recompete_report as jrr

    with patch.object(jrr, "fetch_contracts", return_value=list(_FAKE_AWARDS)):
        jrr.main()

    assert _count("contracts") == 2
    assert _count("contract_snapshots") == 2

    with db_module.get_engine().connect() as conn:
        row = conn.execute(text(
            "SELECT vendor, agency, priority, recompete_score FROM contracts"
            " WHERE internal_id = 'CONT_AWD_2'"
        )).mappings().fetchone()
    assert row["vendor"] == "Beta Facilities"
    assert row["agency"] == "VETERANS AFFAIRS"
    assert row["priority"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_main_is_idempotent_on_rerun(test_db):
    import janitorial_recompete_report as jrr

    with patch.object(jrr, "fetch_contracts", return_value=list(_FAKE_AWARDS)):
        jrr.main()
        jrr.main()

    # Upsert keyed on internal_id + UNIQUE(run_date, internal_id) → no duplicates.
    assert _count("contracts") == 2
    assert _count("contract_snapshots") == 2


def test_main_fts_index_is_searchable_after_ingest(test_db):
    import janitorial_recompete_report as jrr

    with patch.object(jrr, "fetch_contracts", return_value=list(_FAKE_AWARDS)):
        jrr.main()

    with db_module.get_engine().connect() as conn:
        hits = conn.execute(text(
            "SELECT internal_id FROM contracts_fts WHERE contracts_fts MATCH 'Acme'"
        )).fetchall()
    assert len(hits) == 1
