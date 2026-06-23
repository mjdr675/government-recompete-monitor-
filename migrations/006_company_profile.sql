-- migrations/006_company_profile.sql
-- Company Profile foundation: one profile per user with normalised junction tables
-- for NAICS codes, geographic states, preferred agencies, and set-aside types.
--
-- Idempotent: every statement uses IF NOT EXISTS so this is safe to re-run.
-- Applied automatically at startup via _apply_migrations() when DATABASE_URL is set.

CREATE TABLE IF NOT EXISTS company_profiles (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    company_name       TEXT,
    website            TEXT,
    geo_coverage       TEXT NOT NULL DEFAULT 'nationwide',
    min_contract_value REAL,
    max_contract_value REAL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_naics (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    naics_code  TEXT NOT NULL,
    UNIQUE(profile_id, naics_code)
);

CREATE INDEX IF NOT EXISTS idx_company_naics_code ON company_naics(naics_code);

CREATE TABLE IF NOT EXISTS company_states (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    state_code  TEXT NOT NULL,
    UNIQUE(profile_id, state_code)
);

CREATE TABLE IF NOT EXISTS company_preferred_agencies (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    agency_name TEXT NOT NULL,
    UNIQUE(profile_id, agency_name)
);

CREATE INDEX IF NOT EXISTS idx_company_agencies_name ON company_preferred_agencies(agency_name);

CREATE TABLE IF NOT EXISTS company_set_asides (
    id             SERIAL PRIMARY KEY,
    profile_id     INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    set_aside_type TEXT NOT NULL,
    UNIQUE(profile_id, set_aside_type)
);
