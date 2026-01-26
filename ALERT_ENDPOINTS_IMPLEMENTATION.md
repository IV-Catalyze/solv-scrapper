# Alert Endpoints Implementation Summary

## Overview
This document summarizes the implementation of the alert endpoints for the monitoring and alerting system.

## Implementation Date
January 2025

## Endpoints Implemented

### 1. POST `/alerts`
**Purpose:** Submit an alert from VM, server, or monitoring system

**Features:**
- Validates source (vm, server, uipath, monitor)
- Validates severity (critical, warning, info)
- Stores alert in database
- Optionally sends notifications (email/Slack)
- Returns alert ID and creation timestamp

**Request Body:**
```json
{
  "source": "vm",
  "sourceId": "server1-vm1",
  "severity": "critical",
  "message": "UiPath process stopped unexpectedly",
  "details": {
    "errorCode": "PROCESS_NOT_FOUND",
    "lastKnownStatus": "running"
  }
}
```

**Response:**
```json
{
  "alertId": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "notificationSent": true,
  "createdAt": "2025-01-22T10:30:00Z"
}
```

---

### 2. GET `/alerts`
**Purpose:** Retrieve alerts with filtering and pagination

**Query Parameters:**
- `source` (optional): Filter by source
- `sourceId` (optional): Filter by specific source ID
- `severity` (optional): Filter by severity
- `resolved` (optional): Include resolved alerts (default: false)
- `limit` (optional): Number of alerts (default: 50, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "alerts": [
    {
      "alertId": "550e8400-e29b-41d4-a716-446655440000",
      "source": "vm",
      "sourceId": "server1-vm1",
      "severity": "critical",
      "message": "UiPath process stopped unexpectedly",
      "details": {...},
      "resolved": false,
      "resolvedAt": null,
      "createdAt": "2025-01-22T10:30:00Z"
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

---

### 3. PATCH `/alerts/{alertId}/resolve`
**Purpose:** Mark an alert as resolved

**Path Parameters:**
- `alertId` (required): Alert UUID

**Response:**
```json
{
  "alertId": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "resolvedAt": "2025-01-22T10:35:00Z"
}
```

---

## Files Created/Modified

### New Files
1. **`app/api/routes/alerts.py`**
   - Contains all three alert endpoints
   - Follows the same pattern as `vm_health.py`
   - Includes comprehensive error handling

2. **`app/utils/notifications.py`**
   - Optional notification service
   - Supports email (SMTP) and Slack webhooks
   - Non-blocking (failures don't prevent alert creation)

3. **`test_alerts.py`**
   - Comprehensive test script for all endpoints
   - Tests success cases, validation, and error handling

### Modified Files
1. **`app/database/schema.sql`**
   - Added `alerts` table with all required columns
   - Added indexes for performance
   - Added check constraints for source and severity
   - Added trigger for `updated_at` auto-update

2. **`app/api/models.py`**
   - Added `AlertRequest` model
   - Added `AlertResponse` model
   - Added `AlertItem` model
   - Added `AlertListResponse` model
   - Added `AlertResolveResponse` model
   - All models use camelCase field names with `populate_by_name = True`

3. **`app/api/database.py`**
   - Added `save_alert()` function
   - Added `get_alerts()` function with filtering and pagination
   - Added `resolve_alert()` function
   - Added `Tuple` and `timezone` imports

4. **`app/api/routes/__init__.py`**
   - Registered alerts router

5. **`app/api/routes.py`**
   - Registered alerts router in main app

6. **`app/api/routes/dependencies.py`**
   - Added alert model imports
   - Added alert database function imports
   - Updated `__all__` exports

---

## Database Schema

### Alerts Table
```sql
CREATE TABLE alerts (
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
```

### Indexes
- `idx_alerts_source` on (source, source_id)
- `idx_alerts_severity` on (severity)
- `idx_alerts_resolved` on (resolved)
- `idx_alerts_created_at` on (created_at DESC)
- `idx_alerts_source_severity` on (source, severity, resolved)

---

## Notification Configuration

### Email Notifications
Set these environment variables to enable email notifications:
```bash
ALERT_EMAIL_ENABLED=true
ALERT_EMAIL_SMTP_HOST=smtp.gmail.com
ALERT_EMAIL_SMTP_PORT=587
ALERT_EMAIL_SMTP_USER=alerts@example.com
ALERT_EMAIL_SMTP_PASSWORD=password
ALERT_EMAIL_RECIPIENTS=admin@example.com,ops@example.com
ALERT_EMAIL_FROM=alerts@example.com
```

### Slack Notifications
Set these environment variables to enable Slack notifications:
```bash
ALERT_SLACK_ENABLED=true
ALERT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
ALERT_SLACK_CHANNEL=#alerts
```

**Note:** Notifications are optional. If not configured or if sending fails, alerts are still created successfully.

---

## Testing

### Running Tests
```bash
# Set API URL (default: http://localhost:8000)
export API_URL=http://localhost:8000

# Optional: Set API token if authentication is required
export API_TOKEN=your-token-here

# Run tests
python3 test_alerts.py
```

### Test Coverage
The test script covers:
- ✅ Creating alerts (success cases)
- ✅ Creating alerts with invalid data (validation)
- ✅ Listing alerts with various filters
- ✅ Pagination
- ✅ Resolving alerts
- ✅ Error handling (non-existent alerts, invalid UUIDs)

---

## Authentication

All endpoints require authentication:
- POST `/alerts`: Uses `get_auth_dependency()` (HMAC or token-based)
- GET `/alerts`: Uses `require_auth()` (session-based)
- PATCH `/alerts/{alertId}/resolve`: Uses `require_auth()` (session-based)

---

## Error Handling

All endpoints include comprehensive error handling:
- **400 Bad Request**: Invalid request data, missing fields, invalid enum values
- **401 Unauthorized**: Authentication required
- **404 Not Found**: Alert not found (for resolve endpoint)
- **500 Internal Server Error**: Database errors, unexpected exceptions

---

## Design Decisions

1. **Followed Existing Patterns**: Implementation follows the same structure as `vm_health.py` for consistency
2. **camelCase API, snake_case DB**: API uses camelCase field names, database uses snake_case
3. **UUID Primary Key**: Uses UUID for `alert_id` for better distribution
4. **JSONB for Details**: Flexible details field using JSONB
5. **Soft Delete**: Uses `resolved` flag instead of hard deletion
6. **Non-blocking Notifications**: Notification failures don't prevent alert creation
7. **Pagination**: Standard limit/offset pagination
8. **Comprehensive Validation**: Both Pydantic and custom validation

---

## Next Steps

1. **Run Database Migration**: Apply the schema changes to your database
   ```bash
   psql -d your_database -f app/database/schema.sql
   ```

2. **Test Endpoints**: Run the test script to verify everything works
   ```bash
   python3 test_alerts.py
   ```

3. **Configure Notifications** (Optional): Set up email or Slack notifications if desired

4. **Integration**: Integrate alert creation into your monitoring systems (VMs, servers, etc.)

---

## Notes

- All endpoints are fully documented with OpenAPI/Swagger
- The implementation is production-ready and follows best practices
- Error messages are descriptive and helpful for debugging
- The code is well-structured and maintainable
