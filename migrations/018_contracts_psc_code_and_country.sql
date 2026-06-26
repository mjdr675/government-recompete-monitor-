-- Add psc_code and place_of_performance_country to contracts.
-- These were available in raw_json but not as queryable columns.
-- Both are safe to add to existing tables (IF NOT EXISTS guard via DO NOTHING pattern).
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS psc_code TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS place_of_performance_country TEXT;
