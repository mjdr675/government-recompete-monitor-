-- Migration 017: add UEI and CAGE code columns to contracts table
-- These enable exact-match identification of incumbent vendors by federal identifiers.
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS recipient_uei TEXT NOT NULL DEFAULT '';
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS cage_code TEXT NOT NULL DEFAULT '';
