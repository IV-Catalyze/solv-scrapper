-- Migration: Create server_health table
-- Date: 2025-01-22
-- Purpose: Support server-level heartbeat tracking with resource metrics

-- Create server_health table
CREATE TABLE IF NOT EXISTS server_health (
    server_id VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) DEFAULT 'healthy' CHECK (status IN ('healthy', 'unhealthy', 'down')),
    last_heartbeat TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for server_health table
CREATE INDEX IF NOT EXISTS idx_server_health_status ON server_health(status);
CREATE INDEX IF NOT EXISTS idx_server_health_last_heartbeat ON server_health(last_heartbeat);

-- Add trigger to automatically update updated_at for server_health
DROP TRIGGER IF EXISTS update_server_health_updated_at ON server_health;
CREATE TRIGGER update_server_health_updated_at
    BEFORE UPDATE ON server_health
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
