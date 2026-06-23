-- migrations/012_contract_field_changes.sql
-- Auto Updates Commit 1 — field-level change detection foundation.
-- Records diffs of tracked contract fields between consecutive snapshots.
-- Idempotent: IF NOT EXISTS guards make it safe to re-run.
CREATE TABLE IF NOT EXISTS contract_field_changes (
    id              SERIAL PRIMARY KEY,
    run_date        TEXT NOT NULL,
    contract_id     TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    old_snapshot_id INTEGER,
    new_snapshot_id INTEGER,
    changed_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_field_changes_run_date
    ON contract_field_changes(run_date);
CREATE INDEX IF NOT EXISTS idx_field_changes_contract
    ON contract_field_changes(contract_id);
