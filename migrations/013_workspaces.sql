-- migrations/013_workspaces.sql
-- Customer Workspace foundation — company-level workspace + team membership.
-- Permissions/invitations are intentionally out of scope here; the role column
-- exists for future use but is not enforced.
-- Idempotent: IF NOT EXISTS guards make it safe to re-run.
CREATE TABLE IF NOT EXISTS workspaces (
    id          SERIAL PRIMARY KEY,
    name        TEXT,
    logo_path   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id           SERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'owner',
    created_at   TEXT NOT NULL,
    UNIQUE(workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user
    ON workspace_members(user_id);
