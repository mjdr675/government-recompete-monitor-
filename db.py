import sqlite3

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
        con.commit()

def upsert_contract(row):
    fields = [
        "internal_id", "award_id", "vendor", "agency", "sub_agency",
        "value", "start_date", "end_date", "days_remaining",
        "competition_type", "solicitation_id", "recompete_score",
        "priority", "raw_json"
    ]

    values = {field: row.get(field) for field in fields}

    with connect() as con:
        con.execute("""
        INSERT INTO contracts (
            internal_id, award_id, vendor, agency, sub_agency,
            value, start_date, end_date, days_remaining,
            competition_type, solicitation_id, recompete_score,
            priority, raw_json, updated_at
        )
        VALUES (
            :internal_id, :award_id, :vendor, :agency, :sub_agency,
            :value, :start_date, :end_date, :days_remaining,
            :competition_type, :solicitation_id, :recompete_score,
            :priority, :raw_json, CURRENT_TIMESTAMP
        )
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
        """, values)
        con.commit()

def init_snapshots_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            run_date TEXT,
            internal_id TEXT,
            recompete_score INTEGER,
            priority TEXT,
            PRIMARY KEY (run_date, internal_id)
        )
        """)
        con.commit()

def save_snapshot(run_date, rows):
    init_snapshots_table()
    with connect() as con:
        con.executemany("""
        INSERT OR REPLACE INTO snapshots (
            run_date, internal_id, recompete_score, priority
        )
        VALUES (
            :run_date, :internal_id, :recompete_score, :priority
        )
        """, [
            {
                "run_date": run_date,
                "internal_id": row.get("internal_id"),
                "recompete_score": row.get("recompete_score"),
                "priority": row.get("priority")
            }
            for row in rows
            if row.get("internal_id")
        ])
        con.commit()

def init_changes_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT,
            change_type TEXT,
            internal_id TEXT,
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

def insert_change(run_date, change_type, internal_id, old_priority=None, new_priority=None, description=""):
    init_changes_table()
    with connect() as con:
        con.execute("""
        INSERT INTO changes (
            run_date, change_type, internal_id, old_priority, new_priority, description
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (run_date, change_type, internal_id, old_priority, new_priority, description))
        con.commit()
