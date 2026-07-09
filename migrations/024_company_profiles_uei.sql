-- Migration 024: preserve company_profiles identity columns on PostgreSQL.
--
-- The SQLite dev schema (db.init_db) and the verified snapshot carry three
-- company_profiles columns the Postgres schema (migration 006) never defined:
--   * uei         — SAM Unique Entity Identifier (a real value exists in prod)
--   * vendor_name
--   * cage_code
--
-- These are NOT merely source-only drift: db.save_company_profile() runs its
-- INSERT ... ON CONFLICT upsert against the shared engine (Postgres when
-- DATABASE_URL is set) and writes all three columns. Without them the live app
-- would raise UndefinedColumn (500) on Postgres, and a fresh-load would drop the
-- real UEI as source-only. Add them as nullable TEXT to mirror the SQLite columns
-- exactly so values copy verbatim (NULL where absent).
--
-- (users.billing_interval is intentionally NOT added: it is a vestigial users
-- column no code writes — the app's billing_interval lives on workspaces via
-- migration 015 — and is all-NULL in the snapshot, so it stays an accepted drop.)
--
-- Idempotent (IF NOT EXISTS); runs on the Postgres-only path via _apply_migrations().
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS uei TEXT;
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS vendor_name TEXT;
ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS cage_code TEXT;
