-- migrations/023_company_psc_codes.sql
-- Add company_psc_codes table for PSC (Product/Service Code) preference matching.
-- PSC codes on contracts (psc_code column) are 4-character codes; this table
-- lets users specify the PSC prefixes they serve so scoring can match them.
-- Idempotent: IF NOT EXISTS guards make it safe to re-run.

CREATE TABLE IF NOT EXISTS company_psc_codes (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    psc_code    TEXT NOT NULL,
    UNIQUE(profile_id, psc_code)
);

CREATE INDEX IF NOT EXISTS idx_company_psc_codes_profile
    ON company_psc_codes(profile_id);
