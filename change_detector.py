from db import (
    connect,
    clear_changes_for_date,
    insert_change,
    clear_field_changes_for_date,
    insert_field_change,
)

_PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Contract fields tracked for field-level change detection. Each is compared
# between the two most recent snapshots of the same contract; any difference is
# recorded in contract_field_changes.
_TRACKED_FIELDS = (
    "value",
    "end_date",
    "days_remaining",
    "vendor",
    "competition_type",
    "recompete_score",
    "priority",
)

_SNAPSHOT_COLUMNS = ("id", "internal_id", "priority") + tuple(
    f for f in _TRACKED_FIELDS if f != "priority"
)


def _norm(value):
    """Stringify a field value for storage/comparison; preserve None as None."""
    return None if value is None else str(value)


def detect_changes(run_date):
    clear_changes_for_date(run_date)
    clear_field_changes_for_date(run_date)

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

        cols = ", ".join(_SNAPSHOT_COLUMNS)

        def _load(snapshot_date):
            return {
                row["internal_id"]: row
                for row in (
                    dict(zip(_SNAPSHOT_COLUMNS, r))
                    for r in con.execute(
                        f"SELECT {cols} FROM contract_snapshots WHERE run_date = ?",
                        (snapshot_date,),
                    )
                )
            }

        today_rows = _load(today)
        yesterday_rows = _load(yesterday)

    new_count = 0
    removed_count = 0
    priority_count = 0
    field_count = 0

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

    # PRIORITY CHANGES (existing semantic changes table) + FIELD-LEVEL CHANGES
    for internal_id in today_rows.keys() & yesterday_rows.keys():
        old_row = yesterday_rows[internal_id]
        new_row = today_rows[internal_id]

        old_priority = old_row["priority"]
        new_priority = new_row["priority"]

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

        # Field-level diff across the tracked fields.
        for field in _TRACKED_FIELDS:
            old_value = old_row[field]
            new_value = new_row[field]
            if old_value != new_value:
                insert_field_change(
                    run_date,
                    internal_id,
                    field,
                    _norm(old_value),
                    _norm(new_value),
                    old_snapshot_id=old_row["id"],
                    new_snapshot_id=new_row["id"],
                )
                field_count += 1

    print(
        f"Changes: NEW={new_count}, "
        f"REMOVED={removed_count}, "
        f"PRIORITY={priority_count}, "
        f"FIELDS={field_count}"
    )
