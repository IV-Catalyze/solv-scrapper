-- Migration: Add server_id and uipath_status columns to vm_health table
-- Date: 2025-01-22
-- Purpose: Support enhanced VM heartbeat tracking with server ID and UiPath status

-- Add server_id column if it doesn't exist
ALTER TABLE vm_health
    ADD COLUMN IF NOT EXISTS server_id VARCHAR(255);

-- Add uipath_status column if it doesn't exist
ALTER TABLE vm_health
    ADD COLUMN IF NOT EXISTS uipath_status VARCHAR(50);

-- Create index on server_id for faster queries
CREATE INDEX IF NOT EXISTS idx_vm_health_server_id ON vm_health(server_id);

-- Create index on uipath_status for faster queries
CREATE INDEX IF NOT EXISTS idx_vm_health_uipath_status ON vm_health(uipath_status);

-- Note: metadata column already exists as JSONB, so no migration needed for it
