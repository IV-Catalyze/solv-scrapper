-- Migration: Rename uipath_status to workflow_status and update alert sources
-- Date: 2025-01-22
-- Purpose: Rename UiPath references to AI Agent Workflow for consistency

-- Step 1: Rename column in vm_health table
ALTER TABLE vm_health
    RENAME COLUMN uipath_status TO workflow_status;

-- Step 2: Drop old index and create new one
DROP INDEX IF EXISTS idx_vm_health_uipath_status;
CREATE INDEX IF NOT EXISTS idx_vm_health_workflow_status ON vm_health(workflow_status);

-- Step 3: Update alert source values from 'uipath' to 'workflow'
-- Note: This updates existing alerts in the database
UPDATE alerts
SET source = 'workflow'
WHERE source = 'uipath';

-- Step 4: Update check constraint on alerts table
-- Drop the old constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'alerts_source_check' 
        AND conrelid = 'alerts'::regclass
    ) THEN
        ALTER TABLE alerts DROP CONSTRAINT alerts_source_check;
    END IF;
END $$;

-- Add new constraint with 'workflow' instead of 'uipath'
ALTER TABLE alerts 
    ADD CONSTRAINT alerts_source_check 
    CHECK (source IN ('vm', 'server', 'workflow', 'monitor'));

-- Step 5: Verify the changes
-- Run these queries to verify:
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'vm_health' AND column_name LIKE '%workflow%';
-- SELECT DISTINCT source FROM alerts WHERE source = 'workflow';
-- SELECT COUNT(*) FROM alerts WHERE source = 'uipath'; -- Should return 0

-- Migration complete
-- All code references have been updated to use:
-- - workflow_status (database column)
-- - workflowStatus (API field name)
-- - vmsWithWorkflowRunning/vmsWithWorkflowStopped (statistics fields)
-- - 'workflow' (alert source value)
