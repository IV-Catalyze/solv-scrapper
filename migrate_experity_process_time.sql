-- Create experity_process_time table for monitoring Experity process durations
CREATE TABLE IF NOT EXISTS experity_process_time (
    process_time_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_name VARCHAR(100) NOT NULL CHECK (process_name IN ('Encounter process time', 'Experity process time')),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NOT NULL,
    duration_seconds INTEGER,  -- Calculated field: ended_at - started_at
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_experity_process_time_process_name ON experity_process_time(process_name);
CREATE INDEX IF NOT EXISTS idx_experity_process_time_started_at ON experity_process_time(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_experity_process_time_ended_at ON experity_process_time(ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_experity_process_time_created_at ON experity_process_time(created_at DESC);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE experity_process_time
    ADD COLUMN IF NOT EXISTS process_time_id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS process_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS ended_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS duration_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add check constraint for process_name if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'experity_process_time_process_name_check' 
        AND conrelid = 'experity_process_time'::regclass
    ) THEN
        ALTER TABLE experity_process_time 
        ADD CONSTRAINT experity_process_time_process_name_check 
        CHECK (process_name IN ('Encounter process time', 'Experity process time'));
    END IF;
END $$;

-- Ensure process_time_id is the primary key
DO $$
BEGIN
    -- Drop existing primary key if it's on a different column
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'experity_process_time' 
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name != 'experity_process_time_pkey'
    ) THEN
        ALTER TABLE experity_process_time DROP CONSTRAINT IF EXISTS experity_process_time_pkey;
    END IF;
    
    -- Add primary key on process_time_id if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'experity_process_time' 
        AND constraint_type = 'PRIMARY KEY'
    ) THEN
        ALTER TABLE experity_process_time ADD PRIMARY KEY (process_time_id);
    END IF;
END $$;

-- Create trigger to automatically update updated_at
DROP TRIGGER IF EXISTS update_experity_process_time_updated_at ON experity_process_time;
CREATE TRIGGER update_experity_process_time_updated_at
    BEFORE UPDATE ON experity_process_time
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to calculate duration when ended_at is set
CREATE OR REPLACE FUNCTION calculate_experity_process_duration()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.ended_at IS NOT NULL AND NEW.started_at IS NOT NULL THEN
        NEW.duration_seconds := EXTRACT(EPOCH FROM (NEW.ended_at - NEW.started_at))::INTEGER;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-calculate duration
DROP TRIGGER IF EXISTS calculate_experity_process_duration ON experity_process_time;
CREATE TRIGGER calculate_experity_process_duration
    BEFORE INSERT OR UPDATE ON experity_process_time
    FOR EACH ROW
    EXECUTE FUNCTION calculate_experity_process_duration();
