-- migrations/009_discovery_columns.sql
-- Add contract discovery columns: NAICS code, place of performance state, category
-- Updates search_vector to include new searchable fields

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS naics_code TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS place_of_performance_state TEXT;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS category TEXT;

ALTER TABLE contracts DROP COLUMN IF EXISTS search_vector;
ALTER TABLE contracts ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('english',
        COALESCE(vendor, '') || ' ' || COALESCE(agency, '') || ' ' ||
        COALESCE(award_id, '') || ' ' || COALESCE(description, '') || ' ' ||
        COALESCE(naics_code, '') || ' ' || COALESCE(place_of_performance_state, '')
    )
) STORED;

CREATE INDEX IF NOT EXISTS idx_contracts_fts ON contracts USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_contracts_state ON contracts(place_of_performance_state);
CREATE INDEX IF NOT EXISTS idx_contracts_category ON contracts(category);
