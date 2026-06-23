-- migrations/002_subscription_and_alerts.sql
-- Subscription/trial columns and alert tables.
-- Idempotent: uses ADD COLUMN IF NOT EXISTS and IF NOT EXISTS guards.
-- Applied automatically at release time via init_db() when DATABASE_URL is set.

-- Subscription and trial fields on users
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'trialing';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at        TEXT;

-- Alert preferences per user (one row per user, upserted on save)
CREATE TABLE IF NOT EXISTS alert_preferences (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    expiry_days INTEGER NOT NULL DEFAULT 30,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL
);

-- Deduplication log for sent alerts
-- UNIQUE(user_id, internal_id, alert_type) prevents duplicate sends.
CREATE TABLE IF NOT EXISTS alert_log (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    internal_id TEXT NOT NULL,
    alert_type  TEXT NOT NULL DEFAULT 'expiry',
    sent_at     TEXT NOT NULL,
    UNIQUE(user_id, internal_id, alert_type)
);

CREATE INDEX IF NOT EXISTS idx_alert_log_user ON alert_log(user_id);
