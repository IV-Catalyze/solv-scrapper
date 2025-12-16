# New Queue Endpoints Summary

## Overview

Two new PATCH endpoints have been created to support Phase 2 n8n orchestration workflow:

1. **PATCH /queue/{queue_id}/status** - Update queue entry status
2. **PATCH /queue/{queue_id}/requeue** - Requeue a queue entry with updated priority

## Endpoint Details

### 1. PATCH /queue/{queue_id}/status

**Purpose**: Update a queue entry's status, optionally increment attempts, and store error messages or experity actions.

**Path Parameters**:
- `queue_id` (UUID, required): Queue identifier

**Request Body**:
```json
{
  "status": "DONE" | "ERROR" | "PENDING" | "PROCESSING",
  "error_message": "Optional error message (for ERROR status)",
  "increment_attempts": true | false,
  "experityActions": {...} | [...],  // Optional, for DONE status
  "dlq": true | false  // Optional, mark for Dead Letter Queue
}
```

**Response**: `QueueResponse` with updated queue entry

**Example Request**:
```bash
PATCH /queue/660e8400-e29b-41d4-a716-446655440000/status
{
  "status": "DONE",
  "experityActions": {
    "vitals": {},
    "complaints": []
  }
}
```

**Example Request (Error)**:
```bash
PATCH /queue/660e8400-e29b-41d4-a716-446655440000/status
{
  "status": "ERROR",
  "error_message": "Processing failed",
  "increment_attempts": true,
  "dlq": false
}
```

**Features**:
- Validates status values (PENDING, PROCESSING, DONE, ERROR)
- Optionally increments attempts counter
- Stores error messages in parsed_payload for ERROR status
- Stores experity actions (dict or list) for DONE status
- Supports DLQ flag for Dead Letter Queue marking
- Uses existing `update_queue_status_and_experity_action` function

### 2. PATCH /queue/{queue_id}/requeue

**Purpose**: Requeue a queue entry with updated priority. Automatically increments attempts counter.

**Path Parameters**:
- `queue_id` (UUID, required): Queue identifier

**Request Body**:
```json
{
  "status": "PENDING" | "PROCESSING" | "DONE" | "ERROR",  // Optional, default: PENDING
  "priority": "HIGH" | "NORMAL" | "LOW",  // Optional, default: HIGH
  "error_message": "Optional error message"
}
```

**Response**: `QueueResponse` with updated queue entry

**Example Request**:
```bash
PATCH /queue/660e8400-e29b-41d4-a716-446655440000/requeue
{
  "status": "PENDING",
  "priority": "HIGH",
  "error_message": "Requeued for retry"
}
```

**Features**:
- Validates status and priority values
- Automatically increments attempts counter
- Stores priority in parsed_payload (since queue table doesn't have priority column)
- Stores requeue message in parsed_payload
- Default status: PENDING
- Default priority: HIGH

## Request Models

### QueueStatusUpdateRequest
```python
class QueueStatusUpdateRequest(BaseModel):
    status: str  # Required: PENDING, PROCESSING, DONE, or ERROR
    error_message: Optional[str] = None
    increment_attempts: Optional[bool] = False
    experity_actions: Optional[Dict[str, Any]] = None  # Alias: experityActions
    dlq: Optional[bool] = None
```

### QueueRequeueRequest
```python
class QueueRequeueRequest(BaseModel):
    status: Optional[str] = "PENDING"
    priority: Optional[str] = "HIGH"  # HIGH, NORMAL, or LOW
    error_message: Optional[str] = None
```

## Authentication

Both endpoints require HMAC authentication (same as all other endpoints):
- `X-Timestamp`: ISO 8601 UTC timestamp
- `X-Signature`: Base64-encoded HMAC-SHA256 signature

## Error Responses

- `400 Bad Request`: Invalid request data, invalid status/priority values, or missing queue_id
- `401 Unauthorized`: Authentication required
- `404 Not Found`: Queue entry not found
- `500 Internal Server Error`: Database or server error

## Integration with n8n Workflow

These endpoints are designed to work with the Phase 2 n8n workflow:

1. **ACK Handler**: Uses `PATCH /queue/{queue_id}/status` with status="DONE" and experityActions
2. **FAIL Handler**: Uses `PATCH /queue/{queue_id}/status` with status="ERROR", increment_attempts=true
3. **Requeue Logic**: Uses `PATCH /queue/{queue_id}/requeue` with priority="HIGH" for retries
4. **DLQ Logic**: Uses `PATCH /queue/{queue_id}/status` with status="ERROR" and dlq=true

## Database Schema Notes

- **Priority**: Stored in `parsed_payload` JSONB field (no dedicated column)
- **DLQ Flag**: Stored in `parsed_payload` JSONB field as `dlq: true`
- **Error Messages**: Stored in `parsed_payload` JSONB field as `error_message`
- **Attempts**: Stored in dedicated `attempts` INTEGER column (auto-incremented)

## Testing

Test the endpoints using curl or Postman:

```bash
# Update status to DONE
curl -X PATCH "https://app-97926.on-aptible.com/queue/{queue_id}/status" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -H "X-Signature: <hmac-signature>" \
  -d '{
    "status": "DONE",
    "experityActions": {"vitals": {}}
  }'

# Requeue with HIGH priority
curl -X PATCH "https://app-97926.on-aptible.com/queue/{queue_id}/requeue" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -H "X-Signature: <hmac-signature>" \
  -d '{
    "priority": "HIGH",
    "error_message": "Requeued for retry"
  }'
```

## Files Modified

- `app/api/routes.py`:
  - Added `QueueStatusUpdateRequest` model (line ~1559)
  - Added `QueueRequeueRequest` model (line ~1580)
  - Added `PATCH /queue/{queue_id}/status` endpoint (line ~2871)
  - Added `PATCH /queue/{queue_id}/requeue` endpoint (line ~3061)

## Next Steps

1. ✅ Endpoints created and integrated
2. Test endpoints with n8n workflow
3. Update API documentation
4. Monitor endpoint usage and performance

