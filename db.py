import glob
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Migration version tracking
# ---------------------------------------------------------------------------

# Detection queries for migrations that existed before version tracking was
# introduced (001–005).  Used exactly once: when _apply_migrations() finds
# schema_migrations empty on a non-empty database (i.e. an existing install
# that predates tracking).  Each query returns a count > 0 when the migration
# artefact already exists on the live database, meaning we can stamp it as
# applied without re-executing — most critically, avoiding the unnecessary
# search_vector rebuild from 005 on every subsequent startup.
_MIGRATION_PROBES: dict = {
    "001_initial_pg.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'contracts'"
    ),
    "002_subscription_and_alerts.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'stripe_customer_id'"
    ),
    "003_company_name.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'company_name'"
    ),
    "004_contracts_days_remaining_index.sql": (
        "SELECT COUNT(*) FROM pg_indexes "
        "WHERE indexname = 'idx_contracts_days_remaining'"
    ),
    "005_contracts_description_search.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'description'"
    ),
}


def _stamp_pre_existing(engine, applied: set) -> None:
    """Stamp migrations that predate version tracking by probing the live schema.

    Called once when schema_migrations is empty on a non-empty database.
    PG-only: SQLite never runs the migration files, so nothing to stamp there.

    For each migration in _MIGRATION_PROBES, runs the detection query. If the
    artefact already exists the migration is recorded as applied (with a sentinel
    timestamp prefixed 'detected:') without re-executing its SQL.  The applied
    set is updated in-place so the caller skips those files.
    """
    import logging as _log

    if engine.dialect.name != "postgresql":
        return

    now = "detected:" + datetime.now(timezone.utc).isoformat()
    stamped = []

    try:
        with engine.begin() as conn:
            for filename, probe_sql in _MIGRATION_PROBES.items():
                try:
                    count = conn.execute(text(probe_sql)).scalar() or 0
                except Exception:
                    count = 0
                if count > 0:
                    conn.execute(
                        text(
                            "INSERT INTO schema_migrations(filename, applied_at) "
                            "VALUES (:f, :a) ON CONFLICT(filename) DO NOTHING"
                        ),
                        {"f": filename, "a": now},
                    )
                    applied.add(filename)
                    stamped.append(filename)
    except Exception as exc:
        _log.warning("Migration auto-stamp failed (non-fatal): %s", exc)
        return

    if stamped:
        _log.info(
            "schema_migrations: stamped %d pre-existing migration(s): %s",
            len(stamped),
            ", ".join(stamped),
        )


def _apply_migrations(migrations_dir: "Path | None" = None) -> None:
    """Apply pending SQL migrations tracked by the schema_migrations table.

    Each migration executes atomically: its SQL statements and the
    schema_migrations INSERT run in a single transaction.  A migration is
    recorded as applied only when it succeeds.  On failure the transaction
    rolls back, an error is logged, and processing stops immediately — leaving
    all previously applied migrations untouched.

    On first use against an existing database (schema_migrations empty but
    contracts table already present), _stamp_pre_existing() detects which
    migrations have already been applied and stamps them without re-executing,
    preventing the unnecessary search_vector rebuild from migration 005.

    Args:
        migrations_dir: directory containing *.sql files.  Defaults to the
            project's own migrations/ directory.  Exposed for testing.
    """
    import logging as _log

    if migrations_dir is None:
        migrations_dir = Path(__file__).parent / "migrations"

    if not Path(migrations_dir).is_dir():
        return

    try:
        engine = get_engine()
    except Exception as exc:
        _log.warning("Skipping migrations — database engine unavailable: %s", exc)
        return

    # Bootstrap: ensure the history table exists.  This is the only operation
    # that runs unconditionally on every startup; it is a genuine no-op once
    # the table exists.
    try:
        with engine.begin() as conn:
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """))
    except Exception as exc:
        _log.warning("Skipping migrations — cannot create schema_migrations: %s", exc)
        return

    # Read the current applied set.
    try:
        with engine.connect() as conn:
            applied = {
                row[0]
                for row in conn.execute(text("SELECT filename FROM schema_migrations"))
            }
    except Exception as exc:
        _log.warning("Skipping migrations — cannot read schema_migrations: %s", exc)
        return

    # First-use bootstrap: stamp pre-existing migrations so they are not
    # re-executed against a database that already has them applied.
    if not applied:
        with engine.connect() as conn:
            try:
                db_has_tables = bool(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name = 'contracts'"
                        )
                    ).scalar()
                )
            except Exception:
                db_has_tables = False
        if db_has_tables:
            _stamp_pre_existing(engine, applied)

    # Apply pending migrations in filename order.
    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    for sql_file in sql_files:
        if sql_file.name in applied:
            _log.debug("Migration already applied, skipping: %s", sql_file.name)
            continue

        _log.info("Applying migration: %s", sql_file.name)
        statements = [
            s.strip()
            for s in sql_file.read_text().split(";")
            if s.strip() and not s.strip().startswith("--")
        ]

        try:
            with engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
                # Record success within the same transaction — atomically.
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations(filename, applied_at) "
                        "VALUES (:f, :a)"
                    ),
                    {
                        "f": sql_file.name,
                        "a": datetime.now(timezone.utc).isoformat(),
                    },
                )
            _log.info("Migration applied: %s", sql_file.name)
        except Exception as exc:
            _log.error(
                "Migration %s FAILED: %s — stopping. "
                "Fix the migration file and restart.",
                sql_file.name,
                exc,
            )
            raise


def _apply_pg_migrations() -> None:
    """Backward-compatible alias for _apply_migrations().

    Pre-versioning callers (and the test that monkeypatches this name) continue
    to work.  New code should call _apply_migrations() directly.
    """
    _apply_migrations()


def _ensure_description_column():
    """Migrate existing SQLite DBs to add description column and rebuild FTS with it.

    Returns True when the migration ran (FTS was dropped and needs recreation),
    False when no action was needed (new DB or already migrated).
    """
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return False  # table doesn't exist yet; CREATE TABLE will include description
        cols = [r[1] for r in rows]
        if "description" in cols:
            return False
        conn.execute(text("ALTER TABLE contracts ADD COLUMN description TEXT"))
        # FTS5 virtual table schema is immutable — must drop and recreate with description.
        # content='contracts' means no FTS data is lost; rebuild restores the index below.
        conn.execute(text("DROP TABLE IF EXISTS contracts_fts"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_ai"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_ad"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_au"))
    return True


def init_db():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        _apply_migrations()
        return

    needs_fts_rebuild = _ensure_description_column()

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS contracts (
            internal_id TEXT PRIMARY KEY,
            award_id TEXT,
            vendor TEXT,
            agency TEXT,
            sub_agency TEXT,
            description TEXT,
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
        # days_remaining drives the dashboard "upcoming" range scan, the open/expired
        # status filter, watchlist expiry alerts, and every vendor/agency profile
        # "ORDER BY days_remaining" — none of which had a supporting index.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contracts_days_remaining ON contracts(days_remaining)"
        ))
        conn.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts USING fts5(
            internal_id UNINDEXED,
            vendor, agency, award_id, description,
            content='contracts', content_rowid='rowid'
        )
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ai AFTER INSERT ON contracts BEGIN
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id, description)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id, new.description);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ad AFTER DELETE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id, description)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id, old.description);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_au AFTER UPDATE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id, description)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id, old.description);
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id, description)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id, new.description);
        END
        """))
        if needs_fts_rebuild:
            conn.execute(text("INSERT INTO contracts_fts(contracts_fts) VALUES ('rebuild')"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            email                   TEXT UNIQUE NOT NULL,
            password_hash           TEXT NOT NULL,
            created_at              TEXT NOT NULL,
            is_active               INTEGER NOT NULL DEFAULT 1,
            reset_token             TEXT,
            reset_token_expires_at  TEXT
        )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        ))
        # Additive migrations — swallow OperationalError when column exists.
        for col in (
            "reset_token TEXT",
            "reset_token_expires_at TEXT",
            "stripe_customer_id TEXT",
            "subscription_status TEXT NOT NULL DEFAULT 'trialing'",
            "trial_ends_at TEXT",
            "company_name TEXT",
        ):
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col}"))
            except Exception:
                pass
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS celery_task_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name   TEXT,
            status      TEXT,
            started_at  TEXT,
            finished_at TEXT,
            result_json TEXT
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_watchlist (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            internal_id TEXT NOT NULL,
            added_at    TEXT NOT NULL,
            UNIQUE(user_id, internal_id)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ingest_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date         TEXT NOT NULL,
            source           TEXT NOT NULL,
            record_count     INTEGER NOT NULL DEFAULT 0,
            duration_seconds REAL,
            status           TEXT NOT NULL,
            error_message    TEXT,
            created_at       TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_saved_searches (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            query_params_json TEXT NOT NULL,
            created_at       TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS contract_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            internal_id TEXT NOT NULL,
            body        TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_preferences (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            expiry_days     INTEGER NOT NULL DEFAULT 30,
            enabled         INTEGER NOT NULL DEFAULT 1,
            updated_at      TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            internal_id TEXT NOT NULL,
            alert_type  TEXT NOT NULL DEFAULT 'expiry',
            sent_at     TEXT NOT NULL,
            UNIQUE(user_id, internal_id, alert_type)
        )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alert_log_user ON alert_log(user_id)"
        ))
        # Migration history table — present on both SQLite and PostgreSQL so
        # schema state is always inspectable regardless of backend.
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            company_name TEXT,
            website     TEXT,
            geo_coverage TEXT NOT NULL DEFAULT 'nationwide',
            min_contract_value REAL,
            max_contract_value REAL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_naics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            naics_code  TEXT NOT NULL,
            UNIQUE(profile_id, naics_code)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_states (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            state_code  TEXT NOT NULL,
            UNIQUE(profile_id, state_code)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_preferred_agencies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            agency_name TEXT NOT NULL,
            UNIQUE(profile_id, agency_name)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_set_asides (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            set_aside_type TEXT NOT NULL,
            UNIQUE(profile_id, set_aside_type)
        )
        """))


def get_company_profile(user_id):
    """Return the full company profile for user_id, or None if none exists.

    Returned dict keys: id, user_id, company_name, website, geo_coverage,
    min_contract_value, max_contract_value, created_at, updated_at,
    naics_codes (list), states (list), agencies (list), set_asides (list).
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM company_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        ).mappings().fetchone()
        if row is None:
            return None
        profile = dict(row)
        pid = profile["id"]

        profile["naics_codes"] = [
            r[0] for r in conn.execute(
                text("SELECT naics_code FROM company_naics WHERE profile_id = :pid ORDER BY naics_code"),
                {"pid": pid},
            ).fetchall()
        ]
        profile["states"] = [
            r[0] for r in conn.execute(
                text("SELECT state_code FROM company_states WHERE profile_id = :pid ORDER BY state_code"),
                {"pid": pid},
            ).fetchall()
        ]
        profile["agencies"] = [
            r[0] for r in conn.execute(
                text("SELECT agency_name FROM company_preferred_agencies WHERE profile_id = :pid ORDER BY agency_name"),
                {"pid": pid},
            ).fetchall()
        ]
        profile["set_asides"] = [
            r[0] for r in conn.execute(
                text("SELECT set_aside_type FROM company_set_asides WHERE profile_id = :pid ORDER BY set_aside_type"),
                {"pid": pid},
            ).fetchall()
        ]
    return profile


def save_company_profile(user_id, data):
    """Create or replace the company profile for user_id.

    data keys: company_name, website, geo_coverage, min_contract_value,
    max_contract_value, naics_codes (list[str]), states (list[str]),
    agencies (list[str]), set_asides (list[str]).

    Multi-value lists are replaced wholesale on every save.
    Returns the profile id.
    """
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"

    naics_codes = [c.strip() for c in (data.get("naics_codes") or []) if c.strip()]
    states = [s.strip() for s in (data.get("states") or []) if s.strip()]
    agencies = [a.strip() for a in (data.get("agencies") or []) if a.strip()]
    set_asides = [s.strip() for s in (data.get("set_asides") or []) if s.strip()]

    min_val = data.get("min_contract_value")
    max_val = data.get("max_contract_value")
    try:
        min_val = float(min_val) if min_val not in (None, "") else None
    except (ValueError, TypeError):
        min_val = None
    try:
        max_val = float(max_val) if max_val not in (None, "") else None
    except (ValueError, TypeError):
        max_val = None

    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM company_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()

        if existing:
            profile_id = existing[0]
            conn.execute(text("""
                UPDATE company_profiles SET
                    company_name = :company_name,
                    website = :website,
                    geo_coverage = :geo_coverage,
                    min_contract_value = :min_val,
                    max_contract_value = :max_val,
                    updated_at = :now
                WHERE user_id = :uid
            """), {
                "company_name": data.get("company_name") or None,
                "website": data.get("website") or None,
                "geo_coverage": data.get("geo_coverage") or "nationwide",
                "min_val": min_val,
                "max_val": max_val,
                "now": now,
                "uid": user_id,
            })
        else:
            if is_pg:
                row = conn.execute(text("""
                    INSERT INTO company_profiles
                        (user_id, company_name, website, geo_coverage, min_contract_value, max_contract_value, created_at, updated_at)
                    VALUES (:uid, :company_name, :website, :geo_coverage, :min_val, :max_val, :now, :now)
                    RETURNING id
                """), {
                    "uid": user_id,
                    "company_name": data.get("company_name") or None,
                    "website": data.get("website") or None,
                    "geo_coverage": data.get("geo_coverage") or "nationwide",
                    "min_val": min_val,
                    "max_val": max_val,
                    "now": now,
                }).fetchone()
                profile_id = row[0]
            else:
                result = conn.execute(text("""
                    INSERT INTO company_profiles
                        (user_id, company_name, website, geo_coverage, min_contract_value, max_contract_value, created_at, updated_at)
                    VALUES (:uid, :company_name, :website, :geo_coverage, :min_val, :max_val, :now, :now)
                """), {
                    "uid": user_id,
                    "company_name": data.get("company_name") or None,
                    "website": data.get("website") or None,
                    "geo_coverage": data.get("geo_coverage") or "nationwide",
                    "min_val": min_val,
                    "max_val": max_val,
                    "now": now,
                })
                profile_id = result.lastrowid

        # Replace all multi-value lists wholesale
        for table in ("company_naics", "company_states", "company_preferred_agencies", "company_set_asides"):
            conn.execute(text(f"DELETE FROM {table} WHERE profile_id = :pid"), {"pid": profile_id})

        for code in naics_codes:
            conn.execute(
                text("INSERT OR IGNORE INTO company_naics (profile_id, naics_code) VALUES (:pid, :code)"),
                {"pid": profile_id, "code": code},
            )
        for state in states:
            conn.execute(
                text("INSERT OR IGNORE INTO company_states (profile_id, state_code) VALUES (:pid, :code)"),
                {"pid": profile_id, "code": state},
            )
        for agency in agencies:
            conn.execute(
                text("INSERT OR IGNORE INTO company_preferred_agencies (profile_id, agency_name) VALUES (:pid, :name)"),
                {"pid": profile_id, "name": agency},
            )
        for sa in set_asides:
            conn.execute(
                text("INSERT OR IGNORE INTO company_set_asides (profile_id, set_aside_type) VALUES (:pid, :sa)"),
                {"pid": profile_id, "sa": sa},
            )

    return profile_id


def upsert_contract(row):
    internal_id = row.get("internal_id") or row.get("generated_internal_id")
    if not internal_id:
        return

    now = datetime.now(timezone.utc).isoformat()

    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO contracts (
            internal_id, award_id, vendor, agency, sub_agency, description, value,
            start_date, end_date, days_remaining, competition_type,
            solicitation_id, recompete_score, priority, raw_json, updated_at
        )
        VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :description, :value,
                :start_date, :end_date, :days_remaining, :competition_type,
                :solicitation_id, :recompete_score, :priority, :raw_json, :updated_at)
        ON CONFLICT(internal_id) DO UPDATE SET
            award_id=excluded.award_id,
            vendor=excluded.vendor,
            agency=excluded.agency,
            sub_agency=excluded.sub_agency,
            description=excluded.description,
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
            "description": row.get("description"),
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
                internal_id, award_id, vendor, agency, sub_agency, description, value,
                start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json, updated_at
            )
            VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :description, :value,
                    :start_date, :end_date, :days_remaining, :competition_type,
                    :solicitation_id, :recompete_score, :priority, :raw_json, CURRENT_TIMESTAMP)
            ON CONFLICT(internal_id) DO UPDATE SET
                award_id=excluded.award_id,
                vendor=excluded.vendor,
                agency=excluded.agency,
                sub_agency=excluded.sub_agency,
                description=excluded.description,
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
                "description": row.get("description"),
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


def list_saved_searches(user_id):
    """Return a user's saved searches (newest first) with parsed params.

    Each item: {id, name, created_at, params}. The caller builds the reload URL.
    Used by both the /searches page and the contracts-page quick links.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, query_params_json, created_at"
                " FROM user_saved_searches WHERE user_id = :uid"
                " ORDER BY created_at DESC"
            ),
            {"uid": user_id},
        ).mappings().fetchall()
    out = []
    for r in rows:
        try:
            params = json.loads(r["query_params_json"] or "{}")
        except (ValueError, TypeError):
            params = {}
        out.append({"id": r["id"], "name": r["name"],
                    "created_at": r["created_at"], "params": params})
    return out


def search_tokens(q, limit=8):
    """Split a user search string into safe, lowercased word tokens.

    Strips punctuation/FTS operators (&, commas, quotes, parens, …) so real-world
    queries like "AT&T" or "Booz, Allen" don't break the full-text query. Returns up
    to ``limit`` tokens; an all-punctuation query yields an empty list.
    """
    return re.findall(r"[a-z0-9]+", (q or "").lower())[:limit]


def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score", direction="desc", page=1, limit=25, status=""):
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"

    params: dict = {}

    if q:
        tokens = search_tokens(q)
        if not tokens:
            # a query with no usable terms (only punctuation) matches nothing — never
            # error, and never fall through to "show everything"
            base = "FROM contracts c WHERE 1=0"
        elif is_pg:
            # prefix match each term so partial words work ("lockhe" → "Lockheed");
            # tokens are alphanumeric only, so the tsquery is always valid + injection-safe
            base = "FROM contracts c WHERE c.search_vector @@ to_tsquery('english', :q)"
            params["q"] = " & ".join(f"{t}:*" for t in tokens)
        else:
            base = """
                FROM contracts c
                JOIN contracts_fts f ON c.rowid = f.rowid
                WHERE contracts_fts MATCH :q
            """
            params["q"] = " ".join(f"{t}*" for t in tokens)
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

    # Open/active status: "open" = still running (days_remaining > 0), "expired" =
    # ended (days_remaining <= 0). Unknown (NULL) days_remaining only appears under
    # the default "all". Lets contractors hide dead opportunities and focus on live ones.
    if status == "open":
        base += " AND c.days_remaining > 0"
    elif status == "expired":
        base += " AND c.days_remaining <= 0"

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
