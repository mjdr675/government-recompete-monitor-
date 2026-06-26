-- migrations/018_contract_field_changes_change_kind.sql
-- Repair pre-existing contract_field_changes tables missing the change_kind
-- column. The column is in 012_contract_field_changes.sql's CREATE TABLE (and
-- the SQLite db.init_field_changes_table() definition), but CREATE TABLE
-- IF NOT EXISTS is a no-op on a table that predates the column, so existing
-- installs never gained it and insert_field_changes() fails with
-- "no column named change_kind".
--
-- Postgres path only (the .sql runner is invoked when DATABASE_URL is set);
-- SQLite repairs this in db.init_field_changes_table().
-- Added nullable (not NOT NULL) so it is safe on tables with existing rows;
-- the application always writes change_kind on new rows.
-- Idempotent (ADD COLUMN IF NOT EXISTS) so it is safe to re-run.

ALTER TABLE contract_field_changes ADD COLUMN IF NOT EXISTS change_kind TEXT;
