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

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_patients_emr_id ON patients(emr_id);
CREATE INDEX IF NOT EXISTS idx_patients_location_id ON patients(location_id);
CREATE INDEX IF NOT EXISTS idx_patients_captured_at ON patients(captured_at);
CREATE INDEX IF NOT EXISTS idx_patients_created_at ON patients(created_at);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE patients
    ADD COLUMN IF NOT EXISTS booking_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS booking_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS patient_number VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_first_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_last_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS dob VARCHAR(50),
    ADD COLUMN IF NOT EXISTS mobile_phone VARCHAR(50),
    ADD COLUMN IF NOT EXISTS sex_at_birth VARCHAR(50),
    ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS reason_for_visit TEXT;

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

