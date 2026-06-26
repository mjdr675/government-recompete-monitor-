-- Add naics_description to contracts.
-- The search endpoint returns NAICS as {"code": ..., "description": ...};
-- previously only the code was stored. Enrichment also provides naics_description
-- from latest_transaction_contract_data.
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS naics_description TEXT;
