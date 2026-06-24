-- migrations/015_feedback_and_billing_interval.sql
-- Add feedback_submissions table and billing_interval column to workspaces.
-- Idempotent: safe to re-run (IF NOT EXISTS + DO NOTHING on column add).

CREATE TABLE IF NOT EXISTS feedback_submissions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email       TEXT,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback_submissions(status);

ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS billing_interval TEXT NOT NULL DEFAULT 'monthly';
