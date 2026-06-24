-- migrations/006_contracts_sam_url.sql
-- Add sam_url column to contracts so the direct SAM.gov opportunity link
-- (returned by the SAM API as uiLink) is queryable without parsing raw_json.
--
-- The column is NULL for contracts where no live SAM solicitation was matched.
-- The UI falls back to a keyword search on SAM.gov when sam_url is empty.
--
-- Idempotent (IF NOT EXISTS). Applied at release via init_db() / Procfile release step.
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS sam_url TEXT;
