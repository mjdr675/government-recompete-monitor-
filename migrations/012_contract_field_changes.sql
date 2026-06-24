-- migrations/012_contract_field_changes.sql
-- Generic field-level contract change history (Auto Contract Updates lane).
--
-- Records one row per (run_date, internal_id, field_name) describing how a
-- tracked field changed between the two most recent contract_snapshots runs.
-- Kept separate from the priority-coupled `changes` table so existing
-- change_detector / report_builder / vendor change_events behavior is preserved.
--
-- SQLite (dev) also creates this lazily via db.init_field_changes_table();
-- this file is the PostgreSQL (prod) path, applied by _apply_migrations().
--
-- All statements are idempotent (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS contract_field_changes (
    id          SERIAL PRIMARY KEY,
    run_date    TEXT NOT NULL,
    internal_id TEXT NOT NULL,
    field_name  TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    change_kind TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_date, internal_id, field_name)
);

CREATE INDEX IF NOT EXISTS idx_field_changes_run_date
    ON contract_field_changes(run_date);
CREATE INDEX IF NOT EXISTS idx_field_changes_internal_id
    ON contract_field_changes(internal_id);
