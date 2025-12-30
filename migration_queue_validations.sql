-- Migration: Create queue_validations table
-- Run this on production database

-- Create queue_validations table
CREATE TABLE IF NOT EXISTS queue_validations (
    validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id UUID NOT NULL UNIQUE REFERENCES queue(queue_id) ON DELETE CASCADE,
    encounter_id UUID NOT NULL,
    validation_result JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for queue_validations table
CREATE INDEX IF NOT EXISTS idx_queue_validations_queue_id ON queue_validations(queue_id);
CREATE INDEX IF NOT EXISTS idx_queue_validations_encounter_id ON queue_validations(encounter_id);
CREATE INDEX IF NOT EXISTS idx_queue_validations_created_at ON queue_validations(created_at);

-- Ensure new columns exist (for legacy tables - in case table exists without columns)
DO $$
BEGIN
    -- Check if table exists but columns don't
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'queue_validations') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'validation_id') THEN
            ALTER TABLE queue_validations ADD COLUMN validation_id UUID DEFAULT gen_random_uuid();
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'queue_id') THEN
            ALTER TABLE queue_validations ADD COLUMN queue_id UUID;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'encounter_id') THEN
            ALTER TABLE queue_validations ADD COLUMN encounter_id UUID;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'validation_result') THEN
            ALTER TABLE queue_validations ADD COLUMN validation_result JSONB;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'created_at') THEN
            ALTER TABLE queue_validations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'queue_validations' AND column_name = 'updated_at') THEN
            ALTER TABLE queue_validations ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        END IF;
    END IF;
END $$;

-- Ensure uniqueness on queue_id (create unique index if it doesn't exist)
CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_validations_queue_id_unique ON queue_validations(queue_id);

-- Add foreign key constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'queue_validations_queue_id_fkey'
    ) THEN
        ALTER TABLE queue_validations 
        ADD CONSTRAINT queue_validations_queue_id_fkey 
        FOREIGN KEY (queue_id) REFERENCES queue(queue_id) ON DELETE CASCADE;
    END IF;
END $$;

-- Create trigger to automatically update updated_at for queue_validations
DROP TRIGGER IF EXISTS update_queue_validations_updated_at ON queue_validations;
CREATE TRIGGER update_queue_validations_updated_at
    BEFORE UPDATE ON queue_validations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

