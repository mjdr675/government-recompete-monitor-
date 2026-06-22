-- migrations/007_opportunities.sql
-- Opportunity Pipeline: one row per (user, contract) the user is actively pursuing.
--
-- Design notes:
-- * No hard FK to contracts — internal_id joins contracts.internal_id at read
--   time via LEFT JOIN so orphaned rows survive a contract purge gracefully.
-- * created_by_user_id / last_updated_by_user_id mirror user_id for now;
--   they become distinct when multi-user company teams land (P1 blueprint).
-- * Idempotent: every statement uses IF NOT EXISTS / IF NOT EXISTS guards.

CREATE TABLE IF NOT EXISTS opportunities (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    internal_id             TEXT NOT NULL,
    stage                   TEXT NOT NULL DEFAULT 'new',
    probability             INTEGER CHECK (probability IS NULL OR (probability >= 0 AND probability <= 100)),
    next_action             TEXT,
    next_action_due         TEXT,
    notes                   TEXT,
    created_by_user_id      INTEGER NOT NULL REFERENCES users(id),
    last_updated_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    UNIQUE(user_id, internal_id)
);

CREATE INDEX IF NOT EXISTS idx_opportunities_user
    ON opportunities(user_id);

CREATE INDEX IF NOT EXISTS idx_opportunities_user_stage
    ON opportunities(user_id, stage);

CREATE INDEX IF NOT EXISTS idx_opportunities_user_due
    ON opportunities(user_id, next_action_due);
