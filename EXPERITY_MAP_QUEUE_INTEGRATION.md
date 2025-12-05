# Experity Map Endpoint - Queue Integration

## Overview

The `/experity/map` endpoint has been updated to work seamlessly with the new queue structure. It can now automatically fetch queue entries from the database, making it compatible with `GET /queue` responses.

## Changes Made

### 1. Updated Request Validation

**Before:**
- Required: `encounter_id` and `raw_payload`
- Optional: `queue_id`

**After:**
- Required: Either `encounter_id` OR `queue_id`
- Optional: `raw_payload` (will be fetched from database if not provided)

### 2. Automatic Database Fetching

The endpoint now automatically:
1. Fetches the queue entry from the database if `raw_payload` is not provided
2. Uses `raw_payload` from the database if available
3. Fills in missing `queue_id` or `encounter_id` from the database

### 3. Compatibility with GET /queue

Since `GET /queue` returns:
```json
{
  "emrId": "EMR12345",
  "status": "PENDING",
  "attempts": 0,
  "encounterPayload": {...}  // camelCase
}
```

The `/experity/map` endpoint can now work with:
- **Option 1**: Provide only `encounter_id` (fetches `raw_payload` from DB)
- **Option 2**: Convert `encounterPayload` → `raw_payload` and provide both

## Usage Examples

### Example 1: Fetch from Database (Recommended)

```json
POST /experity/map
{
  "queue_entry": {
    "encounter_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

The endpoint will:
1. Find the queue entry by `encounter_id`
2. Extract `raw_payload` from the database
3. Use it for Azure AI processing

### Example 2: Provide raw_payload Directly

```json
POST /experity/map
{
  "queue_entry": {
    "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
    "raw_payload": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
      "traumaType": "BURN",
      "chiefComplaints": [...]
    }
  }
}
```

### Example 3: Using queue_id

```json
POST /experity/map
{
  "queue_entry": {
    "queue_id": "660e8400-e29b-41d4-a716-446655440000"
  }
}
```

## Integration with GET /queue

### Workflow 1: Direct Integration (Recommended)

```python
# Step 1: Get queue entry
response = GET /queue
queue_entry = response.json()[0]

# Step 2: Extract encounter_id from encounterPayload
encounter_id = queue_entry['encounterPayload']['id']

# Step 3: Call experity/map with just encounter_id
POST /experity/map
{
  "queue_entry": {
    "encounter_id": encounter_id
  }
}
```

### Workflow 2: Manual Conversion

```python
# Step 1: Get queue entry
response = GET /queue
queue_entry = response.json()[0]

# Step 2: Convert encounterPayload to raw_payload
raw_payload = queue_entry['encounterPayload']

# Step 3: Call experity/map with raw_payload
POST /experity/map
{
  "queue_entry": {
    "encounter_id": raw_payload['id'],
    "raw_payload": raw_payload
  }
}
```

## Benefits

1. **Simplified Integration**: No need to manually convert `encounterPayload` to `raw_payload`
2. **Database Consistency**: Always uses the latest `raw_payload` from the database
3. **Backward Compatible**: Still works with existing code that provides `raw_payload`
4. **Flexible**: Can use either `encounter_id` or `queue_id`

## Error Handling

The endpoint returns appropriate errors:
- `VALIDATION_ERROR`: Missing both `encounter_id` and `queue_id`
- `NOT_FOUND`: Queue entry not found in database
- `VALIDATION_ERROR`: `raw_payload` not found in database and not provided

## Testing

Validation tests confirm:
- ✅ Request with `encounter_id` and `raw_payload` works
- ✅ Request with `queue_id` only works (fetches from DB)
- ✅ Request with `encounter_id` only works (fetches from DB)
- ✅ Request with neither `encounter_id` nor `queue_id` is rejected

