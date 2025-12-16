# Phase 2: n8n Orchestration & Management - Workflow Summary

## Workflow Overview

This n8n workflow implements Phase 2 of the system, handling orchestration and management of queue tasks between Phase 1 (Patient Data Ingestion) and Phase 3 (VM Worker Processing).

## Workflow Components

### 1. Heartbeat Monitor (Every 30 seconds)
**Purpose**: Monitor VM worker health by checking for stuck PROCESSING tasks

**Flow**:
- Schedule Trigger (30s) → Check Processing Tasks → Filter Stuck Tasks → Recover Stuck Task

**Logic**:
- Gets all tasks with status `PROCESSING`
- Filters tasks that haven't been updated in 2+ minutes
- Resets stuck tasks back to `PENDING` for retry

### 2. ACK Handler (Webhook)
**Purpose**: Process successful task completions from VM workers

**Webhook Path**: `/ack`

**Expected Payload**:
```json
{
  "queue_id": "uuid",
  "encounter_id": "uuid",
  "experityActions": {...}
}
```

**Flow**:
- ACK Webhook → Extract ACK Data → Get Queue Entry → Update Queue: DONE → ACK Response

**Actions**:
- Updates queue status to `DONE`
- Stores experity actions in parsed_payload
- Sends success response to VM worker

### 3. FAIL Handler (Webhook)
**Purpose**: Process failed task completions from VM workers

**Webhook Path**: `/fail`

**Expected Payload**:
```json
{
  "queue_id": "uuid",
  "encounter_id": "uuid",
  "error_message": "Error description"
}
```

**Flow**:
- FAIL Webhook → Extract FAIL Data → Get Queue Entry → Check Retry Limit
  - **If attempts < max**: Update Queue: ERROR (increment attempts) → Requeue Task → FAIL Response
  - **If attempts >= max**: Move to Dead Letter Queue → FAIL Response

**Actions**:
- Updates queue status to `ERROR`
- Checks retry limit (default: 3 attempts)
- Either requeues with HIGH priority or moves to DLQ

### 4. VT Sweep (Every 5 minutes)
**Purpose**: Recover tasks stuck in PROCESSING state

**Flow**:
- VT Sweep Schedule (5 min) → Get Stuck Tasks → Filter Stuck by Time → Recover (VT Sweep)

**Logic**:
- Gets all tasks with status `PROCESSING`
- Filters tasks stuck for >10 minutes
- Resets to `PENDING` with recovery message

### 5. SLA Prom (Every 15 minutes)
**Purpose**: Escalate old PENDING tasks that exceed SLA threshold

**Flow**:
- SLA Prom Schedule (15 min) → Get Old PENDING Tasks → Filter Old Tasks → Escalate (SLA Prom)

**Logic**:
- Gets all tasks with status `PENDING`
- Filters tasks older than 30 minutes (SLA threshold)
- Escalates to HIGH priority

## Queue Status Transitions

```
PENDING → PROCESSING → DONE ✅
                ↓
              ERROR → (attempts < max?) → PENDING (HIGH priority) → PROCESSING
                ↓
              ERROR → (attempts >= max?) → DLQ ❌
```

## Configuration

### Environment Variables
- `API_BASE_URL`: Base URL of the API (e.g., `https://app-97926.on-aptible.com`)
- `HMAC_SECRET`: Secret key for HMAC authentication
- `MAX_RETRY_ATTEMPTS`: Maximum retry attempts before DLQ (default: 3)

### Authentication
- All API requests use HMAC-SHA256 authentication
- Headers: `X-Timestamp`, `X-Signature`

## Required API Endpoints

The workflow requires these endpoints (some need to be created):

1. **GET /queue** ✅ (exists)
   - Query params: `status`, `queue_id`, `encounter_id`, `limit`

2. **PATCH /queue/{queue_id}/status** ❌ (needs to be created)
   - Update queue status, increment attempts, store error messages

3. **PATCH /queue/{queue_id}/requeue** ❌ (needs to be created)
   - Requeue task with updated priority

## Priority Levels

- **HIGH**: Requeued tasks, SLA violations, escalated tasks
- **NORMAL**: Regular tasks (default)
- **LOW**: (Future use)

## Dead Letter Queue (DLQ)

Tasks are moved to DLQ when:
- Maximum retry attempts exceeded
- Manual review required
- Root cause investigation needed

DLQ tasks are marked with:
- Status: `ERROR`
- `dlq: true` flag in parsed_payload
- Error message: "Max retry attempts exceeded. Moved to Dead Letter Queue."

## Monitoring Points

Monitor these metrics:
1. **ACK/FAIL Processing Rate**: Webhook response times and success rates
2. **Queue Status Distribution**: Count of tasks in each status
3. **VT Sweep Recovery Rate**: Number of stuck tasks recovered
4. **SLA Prom Escalation Rate**: Number of tasks escalated
5. **DLQ Size**: Number of tasks requiring manual review
6. **Retry Rate**: Percentage of tasks that require retries

## Error Handling

- All HTTP requests include error handling
- Failed API calls are logged
- Webhook responses always return success/failure status
- Stuck tasks are automatically recovered

## Integration Points

### With Phase 1 (Patient Data Ingestion)
- Receives queue entries created by `POST /queue` endpoint
- Monitors and manages these entries

### With Phase 3 (VM Worker Processing)
- Receives ACK/FAIL webhooks from VM workers
- Provides queue status updates via API
- Handles retry logic and DLQ management

## Next Steps

1. **Create Required Endpoints**: Implement PATCH endpoints for queue status updates
2. **Add Priority Field**: Add priority column to queue table if not exists
3. **Configure VM Workers**: Update VM workers to send ACK/FAIL to n8n webhooks
4. **Set Up Monitoring**: Configure alerts and dashboards
5. **Test End-to-End**: Validate complete flow from Phase 1 → Phase 2 → Phase 3

## Troubleshooting

### Webhook Not Receiving Requests
- Verify n8n webhook URL is accessible
- Check webhook path matches VM worker configuration
- Ensure workflow is active in n8n

### Status Updates Failing
- Verify API endpoints exist and are accessible
- Check HMAC authentication configuration
- Verify API_BASE_URL is correct

### Tasks Stuck in PROCESSING
- Check VT Sweep is running (every 5 minutes)
- Verify heartbeat threshold settings
- Check VM workers are sending heartbeats

### High DLQ Rate
- Investigate root causes of failures
- Review error messages in DLQ tasks
- Consider adjusting MAX_RETRY_ATTEMPTS
- Check VM worker health and logs

