import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = "contracts.db"

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            internal_id TEXT PRIMARY KEY,
            award_id TEXT,
            vendor TEXT,
            agency TEXT,
            sub_agency TEXT,
            value REAL,
            start_date TEXT,
            end_date TEXT,
            days_remaining INTEGER,
            competition_type TEXT,
            solicitation_id TEXT,
            recompete_score INTEGER,
            priority TEXT,
            raw_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_vendor ON contracts(vendor)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_agency ON contracts(agency)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_priority ON contracts(priority)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_contracts_score ON contracts(recompete_score DESC)")
        con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts USING fts5(
            internal_id UNINDEXED,
            vendor, agency, award_id,
            content='contracts', content_rowid='rowid'
        )
        """)
        con.execute("""
        CREATE TRIGGER IF NOT EXISTS contracts_ai AFTER INSERT ON contracts BEGIN
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id);
        END
        """)
        con.execute("""
        CREATE TRIGGER IF NOT EXISTS contracts_ad AFTER DELETE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id);
        END
        """)
        con.execute("""
        CREATE TRIGGER IF NOT EXISTS contracts_au AFTER UPDATE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id);
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id);
        END
        """)
        con.commit()

def upsert_contract(row):
    internal_id = row.get("internal_id") or row.get("generated_internal_id")
    if not internal_id:
        return

    now = datetime.now(timezone.utc).isoformat()

    with connect() as con:
        con.execute("""
        INSERT INTO contracts (
            internal_id, award_id, vendor, agency, sub_agency, value,
            start_date, end_date, days_remaining, competition_type,
            solicitation_id, recompete_score, priority, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(internal_id) DO UPDATE SET
            award_id=excluded.award_id,
            vendor=excluded.vendor,
            agency=excluded.agency,
            sub_agency=excluded.sub_agency,
            value=excluded.value,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            days_remaining=excluded.days_remaining,
            competition_type=excluded.competition_type,
            solicitation_id=excluded.solicitation_id,
            recompete_score=excluded.recompete_score,
            priority=excluded.priority,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """, (
            internal_id,
            row.get("award_id"),
            row.get("vendor"),
            row.get("agency"),
            row.get("sub_agency"),
            float(row.get("value") or 0),
            row.get("start_date"),
            row.get("end_date"),
            int(row.get("days_remaining") or 0),
            row.get("competition_type"),
            row.get("solicitation_id"),
            int(row.get("score") or row.get("recompete_score") or 0),
            row.get("priority"),
            json.dumps(row, default=str),
            now,
        ))
        con.commit()

def init_snapshots_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS contract_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            internal_id TEXT NOT NULL,
            award_id TEXT,
            vendor TEXT,
            agency TEXT,
            sub_agency TEXT,
            value REAL,
            start_date TEXT,
            end_date TEXT,
            days_remaining INTEGER,
            competition_type TEXT,
            solicitation_id TEXT,
            recompete_score INTEGER,
            priority TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_date, internal_id)
        )
        """)
        con.commit()

def save_snapshot(run_date, rows):
    init_db()
    init_snapshots_table()

    with connect() as con:
        for row in rows:
            internal_id = row.get("internal_id") or row.get("generated_internal_id")
            if not internal_id:
                continue

            con.execute("""
            INSERT INTO contracts (
                internal_id, award_id, vendor, agency, sub_agency, value,
                start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(internal_id) DO UPDATE SET
                award_id=excluded.award_id,
                vendor=excluded.vendor,
                agency=excluded.agency,
                sub_agency=excluded.sub_agency,
                value=excluded.value,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                days_remaining=excluded.days_remaining,
                competition_type=excluded.competition_type,
                solicitation_id=excluded.solicitation_id,
                recompete_score=excluded.recompete_score,
                priority=excluded.priority,
                raw_json=excluded.raw_json,
                updated_at=CURRENT_TIMESTAMP
            """, (
                internal_id,
                row.get("award_id") or row.get("contract"),
                row.get("vendor"),
                row.get("agency"),
                row.get("sub_agency"),
                float(row.get("value") or 0),
                row.get("start_date"),
                row.get("end_date"),
                int(row.get("days_remaining") or 0),
                row.get("competition_type"),
                row.get("solicitation_id"),
                int(row.get("recompete_score") or row.get("score") or 0),
                row.get("priority"),
                json.dumps(row, default=str),
            ))

            con.execute("""
            INSERT INTO contract_snapshots (
                run_date, internal_id, award_id, vendor, agency, sub_agency,
                value, start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_date, internal_id) DO UPDATE SET
                award_id=excluded.award_id,
                vendor=excluded.vendor,
                agency=excluded.agency,
                sub_agency=excluded.sub_agency,
                value=excluded.value,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                days_remaining=excluded.days_remaining,
                competition_type=excluded.competition_type,
                solicitation_id=excluded.solicitation_id,
                recompete_score=excluded.recompete_score,
                priority=excluded.priority,
                raw_json=excluded.raw_json
            """, (
                run_date,
                internal_id,
                row.get("award_id") or row.get("contract"),
                row.get("vendor"),
                row.get("agency"),
                row.get("sub_agency"),
                float(row.get("value") or 0),
                row.get("start_date"),
                row.get("end_date"),
                int(row.get("days_remaining") or 0),
                row.get("competition_type"),
                row.get("solicitation_id"),
                int(row.get("recompete_score") or row.get("score") or 0),
                row.get("priority"),
                json.dumps(row, default=str),
            ))

        con.commit()

def init_changes_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            change_type TEXT NOT NULL,
            internal_id TEXT NOT NULL,
            old_priority TEXT,
            new_priority TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.commit()

def clear_changes_for_date(run_date):
    init_changes_table()
    with connect() as con:
        con.execute("DELETE FROM changes WHERE run_date = ?", (run_date,))
        con.commit()

def insert_change(run_date, change_type, internal_id,
                  old_priority=None, new_priority=None,
                  description=""):
    init_changes_table()
    with connect() as con:
        con.execute("""
        INSERT INTO changes (
            run_date,
            change_type,
            internal_id,
            old_priority,
            new_priority,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_date,
            change_type,
            internal_id,
            old_priority,
            new_priority,
            description,
        ))
        con.commit()

def change_summary(run_date):
    init_changes_table()
    with connect() as con:
        rows = con.execute("""
            SELECT change_type, COUNT(*)
            FROM changes
            WHERE run_date = ?
            GROUP BY change_type
        """, (run_date,)).fetchall()
    return {change_type: count for change_type, count in rows}

def get_changes(run_date, change_type):
    init_changes_table()
    with connect() as con:
        return con.execute("""
            SELECT
                ch.change_type,
                ch.internal_id,
                ch.old_priority,
                ch.new_priority,
                ch.description,
                c.vendor,
                c.agency,
                c.value,
                c.days_remaining,
                c.recompete_score,
                c.priority
            FROM changes ch
            LEFT JOIN contracts c
              ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
              AND ch.change_type = ?
            ORDER BY c.recompete_score DESC, c.value DESC
        """, (run_date, change_type)).fetchall()

def init_saved_searches_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filters TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.commit()

def create_saved_search(name: str, filters: dict) -> int:
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute(
            "INSERT INTO saved_searches (name, filters) VALUES (?, ?)",
            (name, _json.dumps(filters)),
        )
        con.commit()
        return cur.lastrowid

def get_saved_searches() -> list:
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        rows = con.execute(
            "SELECT id, name, filters, created_at FROM saved_searches ORDER BY id DESC"
        ).fetchall()
    return [
        {"id": r[0], "name": r[1], "filters": _json.loads(r[2]), "created_at": r[3]}
        for r in rows
    ]

def get_saved_search(search_id: int) -> dict | None:
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        row = con.execute(
            "SELECT id, name, filters, created_at FROM saved_searches WHERE id = ?",
            (search_id,),
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "filters": _json.loads(row[2]), "created_at": row[3]}

def rename_saved_search(search_id: int, name: str) -> bool:
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute(
            "UPDATE saved_searches SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name, search_id),
        )
        con.commit()
        return cur.rowcount > 0

def delete_saved_search(search_id: int) -> bool:
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
        con.commit()
        return cur.rowcount > 0


_SORTABLE = {"recompete_score", "value", "days_remaining", "end_date", "priority", "vendor", "agency"}

def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score", direction="desc", page=1, limit=25):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if q:
        base = """
            FROM contracts c
            JOIN contracts_fts f ON c.rowid = f.rowid
            WHERE contracts_fts MATCH ?
        """
        params = [q + "*"]
    else:
        base = "FROM contracts c WHERE 1=1"
        params = []

    if agency:
        base += " AND c.agency LIKE ?"
        params.append(f"%{agency}%")

    if priority:
        base += " AND c.priority = ?"
        params.append(priority)

    if days is not None:
        base += " AND c.days_remaining <= ?"
        params.append(int(days))

    if min_value is not None:
        base += " AND c.value >= ?"
        params.append(float(min_value))

    col = sort if sort in _SORTABLE else "recompete_score"
    order = "ASC" if direction == "asc" else "DESC"

    total = cur.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows = cur.execute(f"SELECT c.* {base} ORDER BY c.{col} {order} LIMIT ? OFFSET ?", params + [limit, (page - 1) * limit]).fetchall()
    conn.close()

    return {
        "contracts": rows,
        "page": page,
        "start": (page - 1) * limit,
        "total": total,
        "count": len(rows),
    }
