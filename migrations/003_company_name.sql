-- Add optional company_name to users (Task: collect company name at signup).
-- Idempotent and backward compatible: existing users keep NULL company_name and
-- the UI falls back to their email until they set one.
ALTER TABLE users ADD COLUMN IF NOT EXISTS company_name TEXT;
