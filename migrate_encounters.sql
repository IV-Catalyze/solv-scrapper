-- Migration to add raw_payload and parsed_payload columns to encounters table
-- Run this after establishing Aptible tunnel

-- Check if columns exist and add them if missing
ALTER TABLE encounters 
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS parsed_payload JSONB;

-- Verify columns were added
SELECT 
    column_name, 
    data_type 
FROM information_schema.columns 
WHERE table_name = 'encounters' 
AND column_name IN ('raw_payload', 'parsed_payload')
ORDER BY column_name;

