-- Migration script to create alerts table
-- This script can be run independently to add the alerts table to an existing database

-- Create alerts table for monitoring and alerting system
CREATE TABLE IF NOT EXISTS alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL CHECK (source IN ('vm', 'server', 'uipath', 'monitor')),
    source_id VARCHAR(255) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
    message TEXT NOT NULL,
    details JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for alerts table
CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source, source_id);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_source_severity ON alerts(source, severity, resolved);

-- Ensure new columns exist (for legacy tables)
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS alert_id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS source_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS severity VARCHAR(20),
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS details JSONB,
    ADD COLUMN IF NOT EXISTS resolved BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add check constraints if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'alerts_source_check' 
        AND conrelid = 'alerts'::regclass
    ) THEN
        ALTER TABLE alerts 
        ADD CONSTRAINT alerts_source_check 
        CHECK (source IN ('vm', 'server', 'uipath', 'monitor'));
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'alerts_severity_check' 
        AND conrelid = 'alerts'::regclass
    ) THEN
        ALTER TABLE alerts 
        ADD CONSTRAINT alerts_severity_check 
        CHECK (severity IN ('critical', 'warning', 'info'));
    END IF;
END $$;

-- Ensure alert_id is the primary key
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'alerts' 
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name != 'alerts_pkey'
    ) THEN
        ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_pkey;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'alerts' 
        AND constraint_type = 'PRIMARY KEY'
    ) THEN
        ALTER TABLE alerts ADD PRIMARY KEY (alert_id);
    END IF;
END $$;

-- Create trigger to automatically update updated_at for alerts
DROP TRIGGER IF EXISTS update_alerts_updated_at ON alerts;
CREATE TRIGGER update_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
