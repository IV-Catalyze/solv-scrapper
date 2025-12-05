-- PostgreSQL schema for patient data
-- Run this script to create the database and table

-- Create database (uncomment if needed)
-- CREATE DATABASE solvhealth_patients;

-- Connect to the database before running the table creation
-- \c solvhealth_patients;

-- Create patients table
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    emr_id VARCHAR(255) UNIQUE NOT NULL,
    booking_id VARCHAR(255),
    booking_number VARCHAR(255),
    patient_number VARCHAR(255),
    location_id VARCHAR(255) NOT NULL,
    location_name VARCHAR(255),
    status VARCHAR(50),
    legal_first_name VARCHAR(255),
    legal_last_name VARCHAR(255),
    dob VARCHAR(50),
    mobile_phone VARCHAR(50),
    sex_at_birth VARCHAR(50),
    captured_at TIMESTAMP,
    reason_for_visit TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create pending patients table (staging area before EMR ID is assigned)
CREATE TABLE IF NOT EXISTS pending_patients (
    pending_id SERIAL PRIMARY KEY,
    emr_id VARCHAR(255),
    booking_id VARCHAR(255),
    booking_number VARCHAR(255),
    patient_number VARCHAR(255),
    location_id VARCHAR(255) NOT NULL,
    location_name VARCHAR(255),
    legal_first_name VARCHAR(255),
    legal_last_name VARCHAR(255),
    dob VARCHAR(50),
    mobile_phone VARCHAR(50),
    sex_at_birth VARCHAR(50),
    captured_at TIMESTAMP,
    reason_for_visit TEXT,
    raw_payload JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_patients_emr_id ON patients(emr_id);
CREATE INDEX IF NOT EXISTS idx_patients_location_id ON patients(location_id);
CREATE INDEX IF NOT EXISTS idx_patients_captured_at ON patients(captured_at);
CREATE INDEX IF NOT EXISTS idx_patients_created_at ON patients(created_at);

CREATE INDEX IF NOT EXISTS idx_pending_patients_status ON pending_patients(status);
CREATE INDEX IF NOT EXISTS idx_pending_patients_created_at ON pending_patients(created_at);
CREATE INDEX IF NOT EXISTS idx_pending_patients_emr_id ON pending_patients(emr_id);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE patients
    ADD COLUMN IF NOT EXISTS booking_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS booking_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS patient_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_first_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_last_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS status VARCHAR(50),
    ADD COLUMN IF NOT EXISTS dob VARCHAR(50),
    ADD COLUMN IF NOT EXISTS mobile_phone VARCHAR(50),
    ADD COLUMN IF NOT EXISTS sex_at_birth VARCHAR(50),
    ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS reason_for_visit TEXT;

ALTER TABLE pending_patients
    ADD COLUMN IF NOT EXISTS emr_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS booking_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS booking_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS patient_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_first_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_last_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS dob VARCHAR(50),
    ADD COLUMN IF NOT EXISTS mobile_phone VARCHAR(50),
    ADD COLUMN IF NOT EXISTS sex_at_birth VARCHAR(50),
    ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS reason_for_visit TEXT,
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Drop legacy columns that are no longer used
ALTER TABLE patients
    DROP COLUMN IF EXISTS patient_id,
    DROP COLUMN IF EXISTS solv_id,
    DROP COLUMN IF EXISTS first_name,
    DROP COLUMN IF EXISTS last_name,
    DROP COLUMN IF EXISTS date_of_birth,
    DROP COLUMN IF EXISTS gender,
    DROP COLUMN IF EXISTS room,
    DROP COLUMN IF EXISTS raw_data;

-- Ensure uniqueness on emr_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_emr_id_unique ON patients(emr_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update updated_at
DROP TRIGGER IF EXISTS update_patients_updated_at ON patients;
CREATE TRIGGER update_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_pending_patients_updated_at ON pending_patients;
CREATE TRIGGER update_pending_patients_updated_at
    BEFORE UPDATE ON pending_patients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create encounters table (simplified structure)
-- Note: This table now only stores emr_id, encounter_id, and encounter_payload
-- Run migrate_encounters_simplify.sql to migrate existing tables
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id UUID PRIMARY KEY,
    emr_id VARCHAR(255) NOT NULL,
    encounter_payload JSONB NOT NULL
);

-- Create indexes for encounters table
CREATE INDEX IF NOT EXISTS idx_encounters_encounter_id ON encounters(encounter_id);
CREATE INDEX IF NOT EXISTS idx_encounters_emr_id ON encounters(emr_id);

-- Ensure new columns exist (for legacy tables - will be removed by migration)
ALTER TABLE encounters
    ADD COLUMN IF NOT EXISTS encounter_id UUID,
    ADD COLUMN IF NOT EXISTS emr_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS encounter_payload JSONB;

-- Drop legacy encounter columns/indexes that are no longer used
ALTER TABLE encounters
    DROP COLUMN IF EXISTS patient_id,
    DROP COLUMN IF EXISTS id,
    DROP COLUMN IF EXISTS client_id,
    DROP COLUMN IF EXISTS trauma_type,
    DROP COLUMN IF EXISTS chief_complaints,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS created_by,
    DROP COLUMN IF EXISTS started_at,
    DROP COLUMN IF EXISTS raw_payload,
    DROP COLUMN IF EXISTS parsed_payload,
    DROP COLUMN IF EXISTS created_at,
    DROP COLUMN IF EXISTS updated_at;

DROP INDEX IF EXISTS idx_encounters_patient_id;
DROP INDEX IF EXISTS idx_encounters_client_id;
DROP INDEX IF EXISTS idx_encounters_started_at;
DROP INDEX IF EXISTS idx_encounters_status;
DROP INDEX IF EXISTS idx_encounters_created_at;

-- Drop constraint if it exists
ALTER TABLE encounters DROP CONSTRAINT IF EXISTS chief_complaints_not_empty;

-- Ensure encounter_id is the primary key
DO $$
BEGIN
    -- Drop existing primary key if it's on a different column
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'encounters' 
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name != 'encounters_pkey'
    ) THEN
        ALTER TABLE encounters DROP CONSTRAINT IF EXISTS encounters_pkey;
    END IF;
    
    -- Add primary key on encounter_id if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'encounters' 
        AND constraint_type = 'PRIMARY KEY'
    ) THEN
        ALTER TABLE encounters ADD PRIMARY KEY (encounter_id);
    END IF;
END $$;

-- Ensure NOT NULL constraints
ALTER TABLE encounters 
    ALTER COLUMN encounter_id SET NOT NULL,
    ALTER COLUMN emr_id SET NOT NULL,
    ALTER COLUMN encounter_payload SET NOT NULL;

-- Ensure uniqueness on encounter_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_encounters_encounter_id_unique ON encounters(encounter_id);

-- Note: No trigger needed for updated_at since that column has been removed

-- Create queue table
-- Note: parsed_payload JSONB structure:
--   - trauma_type: string
--   - chief_complaints: array of complaint objects
--   - experityAction: array of action objects (each object contains template, bodyAreaKey, etc.)
CREATE TABLE IF NOT EXISTS queue (
    queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID UNIQUE NOT NULL,
    emr_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'ERROR')),
    raw_payload JSONB,
    parsed_payload JSONB,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for queue table
CREATE INDEX IF NOT EXISTS idx_queue_encounter_id ON queue(encounter_id);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_emr_id ON queue(emr_id);
CREATE INDEX IF NOT EXISTS idx_queue_created_at ON queue(created_at);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE queue
    ADD COLUMN IF NOT EXISTS queue_id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS encounter_id UUID,
    ADD COLUMN IF NOT EXISTS emr_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS parsed_payload JSONB,
    ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add check constraint for status if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'queue_status_check' 
        AND conrelid = 'queue'::regclass
    ) THEN
        ALTER TABLE queue 
        ADD CONSTRAINT queue_status_check 
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'ERROR'));
    END IF;
END $$;

-- Ensure uniqueness on encounter_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_encounter_id_unique ON queue(encounter_id);

-- Create trigger to automatically update updated_at for queue
DROP TRIGGER IF EXISTS update_queue_updated_at ON queue;
CREATE TRIGGER update_queue_updated_at
    BEFORE UPDATE ON queue
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create summaries table
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    emr_id VARCHAR(255) NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for summaries table
CREATE INDEX IF NOT EXISTS idx_summaries_emr_id ON summaries(emr_id);
CREATE INDEX IF NOT EXISTS idx_summaries_created_at ON summaries(created_at);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE summaries
    ADD COLUMN IF NOT EXISTS emr_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS note TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add NOT NULL constraints if they don't exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'summaries' AND column_name = 'emr_id' 
               AND is_nullable = 'YES') THEN
        ALTER TABLE summaries ALTER COLUMN emr_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'summaries' AND column_name = 'note' 
               AND is_nullable = 'YES') THEN
        ALTER TABLE summaries ALTER COLUMN note SET NOT NULL;
    END IF;
END $$;

-- Create trigger to automatically update updated_at for summaries
DROP TRIGGER IF EXISTS update_summaries_updated_at ON summaries;
CREATE TRIGGER update_summaries_updated_at
    BEFORE UPDATE ON summaries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username VARCHAR(255),
    ADD COLUMN IF NOT EXISTS email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add NOT NULL constraints if they don't exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'users' AND column_name = 'username' 
               AND is_nullable = 'YES') THEN
        ALTER TABLE users ALTER COLUMN username SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'users' AND column_name = 'password_hash' 
               AND is_nullable = 'YES') THEN
        ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
    END IF;
END $$;

-- Ensure uniqueness on username and email
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL;

-- Create trigger to automatically update updated_at for users
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

