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
