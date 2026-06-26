-- migrations/021_lead_outreach_tracking.sql
-- Lead Intelligence follow-up: per-lead outreach status, free-text notes, and a
-- normalized-name key for dedupe-safe imports.
-- Idempotent: ADD COLUMN IF NOT EXISTS guards make it safe to re-run, and safe
-- on existing deployed lead_companies rows (existing prospects are preserved;
-- new columns default to "not contacted" / empty).
ALTER TABLE lead_companies ADD COLUMN IF NOT EXISTS contacted_status TEXT NOT NULL DEFAULT 'not_contacted';
ALTER TABLE lead_companies ADD COLUMN IF NOT EXISTS outreach_notes TEXT;
ALTER TABLE lead_companies ADD COLUMN IF NOT EXISTS normalized_name TEXT;
CREATE INDEX IF NOT EXISTS idx_lead_companies_normalized ON lead_companies(normalized_name);
