-- Migration script to simplify encounters table
-- This migration:
-- 1. Renames raw_payload to encounter_payload
-- 2. Removes all columns except emr_id, encounter_id, and encounter_payload
-- 3. Drops the chief_complaints_not_empty constraint
-- 4. Updates indexes

-- Step 1: Drop the constraint and trigger first
ALTER TABLE encounters DROP CONSTRAINT IF EXISTS chief_complaints_not_empty;

-- Drop the trigger for updated_at (column will be removed)
DROP TRIGGER IF EXISTS update_encounters_updated_at ON encounters;

-- Step 2: Handle encounter_payload column
DO $$
BEGIN
    -- If raw_payload exists, copy data to encounter_payload first (if encounter_payload doesn't exist)
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'encounters' AND column_name = 'raw_payload')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'encounters' AND column_name = 'encounter_payload') THEN
        -- Create encounter_payload column and copy data
        ALTER TABLE encounters ADD COLUMN encounter_payload JSONB;
        UPDATE encounters SET encounter_payload = raw_payload WHERE raw_payload IS NOT NULL;
        -- Now rename raw_payload (we'll drop it later)
        ALTER TABLE encounters RENAME COLUMN raw_payload TO raw_payload_old;
    -- If encounter_payload doesn't exist and raw_payload doesn't exist, create it
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'encounters' AND column_name = 'encounter_payload') THEN
        ALTER TABLE encounters ADD COLUMN encounter_payload JSONB;
    END IF;
END $$;

-- Step 2b: For rows where encounter_payload is NULL, create a minimal payload from existing data
UPDATE encounters 
SET encounter_payload = jsonb_build_object(
    'id', COALESCE(id::text, encounter_id::text),
    'encounterId', encounter_id::text,
    'emrId', emr_id,
    'clientId', client_id,
    'traumaType', trauma_type,
    'status', status,
    'chiefComplaints', COALESCE(chief_complaints, '[]'::jsonb)
)
WHERE encounter_payload IS NULL;

-- Step 3: Drop indexes that reference columns we're removing
DROP INDEX IF EXISTS idx_encounters_client_id;
DROP INDEX IF EXISTS idx_encounters_started_at;
DROP INDEX IF EXISTS idx_encounters_status;
DROP INDEX IF EXISTS idx_encounters_created_at;

-- Step 4: Drop columns we no longer need
ALTER TABLE encounters
    DROP COLUMN IF EXISTS id,
    DROP COLUMN IF EXISTS client_id,
    DROP COLUMN IF EXISTS trauma_type,
    DROP COLUMN IF EXISTS chief_complaints,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS created_by,
    DROP COLUMN IF EXISTS started_at,
    DROP COLUMN IF EXISTS parsed_payload,
    DROP COLUMN IF EXISTS raw_payload_old,
    DROP COLUMN IF EXISTS raw_payload,
    DROP COLUMN IF EXISTS created_at,
    DROP COLUMN IF EXISTS updated_at;

-- Step 5: Make encounter_id the primary key (since we're removing id)
-- First, drop the existing primary key constraint if it exists
ALTER TABLE encounters DROP CONSTRAINT IF EXISTS encounters_pkey;

-- Make encounter_id the primary key
ALTER TABLE encounters ADD PRIMARY KEY (encounter_id);

-- Step 6: Delete any rows that still have NULL encounter_payload (invalid data)
DELETE FROM encounters WHERE encounter_payload IS NULL;

-- Step 7: Ensure encounter_payload is NOT NULL (since it's required)
ALTER TABLE encounters ALTER COLUMN encounter_payload SET NOT NULL;

-- Step 8: Ensure emr_id is NOT NULL (since it's required)
-- First, delete rows with NULL emr_id if any
DELETE FROM encounters WHERE emr_id IS NULL;
ALTER TABLE encounters ALTER COLUMN emr_id SET NOT NULL;

-- Step 8: Recreate the unique index on encounter_id (should already exist, but ensure it)
CREATE UNIQUE INDEX IF NOT EXISTS idx_encounters_encounter_id_unique ON encounters(encounter_id);

-- Step 9: Keep the emr_id index
CREATE INDEX IF NOT EXISTS idx_encounters_emr_id ON encounters(emr_id);

-- Note: The encounters table now has only 3 columns:
-- - encounter_id (UUID, PRIMARY KEY, UNIQUE, NOT NULL)
-- - emr_id (VARCHAR(255), NOT NULL)
-- - encounter_payload (JSONB, NOT NULL)

