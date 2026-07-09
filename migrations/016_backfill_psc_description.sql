-- migrations/016_backfill_psc_description.sql
-- Promote psc_description to a queryable first-class column.
-- Prior to this migration the value was stored only in raw_json.
-- Use regexp_match (scalar, returns text[]) to extract the value safely
-- without a full JSONB cast, so malformed or NULL raw_json rows are silently
-- skipped. NOTE: regexp_match() is used deliberately instead of the plural
-- regexp_matches(), which is set-returning and is rejected by PostgreSQL inside
-- UPDATE ... SET ("set-returning functions are not allowed in UPDATE").

UPDATE contracts
SET psc_description = (regexp_match(raw_json, '"psc_description"\s*:\s*"([^"]*)"'))[1]
WHERE psc_description IS NULL
  AND raw_json IS NOT NULL
  AND raw_json <> ''
  AND raw_json ~ '"psc_description"\s*:\s*"[^"]';
