import json
import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import create_engine, text

# Allow DB_PATH to be overridden via environment variable so Railway can point
# it at a persistent volume (e.g. DB_PATH=/data/contracts.db). Falls back to
# the local working-directory path for development.
DB_PATH = os.environ.get("DB_PATH", "contracts.db")


@lru_cache(maxsize=None)
def _cached_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


def get_engine():
    """Return a SQLAlchemy Engine for the active database (SQLite or PostgreSQL)."""
    database_url = os.environ.get("DATABASE_URL", "")
    url = database_url if database_url else f"sqlite:///{DB_PATH}"
    return _cached_engine(url)


def get_connection():
    """
    Return a native database connection (sqlite3 or psycopg2).

    Kept for backward compatibility with analytics functions and tests that
    need a native DBAPI connection.  Prefer get_engine() for new code.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        try:
            import psycopg2  # noqa: PLC0415
            return psycopg2.connect(database_url)
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            ) from exc
    return sqlite3.connect(DB_PATH)


def connect():
    """Backward-compatible wrapper around get_connection()."""
    return get_connection()


def init_db():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        # PostgreSQL schema management is handled by migrations/001_initial_pg.sql
        # applied via the Procfile release command.
        return

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
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
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contracts_vendor ON contracts(vendor)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contracts_agency ON contracts(agency)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contracts_priority ON contracts(priority)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contracts_score ON contracts(recompete_score DESC)"
        ))
        conn.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts USING fts5(
            internal_id UNINDEXED,
            vendor, agency, award_id,
            content='contracts', content_rowid='rowid'
        )
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ai AFTER INSERT ON contracts BEGIN
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ad AFTER DELETE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_au AFTER UPDATE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id);
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id);
        END
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1
        )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        ))


def upsert_contract(row):
    internal_id = row.get("internal_id") or row.get("generated_internal_id")
    if not internal_id:
        return

    now = datetime.now(timezone.utc).isoformat()

    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO contracts (
            internal_id, award_id, vendor, agency, sub_agency, value,
            start_date, end_date, days_remaining, competition_type,
            solicitation_id, recompete_score, priority, raw_json, updated_at
        )
        VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :value,
                :start_date, :end_date, :days_remaining, :competition_type,
                :solicitation_id, :recompete_score, :priority, :raw_json, :updated_at)
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
        """), {
            "internal_id": internal_id,
            "award_id": row.get("award_id"),
            "vendor": row.get("vendor"),
            "agency": row.get("agency"),
            "sub_agency": row.get("sub_agency"),
            "value": float(row.get("value") or 0),
            "start_date": row.get("start_date"),
            "end_date": row.get("end_date"),
            "days_remaining": int(row.get("days_remaining") or 0),
            "competition_type": row.get("competition_type"),
            "solicitation_id": row.get("solicitation_id"),
            "recompete_score": int(row.get("score") or row.get("recompete_score") or 0),
            "priority": row.get("priority"),
            "raw_json": json.dumps(row, default=str),
            "updated_at": now,
        })


def init_snapshots_table():
    with get_engine().begin() as conn:
        conn.execute(text("""
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
        """))


def save_snapshot(run_date, rows):
    init_db()
    init_snapshots_table()

    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"

    with engine.begin() as conn:
        for row in rows:
            internal_id = row.get("internal_id") or row.get("generated_internal_id")
            if not internal_id:
                continue

            conn.execute(text("""
            INSERT INTO contracts (
                internal_id, award_id, vendor, agency, sub_agency, value,
                start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json, updated_at
            )
            VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :value,
                    :start_date, :end_date, :days_remaining, :competition_type,
                    :solicitation_id, :recompete_score, :priority, :raw_json, CURRENT_TIMESTAMP)
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
            """), {
                "internal_id": internal_id,
                "award_id": row.get("award_id") or row.get("contract"),
                "vendor": row.get("vendor"),
                "agency": row.get("agency"),
                "sub_agency": row.get("sub_agency"),
                "value": float(row.get("value") or 0),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "days_remaining": int(row.get("days_remaining") or 0),
                "competition_type": row.get("competition_type"),
                "solicitation_id": row.get("solicitation_id"),
                "recompete_score": int(row.get("recompete_score") or row.get("score") or 0),
                "priority": row.get("priority"),
                "raw_json": json.dumps(row, default=str),
            })

            conn.execute(text("""
            INSERT INTO contract_snapshots (
                run_date, internal_id, award_id, vendor, agency, sub_agency,
                value, start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json
            )
            VALUES (:run_date, :internal_id, :award_id, :vendor, :agency, :sub_agency,
                    :value, :start_date, :end_date, :days_remaining, :competition_type,
                    :solicitation_id, :recompete_score, :priority, :raw_json)
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
            """), {
                "run_date": run_date,
                "internal_id": internal_id,
                "award_id": row.get("award_id") or row.get("contract"),
                "vendor": row.get("vendor"),
                "agency": row.get("agency"),
                "sub_agency": row.get("sub_agency"),
                "value": float(row.get("value") or 0),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "days_remaining": int(row.get("days_remaining") or 0),
                "competition_type": row.get("competition_type"),
                "solicitation_id": row.get("solicitation_id"),
                "recompete_score": int(row.get("recompete_score") or row.get("score") or 0),
                "priority": row.get("priority"),
                "raw_json": json.dumps(row, default=str),
            })

        # Rebuild FTS index after batch upserts. ON CONFLICT DO UPDATE does not
        # fire AFTER UPDATE triggers in SQLite, so stale FTS entries can accumulate.
        # A manual rebuild syncs the index from scratch.
        if not is_pg:
            conn.execute(text("INSERT INTO contracts_fts(contracts_fts) VALUES ('rebuild')"))


def init_changes_table():
    with get_engine().begin() as conn:
        conn.execute(text("""
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
        """))


def clear_changes_for_date(run_date):
    init_changes_table()
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM changes WHERE run_date = :run_date"),
            {"run_date": run_date},
        )


def insert_change(run_date, change_type, internal_id,
                  old_priority=None, new_priority=None,
                  description=""):
    init_changes_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO changes (
            run_date,
            change_type,
            internal_id,
            old_priority,
            new_priority,
            description
        )
        VALUES (:run_date, :change_type, :internal_id,
                :old_priority, :new_priority, :description)
        """), {
            "run_date": run_date,
            "change_type": change_type,
            "internal_id": internal_id,
            "old_priority": old_priority,
            "new_priority": new_priority,
            "description": description,
        })


def change_summary(run_date):
    init_changes_table()
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT change_type, COUNT(*)
            FROM changes
            WHERE run_date = :run_date
            GROUP BY change_type
        """), {"run_date": run_date}).fetchall()
    return {row[0]: row[1] for row in rows}


def get_changes(run_date, change_type):
    init_changes_table()
    with get_engine().connect() as conn:
        return conn.execute(text("""
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
            WHERE ch.run_date = :run_date
              AND ch.change_type = :change_type
            ORDER BY c.recompete_score DESC, c.value DESC
        """), {
            "run_date": run_date,
            "change_type": change_type,
        }).mappings().fetchall()


def init_demo_table():
    with get_engine().begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS demo_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT,
            company TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            hubspot_contact_id TEXT,
            hubspot_deal_id TEXT
        )
        """))


def save_demo_request(
    email: str,
    name: str = "",
    company: str = "",
    phone: str = "",
    notes: str = "",
    hubspot_contact_id: str | None = None,
    hubspot_deal_id: str | None = None,
) -> None:
    init_demo_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO demo_requests (email, name, company, phone, notes, hubspot_contact_id, hubspot_deal_id)
        VALUES (:email, :name, :company, :phone, :notes, :hubspot_contact_id, :hubspot_deal_id)
        """), {
            "email": email,
            "name": name,
            "company": company,
            "phone": phone,
            "notes": notes,
            "hubspot_contact_id": hubspot_contact_id,
            "hubspot_deal_id": hubspot_deal_id,
        })


def init_early_access_table():
    with get_engine().begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS early_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            hubspot_contact_id TEXT
        )
        """))


def save_early_access(email: str, hubspot_contact_id: str | None = None) -> None:
    init_early_access_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO early_access (email, hubspot_contact_id)
        VALUES (:email, :hubspot_contact_id)
        ON CONFLICT(email) DO UPDATE SET hubspot_contact_id = excluded.hubspot_contact_id
        """), {
            "email": email,
            "hubspot_contact_id": hubspot_contact_id,
        })


_SORTABLE = {"recompete_score", "value", "days_remaining", "end_date", "priority", "vendor", "agency"}


def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score", direction="desc", page=1, limit=25):
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"

    params: dict = {}

    if q:
        if is_pg:
            base = "FROM contracts c WHERE c.search_vector @@ websearch_to_tsquery('english', :q)"
            params["q"] = q
        else:
            base = """
                FROM contracts c
                JOIN contracts_fts f ON c.rowid = f.rowid
                WHERE contracts_fts MATCH :q
            """
            params["q"] = q + "*"
    else:
        base = "FROM contracts c WHERE 1=1"

    if agency:
        base += " AND c.agency LIKE :agency"
        params["agency"] = f"%{agency}%"

    if priority:
        base += " AND c.priority = :priority"
        params["priority"] = priority

    if days is not None:
        base += " AND c.days_remaining <= :days"
        params["days"] = int(days)

    if min_value is not None:
        base += " AND c.value >= :min_value"
        params["min_value"] = float(min_value)

    col = sort if sort in _SORTABLE else "recompete_score"
    order = "ASC" if direction == "asc" else "DESC"

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
        rows = conn.execute(
            text(f"SELECT c.* {base} ORDER BY c.{col} {order} LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": (page - 1) * limit},
        ).mappings().fetchall()

    return {
        "contracts": rows,
        "page": page,
        "start": (page - 1) * limit,
        "total": total,
        "count": len(rows),
    }
