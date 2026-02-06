-- Add encounter_id column to experity_process_time table
ALTER TABLE experity_process_time
    ADD COLUMN IF NOT EXISTS encounter_id UUID;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_experity_process_time_encounter_id 
    ON experity_process_time(encounter_id);
