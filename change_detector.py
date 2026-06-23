from db import (
    connect,
    clear_changes_for_date,
    insert_change,
)

_PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def detect_changes(run_date):
    """Record contract-presence and priority changes into the `changes` table.

    Field-level contract changes are recorded separately by
    update_detector.detect_field_changes() (the authoritative
    contract_field_changes writer); this detector only handles the
    NEW / REMOVED / UPGRADE / DOWNGRADE priority feed.
    """
    clear_changes_for_date(run_date)

    with connect() as con:
        dates = [
            r[0]
            for r in con.execute("""
                SELECT DISTINCT run_date
                FROM contract_snapshots
                ORDER BY run_date DESC
                LIMIT 2
            """)
        ]

        if len(dates) < 2:
            print("No previous snapshot available.")
            return

        today, yesterday = dates

        def _load(snapshot_date):
            return {
                r[0]: r[1]
                for r in con.execute(
                    "SELECT internal_id, priority FROM contract_snapshots WHERE run_date = ?",
                    (snapshot_date,),
                )
            }

        today_rows = _load(today)
        yesterday_rows = _load(yesterday)

    new_count = 0
    removed_count = 0
    priority_count = 0

    # NEW
    for internal_id in today_rows.keys() - yesterday_rows.keys():
        insert_change(
            run_date,
            "NEW",
            internal_id,
            description="New contract"
        )
        new_count += 1

    # REMOVED
    for internal_id in yesterday_rows.keys() - today_rows.keys():
        insert_change(
            run_date,
            "REMOVED",
            internal_id,
            description="Removed contract"
        )
        removed_count += 1

    # PRIORITY CHANGES
    for internal_id in today_rows.keys() & yesterday_rows.keys():
        old_priority = yesterday_rows[internal_id]
        new_priority = today_rows[internal_id]

        if old_priority != new_priority:
            old_rank = _PRIORITY_RANK.get(old_priority, 0)
            new_rank = _PRIORITY_RANK.get(new_priority, 0)
            change_type = "UPGRADE" if new_rank > old_rank else "DOWNGRADE"
            insert_change(
                run_date,
                change_type,
                internal_id,
                old_priority,
                new_priority,
                "Priority changed"
            )
            priority_count += 1

    print(
        f"Changes: NEW={new_count}, "
        f"REMOVED={removed_count}, "
        f"PRIORITY={priority_count}"
    )
