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
