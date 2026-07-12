from sqlalchemy import text

from db import get_engine, init_changes_table

_PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def detect_changes(run_date):
    """Record contract-presence and priority changes into the `changes` table.

    Field-level contract changes are recorded separately by
    update_detector.detect_field_changes() (the authoritative
    contract_field_changes writer); this detector only handles the
    NEW / REMOVED / UPGRADE / DOWNGRADE priority feed.

    Uses the shared SQLAlchemy engine (dialect-safe on SQLite and PostgreSQL):
    reads go through engine.connect() with bound parameters, and the clear+insert
    write runs in a single engine.begin() transaction so a failure leaves no
    partial change rows.
    """
    engine = get_engine()

    # Read phase: the two most recent snapshot dates + per-contract priorities.
    with engine.connect() as con:
        dates = [
            r[0]
            for r in con.execute(
                text(
                    "SELECT DISTINCT run_date FROM contract_snapshots "
                    "ORDER BY run_date DESC LIMIT 2"
                )
            )
        ]

        have_comparison = len(dates) >= 2
        today_rows = {}
        yesterday_rows = {}
        if have_comparison:
            today, yesterday = dates

            def _load(snapshot_date):
                return {
                    r[0]: r[1]
                    for r in con.execute(
                        text(
                            "SELECT internal_id, priority FROM contract_snapshots "
                            "WHERE run_date = :run_date"
                        ),
                        {"run_date": snapshot_date},
                    )
                }

            today_rows = _load(today)
            yesterday_rows = _load(yesterday)

    if not have_comparison:
        print("No previous snapshot available.")

    # Compute the priority feed (change semantics unchanged; empty when we can't
    # compare). IDs within each category are sorted so the persisted order is
    # deterministic rather than dependent on set iteration order.
    records = []
    for internal_id in sorted(today_rows.keys() - yesterday_rows.keys()):
        records.append(
            {
                "change_type": "NEW",
                "internal_id": internal_id,
                "old_priority": None,
                "new_priority": None,
                "description": "New contract",
            }
        )
    for internal_id in sorted(yesterday_rows.keys() - today_rows.keys()):
        records.append(
            {
                "change_type": "REMOVED",
                "internal_id": internal_id,
                "old_priority": None,
                "new_priority": None,
                "description": "Removed contract",
            }
        )
    for internal_id in sorted(today_rows.keys() & yesterday_rows.keys()):
        old_priority = yesterday_rows[internal_id]
        new_priority = today_rows[internal_id]
        if old_priority != new_priority:
            old_rank = _PRIORITY_RANK.get(old_priority, 0)
            new_rank = _PRIORITY_RANK.get(new_priority, 0)
            change_type = "UPGRADE" if new_rank > old_rank else "DOWNGRADE"
            records.append(
                {
                    "change_type": change_type,
                    "internal_id": internal_id,
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "description": "Priority changed",
                }
            )

    # Write phase: clear + insert atomically — a failure rolls back everything, so
    # no partial change rows are left, and a rerun is idempotent (DELETE then insert).
    init_changes_table()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM changes WHERE run_date = :run_date"),
            {"run_date": run_date},
        )
        for rec in records:
            conn.execute(
                text(
                    "INSERT INTO changes "
                    "(run_date, change_type, internal_id, old_priority, new_priority, description) "
                    "VALUES (:run_date, :change_type, :internal_id, :old_priority, "
                    ":new_priority, :description)"
                ),
                {"run_date": run_date, **rec},
            )

    if have_comparison:
        new_count = sum(1 for r in records if r["change_type"] == "NEW")
        removed_count = sum(1 for r in records if r["change_type"] == "REMOVED")
        priority_count = sum(
            1 for r in records if r["change_type"] in ("UPGRADE", "DOWNGRADE")
        )
        print(
            f"Changes: NEW={new_count}, REMOVED={removed_count}, PRIORITY={priority_count}"
        )
