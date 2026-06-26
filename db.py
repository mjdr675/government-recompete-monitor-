import glob
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, text

DB_PATH = os.environ.get("DB_PATH", "contracts.db")

# Apply-window bounds — kept in sync with apply_window.py. A contract is
# "applyable" when an SMB has enough runway left to realistically bid:
# at least MIN_APPLY_DAYS and at most MAX_PREP_DAYS before the incumbent ends.
APPLY_MIN_DAYS = 60
APPLY_MAX_DAYS = 540


@lru_cache(maxsize=None)
def _cached_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


def get_engine():
    database_url = os.environ.get("DATABASE_URL", "")
    url = database_url if database_url else f"sqlite:///{DB_PATH}"
    return _cached_engine(url)


def get_connection():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        try:
            import psycopg2
            return psycopg2.connect(database_url)
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            ) from exc
    return sqlite3.connect(DB_PATH)


def connect():
    return get_connection()


_MIGRATION_PROBES: dict = {
    "001_initial_schema.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'contracts'"
    ),
    "001_initial_pg.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'contracts'"
    ),
    "002_contract_snapshots.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'contract_snapshots'"
    ),
    "002_subscription_and_alerts.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'user_subscriptions'"
    ),
    "003_changes.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'changes'"
    ),
    "004_saved_views.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'saved_views'"
    ),
    "005_users.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'users'"
    ),
    "006_user_companies.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'user_companies'"
    ),
    "006_company_profile.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'user_companies'"
    ),
    "007_opportunities.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'opportunities'"
    ),
    "008_notification_preferences.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'user_notification_preferences'"
    ),
    "009_contracts_ci_columns.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'place_of_performance_state'"
    ),
    "010_discovery_columns.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'place_of_performance_state'"
    ),
    "003_company_name.sql": ("SELECT 1"),
    "004_contracts_days_remaining_index.sql": ("SELECT 1"),
    "005_contracts_description_search.sql": ("SELECT 1"),
    "011_company_keywords.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'company_keywords'"
    ),
    "012_contract_field_changes.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'contract_field_changes'"
    ),
    "013_workspaces.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'workspaces'"
    ),
    "014_workspace_billing.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'workspaces' AND column_name = 'subscription_status'"
    ),
    "015_feedback_and_billing_interval.sql": (
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'feedback_submissions'"
    ),
    "015_location_columns.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'place_of_performance_city'"
    ),
    "016_contracts_sam_url.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'sam_url'"
    ),
    "016_add_psc_description_column.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'psc_description'"
    ),
    "016_backfill_psc_description.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'psc_description'"
    ),
    "017_contracts_uei_cage.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'recipient_uei'"
    ),
    "018_contract_field_changes_change_kind.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contract_field_changes' AND column_name = 'change_kind'"
    ),
    "018_contracts_psc_code_and_country.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'psc_code'"
    ),
    "019_contracts_naics_description.sql": (
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = 'contracts' AND column_name = 'naics_description'"
    ),
}


def _stamp_pre_existing(engine, applied: set) -> None:
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
            len(stamped), ", ".join(stamped),
        )


def _apply_migrations(migrations_dir=None) -> None:
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
    try:
        with engine.connect() as conn:
            applied = {
                row[0]
                for row in conn.execute(text("SELECT filename FROM schema_migrations"))
            }
    except Exception as exc:
        _log.warning("Skipping migrations — cannot read schema_migrations: %s", exc)
        return
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
    sql_files = sorted(Path(migrations_dir).glob("*.sql"))
    for sql_file in sql_files:
        if sql_file.name in applied:
            _log.debug("Migration already applied, skipping: %s", sql_file.name)
            continue
        _log.info("Applying migration: %s", sql_file.name)
        statements = []
        for seg in sql_file.read_text().split(";"):
            body = "\n".join(
                line for line in seg.splitlines()
                if line.strip() and not line.strip().startswith("--")
            ).strip()
            if body:
                statements.append(body)
        try:
            with engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations(filename, applied_at) "
                        "VALUES (:f, :a)"
                    ),
                    {"f": sql_file.name, "a": datetime.now(timezone.utc).isoformat()},
                )
            _log.info("Migration applied: %s", sql_file.name)
        except Exception as exc:
            _log.error(
                "Migration %s FAILED: %s — stopping.", sql_file.name, exc
            )
            raise


def _apply_pg_migrations() -> None:
    _apply_migrations()


_CATEGORY_RULES = [
    ("Cybersecurity", ["cyber", "information security", "security operations", "soc "]),
    ("IT", [
        "information technology", "help desk", "helpdesk", "software", "cloud ",
        "network ", "hardware", "data center", "systems integrat",
        "it support", "it service", "managed service",
    ]),
    ("Cleaning", ["janitorial", "cleaning", "custodial", "housekeeping", "sanitation"]),
    ("Grounds", ["grounds", "landscaping", "lawn", "mowing", "turf "]),
    ("Facilities", [
        "facility", "facilities", "hvac", "building maintenance",
        "operations and maintenance", "o&m", "maintenance and repair",
    ]),
    ("Construction", ["construction", "renovation", "roofing", "paving", "demolition", "structural"]),
    ("Logistics", ["logistics", "supply chain", "transportation", "shipping", "warehousing", "distribution"]),
    ("Security", ["security guard", "physical security", "guard service", "armed guard", "unarmed guard"]),
    ("Administrative", ["administrative support", "administrative services", "program support", "clerical"]),
]

_NAICS_CATEGORY_MAP = [
    ("5415", "IT"), ("5416", "IT"), ("5413", "IT"),
    ("7371", "IT"), ("7372", "IT"), ("7374", "IT"),
    ("2381", "Construction"), ("2382", "Construction"),
    ("2383", "Construction"), ("2389", "Construction"),
    ("56173", "Grounds"),
    ("5617", "Cleaning"),
    ("56161", "Security"), ("5616", "Security"),
    ("4841", "Logistics"), ("4842", "Logistics"), ("4931", "Logistics"),
]

# Aliases accepted from the UI or external URLs that map to canonical category names.
# Keys are lowercased so the lookup is case-insensitive.
_CATEGORY_ALIASES: dict[str, str] = {
    "cleaning / janitorial": "Cleaning",
    "cleaning/janitorial": "Cleaning",
    "janitorial": "Cleaning",
    "custodial": "Cleaning",
    "grounds / landscaping": "Grounds",
    "grounds/landscaping": "Grounds",
    "landscaping": "Grounds",
    "lawn": "Grounds",
    "physical security": "Security",
    "guard services": "Security",
    "information technology": "IT",
    "it services": "IT",
}

ALL_CATEGORIES = [
    "Administrative", "Cleaning", "Construction", "Cybersecurity",
    "Facilities", "Grounds", "IT", "Logistics", "Security",
]


def infer_category(description="", naics_code="", vendor="", agency="", psc_description=""):
    text_val = " ".join(filter(None, [description, vendor, psc_description])).lower()
    for cat, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in text_val:
                return cat
    if naics_code:
        nc = str(naics_code).strip()
        for prefix, cat in _NAICS_CATEGORY_MAP:
            if nc.startswith(prefix):
                return cat
    return "Other"


def extract_raw_field(row, field, default=None):
    raw = row.get("raw_json") if row else None
    if not raw:
        return default
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data.get(field) or default
    except Exception:
        return default


def _ensure_ci_columns():
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return
        existing = {r[1] for r in rows}
        for col, coltype in [
            ("place_of_performance_state", "TEXT"),
            ("vendor_website", "TEXT"),
        ]:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE contracts ADD COLUMN {col} {coltype}"))


def _ensure_description_column():
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return False
        cols = [r[1] for r in rows]
        if "description" in cols:
            return False
        conn.execute(text("ALTER TABLE contracts ADD COLUMN description TEXT"))
        conn.execute(text("DROP TABLE IF EXISTS contracts_fts"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_ai"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_ad"))
        conn.execute(text("DROP TRIGGER IF EXISTS contracts_au"))
    return True


def _extract_pop_state(row):
    for key in ("place_of_performance_state", "pop_state", "performance_state", "state"):
        val = row.get(key)
        if val and str(val).strip():
            return str(val).strip()[:2].upper()
    for key in ("place_of_performance_city", "pop_city", "city"):
        val = row.get(key)
        if val and "," in str(val):
            parts = str(val).rsplit(",", 1)
            st = parts[-1].strip()[:2].upper()
            if len(st) == 2 and st.isalpha():
                return st
    return None


def _ensure_discovery_columns():
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return False
        cols = [r[1] for r in rows]
        added = False
        for col_def in ("naics_code TEXT", "place_of_performance_state TEXT", "category TEXT",
                        "place_of_performance_city TEXT", "place_of_performance_zip TEXT"):
            col_name = col_def.split()[0]
            if col_name not in cols:
                conn.execute(text(f"ALTER TABLE contracts ADD COLUMN {col_def}"))
                added = True
        if added:
            conn.execute(text("DROP TABLE IF EXISTS contracts_fts"))
            conn.execute(text("DROP TRIGGER IF EXISTS contracts_ai"))
            conn.execute(text("DROP TRIGGER IF EXISTS contracts_ad"))
            conn.execute(text("DROP TRIGGER IF EXISTS contracts_au"))
    return added


def _ensure_psc_description_column():
    """Add contracts.psc_description to pre-existing SQLite databases."""
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return
        existing = {r[1] for r in rows}
        if "psc_description" not in existing:
            conn.execute(text("ALTER TABLE contracts ADD COLUMN psc_description TEXT"))


def _ensure_richer_location_columns():
    """Add psc_code and place_of_performance_country to pre-existing SQLite DBs.

    Safe to call on new DBs (no-op when columns already exist).
    """
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(contracts)")).fetchall()
        if not rows:
            return
        existing = {r[1] for r in rows}
        for col in ("psc_code TEXT", "place_of_performance_country TEXT", "naics_description TEXT"):
            col_name = col.split()[0]
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE contracts ADD COLUMN {col}"))


def init_db():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        _apply_migrations()
        return

    needs_fts_rebuild = _ensure_description_column()
    _ensure_ci_columns()
    needs_fts_rebuild = _ensure_discovery_columns() or needs_fts_rebuild
    _ensure_psc_description_column()
    _ensure_richer_location_columns()

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
            naics_code TEXT,
            naics_description TEXT,
            place_of_performance_state TEXT,
            place_of_performance_city TEXT,
            place_of_performance_zip TEXT,
            category TEXT,
            value REAL,
            start_date TEXT,
            end_date TEXT,
            days_remaining INTEGER,
            competition_type TEXT,
            solicitation_id TEXT,
            recompete_score INTEGER,
            priority TEXT,
            psc_description TEXT,
            psc_code TEXT,
            place_of_performance_country TEXT,
            raw_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            vendor_website TEXT,
            recipient_uei TEXT NOT NULL DEFAULT '',
            cage_code TEXT NOT NULL DEFAULT ''
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contracts_vendor ON contracts(vendor)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contracts_agency ON contracts(agency)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contracts_priority ON contracts(priority)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contracts_score ON contracts(recompete_score DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_contracts_days_remaining ON contracts(days_remaining)"))
        conn.execute(text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts USING fts5(
            internal_id UNINDEXED,
            vendor, agency, award_id, description, naics_code,
            place_of_performance_state, place_of_performance_city,
            content='contracts', content_rowid='rowid'
        )
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ai AFTER INSERT ON contracts BEGIN
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id, description, naics_code, place_of_performance_state, place_of_performance_city)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id, new.description, new.naics_code, new.place_of_performance_state, new.place_of_performance_city);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_ad AFTER DELETE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id, description, naics_code, place_of_performance_state, place_of_performance_city)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id, old.description, old.naics_code, old.place_of_performance_state, old.place_of_performance_city);
        END
        """))
        conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS contracts_au AFTER UPDATE ON contracts BEGIN
            INSERT INTO contracts_fts(contracts_fts, rowid, internal_id, vendor, agency, award_id, description, naics_code, place_of_performance_state, place_of_performance_city)
            VALUES ('delete', old.rowid, old.internal_id, old.vendor, old.agency, old.award_id, old.description, old.naics_code, old.place_of_performance_state, old.place_of_performance_city);
            INSERT INTO contracts_fts(rowid, internal_id, vendor, agency, award_id, description, naics_code, place_of_performance_state, place_of_performance_city)
            VALUES (new.rowid, new.internal_id, new.vendor, new.agency, new.award_id, new.description, new.naics_code, new.place_of_performance_state, new.place_of_performance_city);
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
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"))
        for col in (
            "reset_token TEXT",
            "reset_token_expires_at TEXT",
            "stripe_customer_id TEXT",
            "subscription_status TEXT NOT NULL DEFAULT 'trialing'",
            "trial_ends_at TEXT",
            "company_name TEXT",
            "billing_interval TEXT",
        ):
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col}"))
            except Exception:
                pass
        try:
            conn.execute(text("ALTER TABLE contracts ADD COLUMN sam_url TEXT"))
        except Exception:
            pass
        for _uei_col in (
            "recipient_uei TEXT NOT NULL DEFAULT ''",
            "cage_code TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(text(f"ALTER TABLE contracts ADD COLUMN {_uei_col}"))
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
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_log_user ON alert_log(user_id)"))
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
            vendor_name TEXT,
            uei         TEXT,
            cage_code   TEXT,
            website     TEXT,
            geo_coverage TEXT NOT NULL DEFAULT 'nationwide',
            min_contract_value REAL,
            max_contract_value REAL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """))
        for _col in (
            "ALTER TABLE company_profiles ADD COLUMN vendor_name TEXT",
            "ALTER TABLE company_profiles ADD COLUMN uei TEXT",
            "ALTER TABLE company_profiles ADD COLUMN cage_code TEXT",
        ):
            try:
                conn.execute(text(_col))
            except Exception:
                pass
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_naics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            naics_code  TEXT NOT NULL,
            UNIQUE(profile_id, naics_code)
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_company_naics_code ON company_naics(naics_code)"))
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
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_company_agencies_name ON company_preferred_agencies(agency_name)"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_set_asides (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            set_aside_type TEXT NOT NULL,
            UNIQUE(profile_id, set_aside_type)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_keywords (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
            keyword     TEXT NOT NULL,
            UNIQUE(profile_id, keyword)
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            logo_path   TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role         TEXT NOT NULL DEFAULT 'owner',
            created_at   TEXT NOT NULL,
            UNIQUE(workspace_id, user_id)
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id)"))
        for col in (
            "plan TEXT NOT NULL DEFAULT 'starter'",
            "subscription_status TEXT NOT NULL DEFAULT 'trialing'",
            "trial_start_at TEXT",
            "trial_end_at TEXT",
            "stripe_customer_id TEXT",
            "stripe_subscription_id TEXT",
        ):
            try:
                conn.execute(text(f"ALTER TABLE workspaces ADD COLUMN {col}"))
            except Exception:
                pass
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workspace_billing_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
            event_type      TEXT,
            stripe_event_id TEXT,
            payload_json    TEXT,
            created_at      TEXT NOT NULL
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_workspace_billing_events_ws ON workspace_billing_events(workspace_id)"))
        for col in (
            "billing_interval TEXT NOT NULL DEFAULT 'monthly'",
        ):
            try:
                conn.execute(text(f"ALTER TABLE workspaces ADD COLUMN {col}"))
            except Exception:
                pass
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS feedback_submissions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            email       TEXT,
            subject     TEXT NOT NULL,
            body        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'new',
            created_at  TEXT NOT NULL
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_submissions(status)"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            internal_id           TEXT NOT NULL,
            stage                 TEXT NOT NULL DEFAULT 'new',
            probability           INTEGER,
            next_action           TEXT,
            next_action_due       TEXT,
            notes                 TEXT,
            created_by_user_id    INTEGER NOT NULL REFERENCES users(id),
            last_updated_by_user_id INTEGER NOT NULL REFERENCES users(id),
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            UNIQUE(user_id, internal_id)
        )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_user ON opportunities(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_user_stage ON opportunities(user_id, stage)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_opportunities_user_due ON opportunities(user_id, next_action_due)"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_notification_preferences (
            id                              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id                         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            email_notifications_enabled     INTEGER NOT NULL DEFAULT 1,
            pipeline_digest_enabled         INTEGER NOT NULL DEFAULT 1,
            next_action_reminders_enabled   INTEGER NOT NULL DEFAULT 1,
            opportunity_alerts_enabled      INTEGER NOT NULL DEFAULT 1,
            digest_frequency                TEXT NOT NULL DEFAULT 'weekly',
            updated_at                      TEXT NOT NULL
        )
        """))


_NOTIFICATION_DEFAULTS: dict = {
    "email_notifications_enabled": 1,
    "pipeline_digest_enabled": 1,
    "next_action_reminders_enabled": 1,
    "opportunity_alerts_enabled": 1,
    "digest_frequency": "weekly",
}
_VALID_NOTIFICATION_FIELDS = frozenset(_NOTIFICATION_DEFAULTS.keys())
_VALID_DIGEST_FREQUENCIES = frozenset({"daily", "weekly", "monthly"})


def get_notification_preferences(user_id: int) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT email_notifications_enabled, pipeline_digest_enabled,"
                " next_action_reminders_enabled, opportunity_alerts_enabled,"
                " digest_frequency"
                " FROM user_notification_preferences WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).mappings().fetchone()
    return dict(row) if row else dict(_NOTIFICATION_DEFAULTS)


def update_notification_preferences(user_id: int, **fields) -> dict:
    valid = {k: v for k, v in fields.items() if k in _VALID_NOTIFICATION_FIELDS}
    if not valid:
        return get_notification_preferences(user_id)
    if "digest_frequency" in valid and valid["digest_frequency"] not in _VALID_DIGEST_FREQUENCIES:
        raise ValueError(f"Invalid digest_frequency: {valid['digest_frequency']!r}")
    for bf in (
        "email_notifications_enabled", "pipeline_digest_enabled",
        "next_action_reminders_enabled", "opportunity_alerts_enabled",
    ):
        if bf in valid:
            valid[bf] = 1 if valid[bf] else 0
    merged = {**get_notification_preferences(user_id), **valid}
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_notification_preferences
                (user_id, email_notifications_enabled, pipeline_digest_enabled,
                 next_action_reminders_enabled, opportunity_alerts_enabled,
                 digest_frequency, updated_at)
            VALUES
                (:uid, :email_notifications_enabled, :pipeline_digest_enabled,
                 :next_action_reminders_enabled, :opportunity_alerts_enabled,
                 :digest_frequency, :now)
            ON CONFLICT(user_id) DO UPDATE SET
                email_notifications_enabled   = excluded.email_notifications_enabled,
                pipeline_digest_enabled       = excluded.pipeline_digest_enabled,
                next_action_reminders_enabled = excluded.next_action_reminders_enabled,
                opportunity_alerts_enabled    = excluded.opportunity_alerts_enabled,
                digest_frequency              = excluded.digest_frequency,
                updated_at                    = excluded.updated_at
        """), {**merged, "uid": user_id, "now": now})
    return get_notification_preferences(user_id)


def get_company_profile(user_id):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, user_id, company_name, vendor_name, uei, cage_code, website, geo_coverage,"
                " min_contract_value, max_contract_value, created_at, updated_at"
                " FROM company_profiles WHERE user_id = :uid"
            ),
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
        profile["keywords"] = [
            r[0] for r in conn.execute(
                text("SELECT keyword FROM company_keywords WHERE profile_id = :pid ORDER BY keyword"),
                {"pid": pid},
            ).fetchall()
        ]
    return profile


def save_company_profile(user_id, data):
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    naics_codes = [c.strip() for c in (data.get("naics_codes") or []) if c.strip()]
    states = [s.strip() for s in (data.get("states") or []) if s.strip()]
    agencies = [a.strip() for a in (data.get("agencies") or []) if a.strip()]
    set_asides = [s.strip() for s in (data.get("set_asides") or []) if s.strip()]
    keywords_raw = data.get("keywords") or []
    if isinstance(keywords_raw, str):
        keywords_raw = [
            k for part in keywords_raw.replace(",", "\n").splitlines()
            for k in [part.strip()] if k
        ]
    keywords = [k.lower() for k in keywords_raw if k.strip()]
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
    params = {
        "uid": user_id,
        "company_name": data.get("company_name") or None,
        "vendor_name": data.get("vendor_name") or None,
        "uei": data.get("uei") or None,
        "cage_code": data.get("cage_code") or None,
        "website": data.get("website") or None,
        "geo_coverage": data.get("geo_coverage") or "nationwide",
        "min_val": min_val,
        "max_val": max_val,
        "now": now,
    }
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO company_profiles
                (user_id, company_name, vendor_name, uei, cage_code, website, geo_coverage,
                 min_contract_value, max_contract_value, created_at, updated_at)
            VALUES (:uid, :company_name, :vendor_name, :uei, :cage_code, :website, :geo_coverage,
                    :min_val, :max_val, :now, :now)
            ON CONFLICT(user_id) DO UPDATE SET
                company_name       = excluded.company_name,
                vendor_name        = excluded.vendor_name,
                uei                = excluded.uei,
                cage_code          = excluded.cage_code,
                website            = excluded.website,
                geo_coverage       = excluded.geo_coverage,
                min_contract_value = excluded.min_contract_value,
                max_contract_value = excluded.max_contract_value,
                updated_at         = excluded.updated_at
            RETURNING id
        """), params).fetchone()
        profile_id = row[0]
        for table in ("company_naics", "company_states",
                      "company_preferred_agencies", "company_set_asides",
                      "company_keywords"):
            conn.execute(text(f"DELETE FROM {table} WHERE profile_id = :pid"), {"pid": profile_id})
        for code in naics_codes:
            conn.execute(
                text("INSERT INTO company_naics (profile_id, naics_code) VALUES (:pid, :code) ON CONFLICT(profile_id, naics_code) DO NOTHING"),
                {"pid": profile_id, "code": code},
            )
        for state in states:
            conn.execute(
                text("INSERT INTO company_states (profile_id, state_code) VALUES (:pid, :code) ON CONFLICT(profile_id, state_code) DO NOTHING"),
                {"pid": profile_id, "code": state},
            )
        for agency in agencies:
            conn.execute(
                text("INSERT INTO company_preferred_agencies (profile_id, agency_name) VALUES (:pid, :name) ON CONFLICT(profile_id, agency_name) DO NOTHING"),
                {"pid": profile_id, "name": agency},
            )
        for sa in set_asides:
            conn.execute(
                text("INSERT INTO company_set_asides (profile_id, set_aside_type) VALUES (:pid, :sa) ON CONFLICT(profile_id, set_aside_type) DO NOTHING"),
                {"pid": profile_id, "sa": sa},
            )
        for kw in keywords:
            conn.execute(
                text("INSERT INTO company_keywords (profile_id, keyword) VALUES (:pid, :kw) ON CONFLICT(profile_id, keyword) DO NOTHING"),
                {"pid": profile_id, "kw": kw},
            )
    return profile_id


def get_workspace_for_user(user_id):
    if not user_id:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT w.id, w.name, w.logo_path, w.created_at, w.updated_at, m.role
            FROM workspaces w
            JOIN workspace_members m ON m.workspace_id = w.id
            WHERE m.user_id = :uid
            ORDER BY m.id ASC
            LIMIT 1
        """), {"uid": user_id}).mappings().fetchone()
    return dict(row) if row else None


def get_or_create_workspace_for_user(user_id):
    if not user_id:
        return None
    existing = get_workspace_for_user(user_id)
    if existing:
        return existing
    engine = get_engine()
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        name = conn.execute(text("SELECT company_name FROM users WHERE id = :uid"), {"uid": user_id}).scalar()
        result = conn.execute(text(
            "INSERT INTO workspaces (name, logo_path, created_at, updated_at) VALUES (:name, NULL, :now, :now)"
        ), {"name": name or None, "now": now})
        workspace_id = result.lastrowid if result.lastrowid else conn.execute(
            text("SELECT id FROM workspaces ORDER BY id DESC LIMIT 1")
        ).scalar()
        conn.execute(text(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) VALUES (:wid, :uid, 'owner', :now) ON CONFLICT(workspace_id, user_id) DO NOTHING"
        ), {"wid": workspace_id, "uid": user_id, "now": now})
    create_workspace_billing_record(workspace_id)
    return get_workspace_for_user(user_id)


def update_workspace(workspace_id, name=None, logo_path=None):
    if not workspace_id:
        return
    sets = ["updated_at = :now"]
    params = {"wid": workspace_id, "now": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name.strip() or None
    if logo_path is not None:
        sets.append("logo_path = :logo_path")
        params["logo_path"] = logo_path or None
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE workspaces SET {', '.join(sets)} WHERE id = :wid"), params)


def list_workspace_members(workspace_id):
    if not workspace_id:
        return []
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT m.user_id, m.role, m.created_at, u.email
            FROM workspace_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.workspace_id = :wid
            ORDER BY m.id ASC
        """), {"wid": workspace_id}).mappings().fetchall()
    return [dict(r) for r in rows]


TRIAL_DAYS = 7
# Active plans offered to new subscribers (basic/pro/enterprise).
# Legacy values starter/growth may still exist on older rows; treat them as
# valid when reading but don't surface them in the UI plan picker.
VALID_PLANS = ("basic", "pro", "enterprise")
_LEGACY_PLAN_ALIASES = {"starter": "basic", "growth": "pro"}


def create_workspace_billing_record(workspace_id, trial_days=TRIAL_DAYS):
    if not workspace_id:
        return
    engine = get_engine()
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=trial_days)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE workspaces
            SET trial_start_at = COALESCE(trial_start_at, :start),
                trial_end_at   = COALESCE(trial_end_at, :end),
                subscription_status = COALESCE(subscription_status, 'trialing'),
                plan = COALESCE(plan, 'starter'),
                updated_at = :now
            WHERE id = :wid
        """), {"start": now.isoformat(), "end": trial_end.isoformat(), "now": now.isoformat(), "wid": workspace_id})


def get_workspace_billing(workspace_id):
    if not workspace_id:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, plan, subscription_status, trial_start_at, trial_end_at,
                   stripe_customer_id, stripe_subscription_id
            FROM workspaces WHERE id = :wid
        """), {"wid": workspace_id}).mappings().fetchone()
    return dict(row) if row else None


def update_workspace_subscription_status(workspace_id, status, plan=None,
                                         stripe_customer_id=None, stripe_subscription_id=None):
    if not workspace_id:
        return
    sets = ["subscription_status = :status", "updated_at = :now"]
    params = {"status": status, "now": datetime.now(timezone.utc).isoformat(), "wid": workspace_id}
    if plan is not None:
        sets.append("plan = :plan")
        params["plan"] = plan
    if stripe_customer_id is not None:
        sets.append("stripe_customer_id = :cust")
        params["cust"] = stripe_customer_id
    if stripe_subscription_id is not None:
        sets.append("stripe_subscription_id = :sub")
        params["sub"] = stripe_subscription_id
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE workspaces SET {', '.join(sets)} WHERE id = :wid"), params)


def is_workspace_in_trial(workspace_id):
    billing = get_workspace_billing(workspace_id)
    if not billing or not billing.get("trial_end_at"):
        return False
    try:
        trial_end = datetime.fromisoformat(billing["trial_end_at"])
    except (ValueError, TypeError):
        return False
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) <= trial_end


def is_workspace_active(workspace_id):
    billing = get_workspace_billing(workspace_id)
    if not billing:
        return False
    if billing.get("subscription_status") == "active":
        return True
    return is_workspace_in_trial(workspace_id)


def get_workspace_by_stripe_customer(stripe_customer_id):
    if not stripe_customer_id:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, plan, subscription_status, trial_start_at, trial_end_at,
                   stripe_customer_id, stripe_subscription_id
            FROM workspaces WHERE stripe_customer_id = :cust
            ORDER BY id ASC LIMIT 1
        """), {"cust": stripe_customer_id}).mappings().fetchone()
    return dict(row) if row else None


def record_workspace_billing_event(workspace_id, event_type, stripe_event_id=None, payload_json=None):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO workspace_billing_events
                (workspace_id, event_type, stripe_event_id, payload_json, created_at)
            VALUES (:wid, :etype, :eid, :payload, :now)
        """), {
            "wid": workspace_id, "etype": event_type,
            "eid": stripe_event_id, "payload": payload_json,
            "now": datetime.now(timezone.utc).isoformat(),
        })


PIPELINE_STAGES = [
    ("new",         "New"),
    ("interested",  "Interested"),
    ("researching", "Researching"),
    ("capturing",   "Capturing"),
    ("proposal",    "Proposal"),
    ("submitted",   "Submitted"),
    ("awarded",     "Awarded"),
    ("lost",        "Lost"),
]
_VALID_PIPELINE_STAGES = frozenset(v for v, _ in PIPELINE_STAGES)
PIPELINE_TERMINAL_STAGES = frozenset({"awarded", "lost"})


def add_opportunity(user_id, internal_id, stage="new"):
    if stage not in _VALID_PIPELINE_STAGES:
        raise ValueError(f"Invalid pipeline stage: {stage!r}")
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        try:
            row = conn.execute(
                text(
                    "INSERT INTO opportunities"
                    " (user_id, internal_id, stage,"
                    "  created_by_user_id, last_updated_by_user_id,"
                    "  created_at, updated_at)"
                    " VALUES (:uid, :iid, :stage, :uid, :uid, :now, :now)"
                    " RETURNING id"
                ),
                {"uid": user_id, "iid": internal_id, "stage": stage, "now": now},
            ).fetchone()
            return row[0], True
        except Exception as exc:
            if "UNIQUE" in str(exc).upper() or "unique" in str(exc).lower():
                existing = conn.execute(
                    text("SELECT id FROM opportunities WHERE user_id = :uid AND internal_id = :iid"),
                    {"uid": user_id, "iid": internal_id},
                ).fetchone()
                if existing:
                    return existing[0], False
            raise


def remove_opportunity(user_id, internal_id):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM opportunities WHERE user_id = :uid AND internal_id = :iid"),
            {"uid": user_id, "iid": internal_id},
        )


def get_opportunity(user_id, opp_id):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, user_id, internal_id, stage, probability,"
                " next_action, next_action_due, notes,"
                " created_by_user_id, last_updated_by_user_id,"
                " created_at, updated_at"
                " FROM opportunities WHERE id = :oid AND user_id = :uid"
            ),
            {"oid": opp_id, "uid": user_id},
        ).mappings().fetchone()
    return dict(row) if row else None


def get_opportunity_by_contract(user_id, internal_id):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, user_id, internal_id, stage, probability,"
                " next_action, next_action_due, notes,"
                " created_by_user_id, last_updated_by_user_id,"
                " created_at, updated_at"
                " FROM opportunities WHERE user_id = :uid AND internal_id = :iid"
            ),
            {"uid": user_id, "iid": internal_id},
        ).mappings().fetchone()
    return dict(row) if row else None


def list_opportunities(user_id, stage=None):
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    nulls_last = "NULLS LAST" if is_pg else ""
    params: dict = {"uid": user_id}
    stage_clause = ""
    if stage is not None:
        if stage not in _VALID_PIPELINE_STAGES:
            raise ValueError(f"Invalid pipeline stage: {stage!r}")
        stage_clause = " AND o.stage = :stage"
        params["stage"] = stage
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT o.id, o.user_id, o.internal_id, o.stage, o.probability,"
                " o.next_action, o.next_action_due, o.notes,"
                " o.created_by_user_id, o.last_updated_by_user_id,"
                " o.created_at, o.updated_at,"
                " c.award_id, c.vendor, c.agency, c.value, c.end_date,"
                " c.days_remaining, c.priority, c.recompete_score,"
                " c.competition_type, c.raw_json"
                " FROM opportunities o"
                " LEFT JOIN contracts c ON c.internal_id = o.internal_id"
                f" WHERE o.user_id = :uid{stage_clause}"
                f" ORDER BY o.next_action_due ASC {nulls_last}, o.created_at ASC"
            ),
            params,
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def update_opportunity(user_id, opp_id, data, updated_by_user_id=None):
    if updated_by_user_id is None:
        updated_by_user_id = user_id
    stage = data.get("stage")
    if stage is not None and stage not in _VALID_PIPELINE_STAGES:
        raise ValueError(f"Invalid pipeline stage: {stage!r}")
    try:
        probability = int(data["probability"]) if data.get("probability") not in (None, "") else None
        if probability is not None and not (0 <= probability <= 100):
            probability = max(0, min(100, probability))
    except (ValueError, TypeError):
        probability = None
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM opportunities WHERE id = :oid AND user_id = :uid"),
            {"oid": opp_id, "uid": user_id},
        ).fetchone()
        if not existing:
            raise LookupError(f"Opportunity {opp_id} not found for user {user_id}")
        sets = ["last_updated_by_user_id = :luu", "updated_at = :now"]
        params: dict = {"oid": opp_id, "uid": user_id, "luu": updated_by_user_id, "now": now}
        if stage is not None:
            sets.append("stage = :stage")
            params["stage"] = stage
        if "probability" in data:
            sets.append("probability = :prob")
            params["prob"] = probability
        if "next_action" in data:
            sets.append("next_action = :next_action")
            params["next_action"] = data["next_action"] or None
        if "next_action_due" in data:
            sets.append("next_action_due = :next_action_due")
            params["next_action_due"] = data["next_action_due"] or None
        if "notes" in data:
            sets.append("notes = :notes")
            params["notes"] = data["notes"] or None
        conn.execute(
            text(f"UPDATE opportunities SET {', '.join(sets)} WHERE id = :oid AND user_id = :uid"),
            params,
        )
    return get_opportunity(user_id, opp_id)


def upsert_contract(row):
    internal_id = row.get("internal_id") or row.get("generated_internal_id")
    if not internal_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    naics_code = row.get("naics_code") or row.get("naics") or ""
    psc_description = row.get("psc_description") or ""
    pop_state = _extract_pop_state(row)
    pop_city = (
        row.get("place_of_performance_city") or row.get("performance_city") or
        row.get("pop_city") or row.get("city") or ""
    )
    pop_zip = (
        row.get("place_of_performance_zip") or row.get("performance_zip") or
        row.get("pop_zip") or ""
    )
    category = infer_category(
        description=row.get("description") or "",
        naics_code=naics_code,
        vendor=row.get("vendor") or "",
        agency=row.get("agency") or "",
        psc_description=psc_description,
    )
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO contracts (
            internal_id, award_id, vendor, agency, sub_agency, description,
            naics_code, naics_description, place_of_performance_state, place_of_performance_city,
            place_of_performance_zip, place_of_performance_country,
            category, psc_description, psc_code,
            value, start_date, end_date, days_remaining, competition_type,
            solicitation_id, recompete_score, priority, raw_json, updated_at, sam_url,
            recipient_uei, cage_code
        )
        VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :description,
                :naics_code, :naics_description, :place_of_performance_state, :place_of_performance_city,
                :place_of_performance_zip, :place_of_performance_country,
                :category, :psc_description, :psc_code,
                :value, :start_date, :end_date, :days_remaining, :competition_type,
                :solicitation_id, :recompete_score, :priority, :raw_json, :updated_at, :sam_url,
                :recipient_uei, :cage_code)
        ON CONFLICT(internal_id) DO UPDATE SET
            award_id=excluded.award_id,
            vendor=excluded.vendor,
            agency=excluded.agency,
            sub_agency=excluded.sub_agency,
            description=excluded.description,
            naics_code=excluded.naics_code,
            naics_description=excluded.naics_description,
            place_of_performance_state=excluded.place_of_performance_state,
            place_of_performance_city=excluded.place_of_performance_city,
            place_of_performance_zip=excluded.place_of_performance_zip,
            place_of_performance_country=excluded.place_of_performance_country,
            category=excluded.category,
            psc_description=excluded.psc_description,
            psc_code=excluded.psc_code,
            value=excluded.value,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            days_remaining=excluded.days_remaining,
            competition_type=excluded.competition_type,
            solicitation_id=excluded.solicitation_id,
            recompete_score=excluded.recompete_score,
            priority=excluded.priority,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at,
            sam_url=excluded.sam_url,
            recipient_uei=excluded.recipient_uei,
            cage_code=excluded.cage_code
        """), {
            "internal_id": internal_id,
            "award_id": row.get("award_id"),
            "vendor": row.get("vendor"),
            "agency": row.get("agency"),
            "sub_agency": row.get("sub_agency"),
            "description": row.get("description"),
            "naics_code": naics_code,
            "naics_description": row.get("naics_description") or None,
            "place_of_performance_state": pop_state,
            "place_of_performance_city": pop_city or None,
            "place_of_performance_zip": pop_zip or None,
            "place_of_performance_country": row.get("performance_country") or row.get("place_of_performance_country") or None,
            "category": category,
            "psc_description": psc_description or None,
            "psc_code": row.get("psc_code") or None,
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
            "sam_url": row.get("sam_url") or "",
            "recipient_uei": row.get("recipient_uei") or "",
            "cage_code": row.get("cage_code") or "",
        })


def _has_unique_index(conn, table, cols):
    """True if `table` has a UNIQUE index whose columns are exactly `cols`.

    SQLite-only (uses PRAGMA). A fresh table's table-level UNIQUE(...) shows up
    here as its sqlite_autoindex, so a repair gated on this is skipped for fresh
    tables and only runs on drifted legacy tables that lack the constraint
    (where ON CONFLICT(...) would otherwise fail with "does not match any
    PRIMARY KEY or UNIQUE constraint").

    `table` is a trusted module constant, never user input (PRAGMA cannot bind).
    """
    target = set(cols)
    for idx in conn.execute(text(f"PRAGMA index_list({table})")).fetchall():
        name, is_unique = idx[1], idx[2]
        if not is_unique:
            continue
        idx_cols = {r[2] for r in conn.execute(text(f"PRAGMA index_info({name})")).fetchall()}
        if idx_cols == target:
            return True
    return False


def init_snapshots_table():
    engine = get_engine()
    with engine.begin() as conn:
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
        # Legacy SQLite tables created before the UNIQUE(run_date, internal_id)
        # constraint existed lack it, so save_snapshot's
        # ON CONFLICT(run_date, internal_id) fails. Dedupe (keep lowest id per
        # key) then add a unique index. Only runs when the constraint is absent.
        if engine.dialect.name != "postgresql" and not _has_unique_index(
            conn, "contract_snapshots", ("run_date", "internal_id")
        ):
            conn.execute(text("""
                DELETE FROM contract_snapshots
                WHERE id NOT IN (
                    SELECT MIN(id) FROM contract_snapshots
                    GROUP BY run_date, internal_id
                )
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_contract_snapshots_run_internal
                ON contract_snapshots(run_date, internal_id)
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
            naics_code = row.get("naics_code") or row.get("naics") or ""
            psc_description = row.get("psc_description") or ""
            pop_state = _extract_pop_state(row)
            pop_city = (
                row.get("place_of_performance_city") or row.get("performance_city") or
                row.get("pop_city") or row.get("city") or ""
            )
            pop_zip = (
                row.get("place_of_performance_zip") or row.get("performance_zip") or
                row.get("pop_zip") or ""
            )
            category = infer_category(
                description=row.get("description") or "",
                naics_code=naics_code,
                vendor=row.get("vendor") or "",
                agency=row.get("agency") or "",
                psc_description=psc_description,
            )
            conn.execute(text("""
            INSERT INTO contracts (
                internal_id, award_id, vendor, agency, sub_agency, description,
                naics_code, naics_description, place_of_performance_state, place_of_performance_city,
                place_of_performance_zip, place_of_performance_country,
                category, psc_description, psc_code,
                value, start_date, end_date, days_remaining, competition_type,
                solicitation_id, recompete_score, priority, raw_json, updated_at, sam_url,
                recipient_uei, cage_code
            )
            VALUES (:internal_id, :award_id, :vendor, :agency, :sub_agency, :description,
                    :naics_code, :naics_description, :place_of_performance_state, :place_of_performance_city,
                    :place_of_performance_zip, :place_of_performance_country,
                    :category, :psc_description, :psc_code,
                    :value, :start_date, :end_date, :days_remaining, :competition_type,
                    :solicitation_id, :recompete_score, :priority, :raw_json, CURRENT_TIMESTAMP,
                    :sam_url, :recipient_uei, :cage_code)
            ON CONFLICT(internal_id) DO UPDATE SET
                award_id=excluded.award_id,
                vendor=excluded.vendor,
                agency=excluded.agency,
                sub_agency=excluded.sub_agency,
                description=excluded.description,
                naics_code=excluded.naics_code,
                naics_description=excluded.naics_description,
                place_of_performance_state=excluded.place_of_performance_state,
                place_of_performance_city=excluded.place_of_performance_city,
                place_of_performance_zip=excluded.place_of_performance_zip,
                place_of_performance_country=excluded.place_of_performance_country,
                category=excluded.category,
                psc_description=excluded.psc_description,
                psc_code=excluded.psc_code,
                value=excluded.value,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                days_remaining=excluded.days_remaining,
                competition_type=excluded.competition_type,
                solicitation_id=excluded.solicitation_id,
                recompete_score=excluded.recompete_score,
                priority=excluded.priority,
                raw_json=excluded.raw_json,
                updated_at=CURRENT_TIMESTAMP,
                sam_url=excluded.sam_url,
                recipient_uei=excluded.recipient_uei,
                cage_code=excluded.cage_code
            """), {
                "internal_id": internal_id,
                "award_id": row.get("award_id") or row.get("contract"),
                "vendor": row.get("vendor"),
                "agency": row.get("agency"),
                "sub_agency": row.get("sub_agency"),
                "description": row.get("description"),
                "naics_code": naics_code,
                "naics_description": row.get("naics_description") or None,
                "place_of_performance_state": pop_state,
                "place_of_performance_city": pop_city or None,
                "place_of_performance_zip": pop_zip or None,
                "place_of_performance_country": row.get("performance_country") or row.get("place_of_performance_country") or None,
                "category": category,
                "psc_description": psc_description or None,
                "psc_code": row.get("psc_code") or None,
                "value": float(row.get("value") or 0),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "days_remaining": int(row.get("days_remaining") or 0),
                "competition_type": row.get("competition_type"),
                "solicitation_id": row.get("solicitation_id"),
                "recompete_score": int(row.get("recompete_score") or row.get("score") or 0),
                "priority": row.get("priority"),
                "raw_json": json.dumps(row, default=str),
                "sam_url": row.get("sam_url") or "",
                "recipient_uei": row.get("recipient_uei") or "",
                "cage_code": row.get("cage_code") or "",
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
        conn.execute(text("DELETE FROM changes WHERE run_date = :run_date"), {"run_date": run_date})


def insert_change(run_date, change_type, internal_id, old_priority=None, new_priority=None, description=""):
    init_changes_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO changes (run_date, change_type, internal_id, old_priority, new_priority, description)
        VALUES (:run_date, :change_type, :internal_id, :old_priority, :new_priority, :description)
        """), {
            "run_date": run_date, "change_type": change_type, "internal_id": internal_id,
            "old_priority": old_priority, "new_priority": new_priority, "description": description,
        })


def change_summary(run_date):
    init_changes_table()
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT change_type, COUNT(*) FROM changes WHERE run_date = :run_date GROUP BY change_type
        """), {"run_date": run_date}).fetchall()
    return {row[0]: row[1] for row in rows}


def get_changes(run_date, change_type):
    init_changes_table()
    with get_engine().connect() as conn:
        return conn.execute(text("""
            SELECT ch.change_type, ch.internal_id, ch.old_priority, ch.new_priority, ch.description,
                   c.vendor, c.agency, c.value, c.days_remaining, c.recompete_score, c.priority
            FROM changes ch
            LEFT JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = :run_date AND ch.change_type = :change_type
            ORDER BY c.recompete_score DESC, c.value DESC
        """), {"run_date": run_date, "change_type": change_type}).mappings().fetchall()


_FIELD_CHANGES_CANON_COLS = (
    "id", "run_date", "internal_id", "field_name",
    "old_value", "new_value", "change_kind", "created_at",
)


def _field_changes_create_sql(if_not_exists=True):
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return f"""
    CREATE TABLE {guard}contract_field_changes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date    TEXT NOT NULL,
        internal_id TEXT NOT NULL,
        field_name  TEXT NOT NULL,
        old_value   TEXT,
        new_value   TEXT,
        change_kind TEXT NOT NULL,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(run_date, internal_id, field_name)
    )
    """


def _heal_field_changes_schema(conn):
    """Bring a legacy SQLite contract_field_changes table to the canonical
    schema, fixing every accumulated drift at once instead of one error at a
    time:
      - missing columns added later (e.g. change_kind);
      - a missing UNIQUE(run_date, internal_id, field_name) backing the
        ON CONFLICT target;
      - obsolete NOT NULL columns from older schemas (e.g. a `contract_id`
        predecessor of internal_id) that break inserts with
        "NOT NULL constraint failed".

    Rebuilds via a temp table, carrying the canonical columns forward with safe
    defaults and deduping on the unique key (INSERT OR IGNORE). Idempotent: a
    table already in canonical shape is left untouched. SQLite-only (the
    Postgres path gets the canonical schema from migration 012).
    """
    info = conn.execute(text("PRAGMA table_info(contract_field_changes)")).fetchall()
    names = [r[1] for r in info]
    is_canonical = (
        set(names) == set(_FIELD_CHANGES_CANON_COLS)
        and _has_unique_index(
            conn, "contract_field_changes", ("run_date", "internal_id", "field_name")
        )
    )
    if is_canonical:
        return

    def src(col, fallback):
        return col if col in names else fallback

    select_exprs = ", ".join([
        src("run_date", "''"),
        src("internal_id", "''"),
        src("field_name", "''"),
        src("old_value", "NULL"),
        src("new_value", "NULL"),
        "COALESCE(change_kind, 'MODIFIED')" if "change_kind" in names else "'MODIFIED'",
        src("created_at", "CURRENT_TIMESTAMP"),
    ])
    target_cols = "run_date, internal_id, field_name, old_value, new_value, change_kind, created_at"

    conn.execute(text("DROP TABLE IF EXISTS _contract_field_changes_legacy"))
    conn.execute(text("ALTER TABLE contract_field_changes RENAME TO _contract_field_changes_legacy"))
    conn.execute(text(_field_changes_create_sql(if_not_exists=False)))
    conn.execute(text(
        f"INSERT OR IGNORE INTO contract_field_changes ({target_cols}) "
        f"SELECT {select_exprs} FROM _contract_field_changes_legacy"
    ))
    conn.execute(text("DROP TABLE _contract_field_changes_legacy"))


def init_field_changes_table():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(_field_changes_create_sql(if_not_exists=True)))
        # Repair legacy SQLite tables that drifted from the canonical schema —
        # missing columns, a missing UNIQUE constraint, or obsolete NOT NULL
        # columns (e.g. a legacy contract_id). Postgres fresh DBs carry the
        # canonical schema via migration 012, so this is SQLite-only.
        if engine.dialect.name != "postgresql":
            _heal_field_changes_schema(conn)
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_field_changes_run_date ON contract_field_changes(run_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_field_changes_internal_id ON contract_field_changes(internal_id)"))


def clear_field_changes_for_date(run_date):
    init_field_changes_table()
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM contract_field_changes WHERE run_date = :run_date"), {"run_date": run_date})


def insert_field_changes(run_date, records):
    records = list(records)
    if not records:
        return 0
    init_field_changes_table()
    engine = get_engine()
    conflict = "ON CONFLICT(run_date, internal_id, field_name) DO NOTHING"
    with engine.begin() as conn:
        for rec in records:
            conn.execute(text(f"""
                INSERT INTO contract_field_changes
                    (run_date, internal_id, field_name, old_value, new_value, change_kind)
                VALUES (:run_date, :internal_id, :field_name, :old_value, :new_value, :change_kind)
                {conflict}
            """), {
                "run_date": run_date,
                "internal_id": rec["internal_id"],
                "field_name": rec["field_name"],
                "old_value": rec.get("old_value"),
                "new_value": rec.get("new_value"),
                "change_kind": rec["change_kind"],
            })
    return len(records)


def get_field_changes_for_contracts(internal_ids, limit=50):
    internal_ids = list(internal_ids or [])
    if not internal_ids:
        return []
    init_field_changes_table()
    engine = get_engine()
    with engine.connect() as conn:
        placeholders = ", ".join(f":iid_{i}" for i in range(len(internal_ids)))
        params = {f"iid_{i}": iid for i, iid in enumerate(internal_ids)}
        params["limit"] = limit
        rows = conn.execute(text(f"""
            SELECT fc.run_date, fc.internal_id, fc.field_name, fc.old_value, fc.new_value,
                   fc.change_kind, fc.created_at, c.award_id, c.vendor
            FROM contract_field_changes fc
            LEFT JOIN contracts c ON c.internal_id = fc.internal_id
            WHERE fc.internal_id IN ({placeholders})
            ORDER BY fc.run_date DESC, fc.created_at DESC, fc.internal_id
            LIMIT :limit
        """), params).mappings().fetchall()
    return [dict(r) for r in rows]


def get_field_changes(run_date):
    init_field_changes_table()
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT run_date, internal_id, field_name, old_value, new_value, change_kind, created_at
            FROM contract_field_changes WHERE run_date = :run_date ORDER BY internal_id, field_name
        """), {"run_date": run_date}).mappings().fetchall()
    return [dict(r) for r in rows]


init_contract_field_changes_table = init_field_changes_table


def get_recent_updates_for_user(user_id, limit=10):
    if not user_id:
        return []
    engine = get_engine()
    with engine.connect() as conn:
        wl = conn.execute(text("SELECT internal_id FROM user_watchlist WHERE user_id = :uid"), {"uid": user_id}).fetchall()
        pl = conn.execute(text("SELECT internal_id FROM opportunities WHERE user_id = :uid"), {"uid": user_id}).fetchall()
    tracked = {r[0] for r in wl} | {r[0] for r in pl}
    return get_field_changes_for_contracts(tracked, limit=limit)


def init_demo_table():
    with get_engine().begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS demo_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL, name TEXT, company TEXT, phone TEXT, notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            hubspot_contact_id TEXT, hubspot_deal_id TEXT
        )
        """))


def save_demo_request(email, name="", company="", phone="", notes="",
                      hubspot_contact_id=None, hubspot_deal_id=None):
    init_demo_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO demo_requests (email, name, company, phone, notes, hubspot_contact_id, hubspot_deal_id)
        VALUES (:email, :name, :company, :phone, :notes, :hubspot_contact_id, :hubspot_deal_id)
        """), {
            "email": email, "name": name, "company": company, "phone": phone,
            "notes": notes, "hubspot_contact_id": hubspot_contact_id, "hubspot_deal_id": hubspot_deal_id,
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


def save_early_access(email, hubspot_contact_id=None):
    init_early_access_table()
    with get_engine().begin() as conn:
        conn.execute(text("""
        INSERT INTO early_access (email, hubspot_contact_id)
        VALUES (:email, :hubspot_contact_id)
        ON CONFLICT(email) DO UPDATE SET hubspot_contact_id = excluded.hubspot_contact_id
        """), {"email": email, "hubspot_contact_id": hubspot_contact_id})


def init_watchlist_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            internal_id TEXT PRIMARY KEY,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.commit()


def watch_contract(internal_id):
    init_watchlist_table()
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO watchlist (internal_id) VALUES (?)", (internal_id,))
        con.commit()


def unwatch_contract(internal_id):
    init_watchlist_table()
    with connect() as con:
        con.execute("DELETE FROM watchlist WHERE internal_id = ?", (internal_id,))
        con.commit()


def is_watched(internal_id):
    init_watchlist_table()
    with connect() as con:
        row = con.execute("SELECT 1 FROM watchlist WHERE internal_id = ?", (internal_id,)).fetchone()
    return row is not None


def get_watchlist():
    init_watchlist_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT c.* FROM watchlist w
        JOIN contracts c ON c.internal_id = w.internal_id
        ORDER BY c.recompete_score DESC, c.value DESC
    """).fetchall()
    conn.close()
    return rows


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


def create_saved_search(name, filters):
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute("INSERT INTO saved_searches (name, filters) VALUES (?, ?)", (name, _json.dumps(filters)))
        con.commit()
        return cur.lastrowid


def get_saved_searches():
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        rows = con.execute("SELECT id, name, filters, created_at FROM saved_searches ORDER BY id DESC").fetchall()
    return [{"id": r[0], "name": r[1], "filters": _json.loads(r[2]), "created_at": r[3]} for r in rows]


def get_saved_search(search_id):
    import json as _json
    init_saved_searches_table()
    with connect() as con:
        row = con.execute("SELECT id, name, filters, created_at FROM saved_searches WHERE id = ?", (search_id,)).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "filters": _json.loads(row[2]), "created_at": row[3]}


def rename_saved_search(search_id, name):
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute("UPDATE saved_searches SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, search_id))
        con.commit()
        return cur.rowcount > 0


def delete_saved_search(search_id):
    init_saved_searches_table()
    with connect() as con:
        cur = con.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
        con.commit()
        return cur.rowcount > 0


_SORTABLE = {"recompete_score", "value", "days_remaining", "end_date", "priority", "vendor", "agency"}


def list_contract_states(engine=None):
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT place_of_performance_state FROM contracts"
            " WHERE place_of_performance_state IS NOT NULL AND place_of_performance_state != ''"
            " ORDER BY place_of_performance_state"
        )).fetchall()
    return [r[0] for r in rows]


def find_contract_by_award_id(award_id: str) -> dict | None:
    """Look up a contract by its user-facing award_id / PIID.

    Returns the minimal fields needed to add it to a watchlist, or None if not found.
    Case-insensitive and strips whitespace so users don't have to be precise.
    """
    if not award_id:
        return None
    normalized = award_id.strip().upper()
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT internal_id, award_id, vendor, agency, value, end_date, days_remaining"
                " FROM contracts WHERE UPPER(award_id) = :aid LIMIT 1"
            ),
            {"aid": normalized},
        ).mappings().fetchone()
    return dict(row) if row else None


def submit_feedback(subject: str, body: str, user_id: int | None = None, email: str | None = None) -> int:
    """Store a feedback/contact submission. Returns the new row id."""
    now = datetime.now(timezone.utc).isoformat()
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO feedback_submissions (user_id, email, subject, body, status, created_at)"
                " VALUES (:uid, :email, :subject, :body, 'new', :now)"
            ),
            {"uid": user_id, "email": email, "subject": subject, "body": body, "now": now},
        )
        return result.lastrowid


def get_feedback_submissions(status: str | None = None, limit: int = 100) -> list[dict]:
    """Return feedback submissions for admin review, newest first."""
    engine = get_engine()
    where = "WHERE status = :status" if status else ""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT id, user_id, email, subject, body, status, created_at"
                f" FROM feedback_submissions {where}"
                f" ORDER BY created_at DESC LIMIT :lim"
            ),
            {"status": status, "lim": limit} if status else {"lim": limit},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def list_saved_searches(user_id):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, query_params_json, created_at"
                " FROM user_saved_searches WHERE user_id = :uid ORDER BY created_at DESC"
            ),
            {"uid": user_id},
        ).mappings().fetchall()
    out = []
    for r in rows:
        try:
            params = json.loads(r["query_params_json"] or "{}")
        except (ValueError, TypeError):
            params = {}
        out.append({"id": r["id"], "name": r["name"], "created_at": r["created_at"], "params": params})
    return out


def search_tokens(q, limit=8):
    return re.findall(r"[a-z0-9]+", (q or "").lower())[:limit]


_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

_NL_STOPWORDS = frozenset([
    "contracts", "contract", "services", "service", "work", "jobs", "job",
    "care", "management", "support", "operations",
    "in", "the", "and", "for", "of", "at", "by", "on", "to", "with",
    "federal", "government", "gov", "us", "united", "states",
])


def parse_nl_query(q: str) -> dict:
    """Extract structured filters from a natural-language search query.

    Returns a dict with zero or more of: 'category', 'state', 'q_remainder'.
    q_remainder is the query with recognized category/state phrases and common
    stopwords removed — use it as the new FTS query when filters were extracted.
    If nothing is extracted, q_remainder equals the original query.

    Examples:
        "lawn care contracts in Virginia" → {category: "Grounds", state: "VA", q_remainder: ""}
        "janitorial services Texas"       → {category: "Cleaning", state: "TX", q_remainder: ""}
        "cybersecurity DOD"               → {category: "Cybersecurity", q_remainder: "dod"}
    """
    if not q or not q.strip():
        return {"q_remainder": ""}

    q_lower = q.lower().strip()
    result: dict = {}
    remaining = q_lower

    # State detection — multi-word names checked first (greedy match)
    for name, code in sorted(_STATE_NAME_TO_CODE.items(), key=lambda x: -len(x[0])):
        in_pattern = r"\bin\s+" + re.escape(name) + r"\b"
        bare_pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(in_pattern, remaining):
            result["state"] = code
            remaining = re.sub(in_pattern, " ", remaining)
            break
        if re.search(bare_pattern, remaining):
            result["state"] = code
            remaining = re.sub(bare_pattern, " ", remaining)
            break

    # Category detection — first match from _CATEGORY_RULES wins
    for cat, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in remaining:
                result["category"] = cat
                remaining = remaining.replace(kw, " ")
                break
        if "category" in result:
            break

    tokens = [t for t in re.findall(r"[a-z0-9]+", remaining) if t not in _NL_STOPWORDS]
    result["q_remainder"] = " ".join(tokens)
    return result


def get_contracts(q="", agency="", priority="", days=None, min_value=None, sort="recompete_score",
                  direction="desc", page=1, limit=25, status="", profile_filter=None,
                  internal_ids=None, state="", category="", exclude_ids=None, all_rows=False,
                  applyable=False, min_days_left=None):
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    params: dict = {}

    if q:
        tokens = search_tokens(q)
        if not tokens:
            base = "FROM contracts c WHERE 1=0"
        elif is_pg:
            # websearch_to_tsquery handles stop words (LLC, Inc, Corp) and punctuation
            # gracefully — to_tsquery crashes when those terms exist in the server's
            # text search stop-word list.
            base = "FROM contracts c WHERE c.search_vector @@ websearch_to_tsquery('english', :q)"
            params["q"] = " ".join(tokens)
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

    # Apply-window filter — show contracts within the actionable window.
    # The upper bound hides contracts too far out (>18 months, not yet actionable).
    # The lower bound is NOT applied so that critically-expiring contracts
    # (days_remaining < MIN_APPLY_DAYS) remain visible — users need to see them.
    if applyable:
        base += " AND c.days_remaining <= :apply_max"
        params["apply_max"] = APPLY_MAX_DAYS

    if min_days_left is not None:
        base += " AND c.days_remaining >= :min_days_left"
        params["min_days_left"] = int(min_days_left)

    if min_value is not None:
        base += " AND c.value >= :min_value"
        params["min_value"] = float(min_value)

    if status == "open":
        base += " AND c.days_remaining > 0"
    elif status == "expired":
        base += " AND c.days_remaining <= 0"

    if profile_filter:
        pf_agencies = profile_filter.get("agencies") or []
        if pf_agencies:
            clauses = []
            for i, ag in enumerate(pf_agencies):
                key = f"pf_agency_{i}"
                clauses.append(f"c.agency LIKE :{key}")
                params[key] = f"%{ag}%"
            base += " AND (" + " OR ".join(clauses) + ")"
        pf_min = profile_filter.get("min_value")
        if pf_min is not None and min_value is None:
            base += " AND c.value >= :pf_min_value"
            params["pf_min_value"] = float(pf_min)
        pf_max = profile_filter.get("max_value")
        if pf_max is not None:
            base += " AND c.value <= :pf_max_value"
            params["pf_max_value"] = float(pf_max)
        pf_sa_keywords = profile_filter.get("set_aside_keywords") or []
        if pf_sa_keywords:
            clauses = []
            for i, kw in enumerate(pf_sa_keywords):
                key = f"pf_sa_{i}"
                clauses.append(f"c.competition_type LIKE :{key}")
                params[key] = f"%{kw}%"
            base += " AND (" + " OR ".join(clauses) + ")"

    if internal_ids is not None:
        if not internal_ids:
            base += " AND 1=0"
        else:
            placeholders = ", ".join(f":iid_{i}" for i in range(len(internal_ids)))
            base += f" AND c.internal_id IN ({placeholders})"
            for i, iid in enumerate(internal_ids):
                params[f"iid_{i}"] = iid

    if state:
        base += " AND c.place_of_performance_state = :state"
        params["state"] = state.upper()

    if category:
        # Normalize aliases (e.g. "Cleaning / Janitorial" → "Cleaning")
        canonical = _CATEGORY_ALIASES.get(category.lower(), category)
        _cat_map = {cat: kws for cat, kws in _CATEGORY_RULES}
        keywords = _cat_map.get(canonical, [canonical])
        # PostgreSQL LIKE is case-sensitive; USASpending descriptions are often
        # ALL-CAPS ("JANITORIAL SERVICES") so plain LIKE '%janitorial%' returns 0.
        # Use ILIKE on Postgres, LIKE on SQLite (already case-insensitive for ASCII).
        like_op = "ILIKE" if is_pg else "LIKE"
        # Category column: use ILIKE (pg) / LIKE (sqlite) for case-insensitive match
        # in case category was stored in a different case by a prior code path.
        cat_clauses = [f"c.category {like_op} :cat_exact"]
        params["cat_exact"] = canonical
        for i, kw in enumerate(keywords):
            key = f"cat_kw_{i}"
            params[key] = f"%{kw}%"
            # description column (populated for all rows)
            cat_clauses.append(f"c.description {like_op} :{key}")
            # psc_description column — backfilled from raw_json by migration 016
            # for legacy rows; populated directly at ingest for new rows.
            cat_clauses.append(f"c.psc_description {like_op} :{key}")
        naics_prefixes = [prefix for prefix, cat in _NAICS_CATEGORY_MAP if cat == canonical]
        for i, prefix in enumerate(naics_prefixes):
            key = f"cat_naics_{i}"
            params[key] = f"{prefix}%"
            cat_clauses.append(f"c.naics_code LIKE :{key}")
        base += f" AND ({' OR '.join(cat_clauses)})"

    if exclude_ids is not None and len(exclude_ids) > 0:
        ex_placeholders = ", ".join(f":ex_{i}" for i in range(len(exclude_ids)))
        base += f" AND c.internal_id NOT IN ({ex_placeholders})"
        for i, eid in enumerate(exclude_ids):
            params[f"ex_{i}"] = eid

    col = sort if sort in _SORTABLE else "recompete_score"
    order = "ASC" if direction == "asc" else "DESC"

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) {base}"), params).scalar()
        if all_rows:
            rows = conn.execute(
                text(f"SELECT c.* {base} ORDER BY c.{col} {order}"), params,
            ).mappings().fetchall()
        else:
            rows = conn.execute(
                text(f"SELECT c.* {base} ORDER BY c.{col} {order} LIMIT :limit OFFSET :offset"),
                {**params, "limit": limit, "offset": (page - 1) * limit},
            ).mappings().fetchall()

    return {
        "contracts": rows, "page": page,
        "start": (page - 1) * limit, "total": total, "count": len(rows),
    }
