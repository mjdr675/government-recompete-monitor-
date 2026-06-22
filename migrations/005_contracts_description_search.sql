-- migrations/005_contracts_description_search.sql
-- Add description column to contracts and include it in full-text search.
--
-- Why: contract descriptions from USAspending (e.g. "Janitorial and facility
-- maintenance services for DOD Building 47") contain the work-type keywords
-- contractors actually search by. Previously only vendor/agency/award_id were
-- indexed, so keyword searches missed most relevant contracts.
--
-- SQLite path: handled in db._ensure_description_column() at startup.
-- PostgreSQL path: this file (applied via _apply_pg_migrations() at startup).
--
-- All statements are idempotent (IF NOT EXISTS / IF EXISTS guards).

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS description TEXT;

-- Regenerate search_vector to include description so full-text search covers
-- contract work descriptions. Generated columns cannot be altered in place —
-- drop and recreate with the updated expression.
ALTER TABLE contracts DROP COLUMN IF EXISTS search_vector;
ALTER TABLE contracts ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('english',
        COALESCE(vendor, '') || ' ' ||
        COALESCE(agency, '') || ' ' ||
        COALESCE(award_id, '') || ' ' ||
        COALESCE(description, '')
    )
) STORED;

-- Recreate GIN index (dropped automatically with the column above).
CREATE INDEX IF NOT EXISTS idx_contracts_fts ON contracts USING GIN(search_vector);
