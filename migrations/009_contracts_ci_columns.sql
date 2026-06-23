-- migrations/009_contracts_ci_columns.sql
-- Add contract-intelligence display columns.
--
-- place_of_performance_state: two-letter state code extracted from ingest
--   enrichment data (USAspending place_of_performance.state_code). Stored as a
--   separate column so the detail and list pages can display location without
--   parsing raw_json on every request. SQLite path is handled by
--   db._ensure_ci_columns() at startup.
--
-- vendor_website: nullable URL for the vendor's public website. Not available
--   from USAspending or SAM.gov ingest — populated by future enrichment only.
--   Column is added now so the schema is ready; display logic shows nothing
--   when NULL (no fabricated URLs are ever inserted).
--
-- All statements are idempotent (IF NOT EXISTS / IF EXISTS guards).

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS place_of_performance_state TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS vendor_website TEXT;
