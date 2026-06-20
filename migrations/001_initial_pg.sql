-- migrations/001_initial_pg.sql
-- Initial PostgreSQL schema for Government Recompete Monitor.
-- Idempotent: safe to run against an existing database (IF NOT EXISTS guards).
-- Run before gunicorn starts via the Procfile release step.

-- pgvector extension for future vector-search use cases
CREATE EXTENSION IF NOT EXISTS vector;

-- Main contracts table with FTS search_vector (PostgreSQL 12+ generated column)
CREATE TABLE IF NOT EXISTS contracts (
    internal_id        TEXT PRIMARY KEY,
    award_id           TEXT,
    vendor             TEXT,
    agency             TEXT,
    sub_agency         TEXT,
    value              REAL,
    start_date         TEXT,
    end_date           TEXT,
    days_remaining     INTEGER,
    competition_type   TEXT,
    solicitation_id    TEXT,
    recompete_score    INTEGER,
    priority           TEXT,
    raw_json           TEXT,
    updated_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    search_vector      tsvector GENERATED ALWAYS AS (
        to_tsvector('english',
            COALESCE(vendor, '') || ' ' ||
            COALESCE(agency, '') || ' ' ||
            COALESCE(award_id, '')
        )
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_contracts_vendor   ON contracts(vendor);
CREATE INDEX IF NOT EXISTS idx_contracts_agency   ON contracts(agency);
CREATE INDEX IF NOT EXISTS idx_contracts_priority ON contracts(priority);
CREATE INDEX IF NOT EXISTS idx_contracts_score    ON contracts(recompete_score DESC);
CREATE INDEX IF NOT EXISTS idx_contracts_fts      ON contracts USING GIN(search_vector);

-- Point-in-time snapshots for change detection
CREATE TABLE IF NOT EXISTS contract_snapshots (
    id               SERIAL PRIMARY KEY,
    run_date         TEXT NOT NULL,
    internal_id      TEXT NOT NULL,
    award_id         TEXT,
    vendor           TEXT,
    agency           TEXT,
    sub_agency       TEXT,
    value            REAL,
    start_date       TEXT,
    end_date         TEXT,
    days_remaining   INTEGER,
    competition_type TEXT,
    solicitation_id  TEXT,
    recompete_score  INTEGER,
    priority         TEXT,
    raw_json         TEXT,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_date, internal_id)
);

-- Detected contract changes between snapshot runs
CREATE TABLE IF NOT EXISTS changes (
    id           SERIAL PRIMARY KEY,
    run_date     TEXT NOT NULL,
    change_type  TEXT NOT NULL,
    internal_id  TEXT NOT NULL,
    old_priority TEXT,
    new_priority TEXT,
    description  TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- User accounts
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Demo request submissions
CREATE TABLE IF NOT EXISTS demo_requests (
    id                  SERIAL PRIMARY KEY,
    email               TEXT NOT NULL,
    name                TEXT,
    company             TEXT,
    phone               TEXT,
    notes               TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    hubspot_contact_id  TEXT,
    hubspot_deal_id     TEXT
);

-- Early access sign-ups
CREATE TABLE IF NOT EXISTS early_access (
    id                  SERIAL PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    hubspot_contact_id  TEXT
);

-- User watchlist (bookmarked contracts)
CREATE TABLE IF NOT EXISTS user_watchlist (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    internal_id TEXT NOT NULL,
    added_at    TEXT NOT NULL,
    UNIQUE(user_id, internal_id)
);

-- Celery task execution log
CREATE TABLE IF NOT EXISTS celery_task_log (
    id           SERIAL PRIMARY KEY,
    task_name    TEXT,
    status       TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    result_json  TEXT
);

-- Ingest run metadata log
CREATE TABLE IF NOT EXISTS ingest_log (
    id               SERIAL PRIMARY KEY,
    run_date         TEXT NOT NULL,
    source           TEXT NOT NULL,
    record_count     INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    status           TEXT NOT NULL,
    error_message    TEXT,
    created_at       TEXT NOT NULL
);

-- User saved contract searches
CREATE TABLE IF NOT EXISTS user_saved_searches (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    query_params_json TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

-- Per-user private notes on contracts
CREATE TABLE IF NOT EXISTS contract_notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    internal_id TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
