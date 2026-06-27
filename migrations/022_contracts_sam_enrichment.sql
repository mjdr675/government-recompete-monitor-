-- migrations/022_contracts_sam_enrichment.sql
-- Add sam_type and sam_due_date columns so the SAM.gov notice type
-- (Solicitation / Award Notice / Sources Sought / etc.) and response
-- deadline are queryable without parsing raw_json.
--
-- These fields are populated by the SAM enrichment step during ingest
-- when SAM_API_KEY is set and a matching solicitation is found.
--
-- Contracts ingested before this migration will have empty strings for
-- both columns; the opportunity_status() classifier falls back to
-- days_remaining-based logic in that case.
--
-- Idempotent (IF NOT EXISTS). Applied at release via _apply_migrations().
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS sam_type TEXT NOT NULL DEFAULT '';
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS sam_due_date TEXT NOT NULL DEFAULT '';
