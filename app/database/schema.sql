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

-- Create encounters table
CREATE TABLE IF NOT EXISTS encounters (
    id UUID PRIMARY KEY,
    encounter_id UUID UNIQUE NOT NULL,
    client_id VARCHAR(255) NOT NULL,
    patient_id UUID NOT NULL,
    trauma_type VARCHAR(50),
    chief_complaints JSONB NOT NULL,
    status VARCHAR(50),
    created_by VARCHAR(255),
    started_at TIMESTAMP,
    raw_payload JSONB,
    parsed_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chief_complaints_not_empty CHECK (jsonb_array_length(chief_complaints) > 0)
);

-- Create indexes for encounters table
CREATE INDEX IF NOT EXISTS idx_encounters_encounter_id ON encounters(encounter_id);
CREATE INDEX IF NOT EXISTS idx_encounters_patient_id ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_client_id ON encounters(client_id);
CREATE INDEX IF NOT EXISTS idx_encounters_started_at ON encounters(started_at);
CREATE INDEX IF NOT EXISTS idx_encounters_status ON encounters(status);
CREATE INDEX IF NOT EXISTS idx_encounters_created_at ON encounters(created_at);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE encounters
    ADD COLUMN IF NOT EXISTS id UUID,
    ADD COLUMN IF NOT EXISTS encounter_id UUID,
    ADD COLUMN IF NOT EXISTS client_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS patient_id UUID,
    ADD COLUMN IF NOT EXISTS trauma_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS chief_complaints JSONB,
    ADD COLUMN IF NOT EXISTS status VARCHAR(50),
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS parsed_payload JSONB,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add NOT NULL constraint to chief_complaints if it doesn't exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'encounters' AND column_name = 'chief_complaints' 
               AND is_nullable = 'YES') THEN
        -- Delete any rows with NULL chief_complaints (invalid data)
        DELETE FROM encounters WHERE chief_complaints IS NULL;
        -- Then add NOT NULL constraint
        ALTER TABLE encounters ALTER COLUMN chief_complaints SET NOT NULL;
    END IF;
END $$;

-- Add check constraint to ensure chief_complaints is not empty
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'chief_complaints_not_empty' 
        AND conrelid = 'encounters'::regclass
    ) THEN
        ALTER TABLE encounters 
        ADD CONSTRAINT chief_complaints_not_empty 
        CHECK (jsonb_array_length(chief_complaints) > 0);
    END IF;
END $$;

-- Ensure uniqueness on encounter_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_encounters_encounter_id_unique ON encounters(encounter_id);

-- Create trigger to automatically update updated_at for encounters
DROP TRIGGER IF EXISTS update_encounters_updated_at ON encounters;
CREATE TRIGGER update_encounters_updated_at
    BEFORE UPDATE ON encounters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

