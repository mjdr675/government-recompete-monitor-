"""Generic field-level contract change detection (Auto Contract Updates lane).

Compares the two most recent ``contract_snapshots`` rows for each ``internal_id``
and records field-level changes to the ``contract_field_changes`` table.

Kept deliberately separate from ``change_detector.py`` (which records only the
priority-based NEW / REMOVED / UPGRADE / DOWNGRADE rows into the ``changes``
table) so that existing change-detection, ``report_builder`` and the vendor
``change_events`` feed all keep working unchanged.

``diff_snapshot_fields`` is a pure function (no DB, no I/O) so it is trivially
testable. ``detect_field_changes`` orchestrates the snapshot reads/writes.
"""

from sqlalchemy import text

from db import (
    get_engine,
    init_snapshots_table,
    clear_field_changes_for_date,
    insert_field_changes,
)

# Fields whose changes we surface to users, grouped by how the change kind is
# classified.  Order here is the order changes are emitted in (deterministic).
_NUMERIC_FIELDS = ("value", "days_remaining", "recompete_score")
_TEXT_FIELDS = ("vendor", "end_date", "competition_type", "priority")
TRACKED_FIELDS = _NUMERIC_FIELDS + _TEXT_FIELDS


def _norm_numeric(v):
    """Coerce a snapshot value to float, or None when blank/unparseable."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_text(v):
    """Normalise a text field to a stripped string, or '' when blank."""
    if v is None:
        return ""
    return str(v).strip()


def _fmt_numeric(v):
    """Render a normalised numeric as a compact string for storage/display."""
    if v is None:
        return None
    if float(v).is_integer():
        return str(int(v))
    return str(v)


def diff_snapshot_fields(prev, curr):
    """Return the list of field-level changes between two snapshot rows.

    ``prev`` and ``curr`` are mapping-like (dict) snapshot rows. Returns a list
    of dicts: ``{field_name, old_value, new_value, change_kind}`` where
    change_kind is one of INCREASE / DECREASE / SET / CLEARED / MODIFIED.

    days_remaining naturally decrements by ~1 every day as the clock advances,
    which is not a meaningful "update".  So a days_remaining change is only
    reported when ``end_date`` also changed in the same diff — i.e. the recompete
    date genuinely moved, rather than time simply passing.
    """
    changes = []

    for field in _NUMERIC_FIELDS:
        old = _norm_numeric(prev.get(field))
        new = _norm_numeric(curr.get(field))
        if old is None and new is None:
            continue
        # value: compare to the cent to avoid float-representation noise.
        if field == "value" and old is not None and new is not None:
            if round(old, 2) == round(new, 2):
                continue
        if old == new:
            continue
        if old is None:
            kind = "SET"
        elif new is None:
            kind = "CLEARED"
        elif new > old:
            kind = "INCREASE"
        else:
            kind = "DECREASE"
        changes.append({
            "field_name": field,
            "old_value": _fmt_numeric(old),
            "new_value": _fmt_numeric(new),
            "change_kind": kind,
        })

    for field in _TEXT_FIELDS:
        old = _norm_text(prev.get(field))
        new = _norm_text(curr.get(field))
        if old == new:
            continue
        if not old:
            kind = "SET"
        elif not new:
            kind = "CLEARED"
        else:
            kind = "MODIFIED"
        changes.append({
            "field_name": field,
            "old_value": old or None,
            "new_value": new or None,
            "change_kind": kind,
        })

    # Suppress pure clock-drift: keep days_remaining only when end_date moved too.
    changed_fields = {c["field_name"] for c in changes}
    if "days_remaining" in changed_fields and "end_date" not in changed_fields:
        changes = [c for c in changes if c["field_name"] != "days_remaining"]

    return changes


def detect_field_changes(run_date):
    """Detect and persist field-level changes for ``run_date``.

    Compares the two most recent snapshot run_dates. Idempotent: clears any
    existing field-change rows for run_date first. Returns the number of change
    rows written. A no-op (returns 0) when fewer than two snapshots exist.
    """
    init_snapshots_table()
    clear_field_changes_for_date(run_date)

    cols = ("internal_id",) + TRACKED_FIELDS
    select_cols = ", ".join(cols)

    # Dialect-safe reads via the shared SQLAlchemy engine (bound run_date param).
    # select_cols is a fixed list of TRACKED_FIELDS identifiers (not user input);
    # only the run_date value is bound.
    with get_engine().connect() as con:
        dates = [
            r[0]
            for r in con.execute(
                text(
                    "SELECT DISTINCT run_date FROM contract_snapshots"
                    " ORDER BY run_date DESC LIMIT 2"
                )
            )
        ]
        if len(dates) < 2:
            print("detect_field_changes: fewer than two snapshots; nothing to compare.")
            return 0

        today, yesterday = dates

        def _load(date):
            out = {}
            for r in con.execute(
                text(
                    f"SELECT {select_cols} FROM contract_snapshots WHERE run_date = :run_date"
                ),
                {"run_date": date},
            ):
                d = dict(zip(cols, r))
                out[d["internal_id"]] = d
            return out

        curr = _load(today)
        prev = _load(yesterday)

    records = []
    for internal_id in curr.keys() & prev.keys():
        for change in diff_snapshot_fields(prev[internal_id], curr[internal_id]):
            change["internal_id"] = internal_id
            records.append(change)

    insert_field_changes(run_date, records)
    print(f"detect_field_changes: recorded {len(records)} field change(s) for {run_date}.")
    return len(records)


if __name__ == "__main__":
    from datetime import date
    detect_field_changes(str(date.today()))
