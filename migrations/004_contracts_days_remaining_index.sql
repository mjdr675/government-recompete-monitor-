-- migrations/004_contracts_days_remaining_index.sql
-- Add an index on contracts.days_remaining to match the SQLite schema.
-- Idempotent (IF NOT EXISTS). Applied automatically at release time via init_db().
--
-- days_remaining drives the dashboard "upcoming" range scan
-- (days_remaining BETWEEN 0 AND 90 ORDER BY days_remaining), the open/expired
-- status filter on /contracts, the watchlist expiry-alert query, and every
-- vendor/agency profile "ORDER BY days_remaining" — none of which had an index.
CREATE INDEX IF NOT EXISTS idx_contracts_days_remaining ON contracts(days_remaining);
