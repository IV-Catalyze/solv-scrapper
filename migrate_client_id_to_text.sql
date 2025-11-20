-- Migration: Change client_id from UUID to VARCHAR(255) in encounters table
-- This allows storing prefixed client IDs like "Stage-..." or "Prod-..."

-- Drop the index first (will recreate it)
DROP INDEX IF EXISTS idx_encounters_client_id;

-- Alter the column type from UUID to VARCHAR(255)
-- Note: This will fail if there are existing UUID values that can't be converted
-- If you have existing data, you may need to handle the conversion differently
ALTER TABLE encounters
    ALTER COLUMN client_id TYPE VARCHAR(255) USING client_id::text;

-- Recreate the index
CREATE INDEX IF NOT EXISTS idx_encounters_client_id ON encounters(client_id);

-- Verify the change
SELECT 
    column_name, 
    data_type, 
    character_maximum_length
FROM information_schema.columns 
WHERE table_name = 'encounters' 
AND column_name = 'client_id';

