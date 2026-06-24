-- migrations/015_location_columns.sql
-- Promote city and zip to first-class columns so they are searchable and
-- displayable in the contracts list without requiring raw_json parsing.
-- Data is populated at next ingest run by the data-pipeline lane.

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS place_of_performance_city TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS place_of_performance_zip  TEXT;

-- Rebuild the full-text search vector to include city so users can find
-- contracts by city name (e.g. searching "Arlington" returns VA contracts).
ALTER TABLE contracts DROP COLUMN IF EXISTS search_vector;
ALTER TABLE contracts ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('english',
        COALESCE(vendor, '') || ' ' || COALESCE(agency, '') || ' ' ||
        COALESCE(award_id, '') || ' ' || COALESCE(description, '') || ' ' ||
        COALESCE(naics_code, '') || ' ' ||
        COALESCE(place_of_performance_state, '') || ' ' ||
        COALESCE(place_of_performance_city, '')
    )
) STORED;

CREATE INDEX IF NOT EXISTS idx_contracts_city ON contracts(place_of_performance_city);
CREATE INDEX IF NOT EXISTS idx_contracts_zip  ON contracts(place_of_performance_zip);
