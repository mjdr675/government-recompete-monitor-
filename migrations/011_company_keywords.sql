-- migrations/009_company_keywords.sql
-- Add company_keywords table for plain-language keyword matching.
-- Idempotent: IF NOT EXISTS guards make it safe to re-run.
CREATE TABLE IF NOT EXISTS company_keywords (
    id          SERIAL PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    UNIQUE(profile_id, keyword)
);
CREATE INDEX IF NOT EXISTS idx_company_keywords_profile
    ON company_keywords(profile_id);
