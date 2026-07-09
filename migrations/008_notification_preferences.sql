-- 008_notification_preferences.sql
-- Adds user_notification_preferences table for per-user email notification controls.
-- Idempotent: uses CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS user_notification_preferences (
    id                              SERIAL PRIMARY KEY,
    user_id                         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    email_notifications_enabled     INTEGER NOT NULL DEFAULT 1,
    pipeline_digest_enabled         INTEGER NOT NULL DEFAULT 1,
    next_action_reminders_enabled   INTEGER NOT NULL DEFAULT 1,
    opportunity_alerts_enabled      INTEGER NOT NULL DEFAULT 1,
    digest_frequency                TEXT NOT NULL DEFAULT 'weekly',
    updated_at                      TEXT NOT NULL
);
