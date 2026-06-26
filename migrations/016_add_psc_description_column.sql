-- migrations/016_add_psc_description_column.sql
-- Add the psc_description column to contracts before 016_backfill populates it.
-- Postgres path only: the .sql migration runner is invoked when DATABASE_URL is
-- set; SQLite databases get this column via db.init_db()'s
-- _ensure_psc_description_column() helper instead.
-- Idempotent (ADD COLUMN IF NOT EXISTS) so it is safe to re-run and a no-op on
-- databases that already have the column.
-- Sorts before 016_backfill_psc_description.sql so the column exists first.

ALTER TABLE contracts ADD COLUMN IF NOT EXISTS psc_description TEXT;
