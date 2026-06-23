-- migrations/014_workspace_billing.sql
-- Workspace-level billing: subscription tiers + 7-day trial + Stripe linkage.
-- Additive to the Phase 1 workspaces table; idempotent guards make it re-runnable.
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'starter';
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'trialing';
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS trial_start_at TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS trial_end_at TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

CREATE TABLE IF NOT EXISTS workspace_billing_events (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
    event_type      TEXT,
    stripe_event_id TEXT,
    payload_json    TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_billing_events_ws
    ON workspace_billing_events(workspace_id);
