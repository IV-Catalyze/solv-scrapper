# Phase 2: n8n Orchestration & Management - Setup Guide

This guide explains how to set up and configure the n8n workflow for Phase 2 of the system.

## Overview

The Phase 2 n8n workflow handles:
- **Heartbeat Monitoring**: Tracks VM worker health every 30 seconds
- **ACK/FAIL Handlers**: Webhook endpoints to receive results from VM workers
- **Queue Management**: Updates queue status (DONE, ERROR), handles retries, and manages Dead Letter Queue
- **VT Sweep**: Recovers stuck tasks (PROCESSING for >10 minutes)
- **SLA Prom**: Escalates old tasks (PENDING for >30 minutes)

## Required API Endpoints

The n8n workflow requires the following API endpoints. **Some of these need to be created** as they don't currently exist:

### Existing Endpoints (Already Available)
- `GET /queue` - List queue entries with filters
- `POST /queue` - Update queue experityAction (but not status)

### Required New Endpoints (Need to be Created)

#### 1. PATCH /queue/{queue_id}/status
Update queue entry status and optionally increment attempts.

**Request:**
```json
PATCH /queue/{queue_id}/status
{
  "status": "DONE" | "ERROR" | "PENDING" | "PROCESSING",
  "error_message": "Optional error message",
  "increment_attempts": true | false,
  "experity_actions": {...} // Optional, for DONE status
}
```

**Response:**
```json
{
  "queue_id": "uuid",
  "status": "DONE",
  "attempts": 1,
  "updated_at": "2025-01-21T10:30:00Z"
}
```

#### 2. PATCH /queue/{queue_id}/requeue
Requeue a task with updated priority.

**Request:**
```json
PATCH /queue/{queue_id}/requeue
{
  "status": "PENDING",
  "priority": "HIGH" | "NORMAL" | "LOW",
  "error_message": "Optional message"
}
```

**Response:**
```json
{
  "queue_id": "uuid",
  "status": "PENDING",
  "priority": "HIGH",
  "attempts": 2,
  "updated_at": "2025-01-21T10:30:00Z"
}
```

## n8n Workflow Configuration

### Environment Variables

Set these in your n8n environment:

```bash
API_BASE_URL=https://app-97926.on-aptible.com
HMAC_SECRET=your-hmac-secret-key
MAX_RETRY_ATTEMPTS=3
```

### Authentication Setup

1. Create an HMAC Authentication credential in n8n:
   - **Type**: HMAC Authentication
   - **Algorithm**: SHA256
   - **Secret Key**: Your HMAC secret
   - **Header Name**: X-Signature
   - **Timestamp Header**: X-Timestamp

### Workflow Components

#### 1. Heartbeat Monitor (Every 30s)
- **Trigger**: Schedule (30 seconds)
- **Action**: Check PROCESSING tasks for stuck workers
- **Logic**: If task hasn't been updated in 2+ minutes, reset to PENDING

#### 2. ACK Webhook Handler
- **Path**: `/ack`
- **Expected Payload**:
  ```json
  {
    "queue_id": "uuid",
    "encounter_id": "uuid",
    "experityActions": {...}
  }
  ```
- **Action**: Update queue status to DONE

#### 3. FAIL Webhook Handler
- **Path**: `/fail`
- **Expected Payload**:
  ```json
  {
    "queue_id": "uuid",
    "encounter_id": "uuid",
    "error_message": "Error description"
  }
  ```
- **Action**: 
  - Update status to ERROR
  - Check if attempts < MAX_RETRY_ATTEMPTS
  - If yes: Requeue with HIGH priority
  - If no: Move to Dead Letter Queue

#### 4. VT Sweep (Every 5 minutes)
- **Trigger**: Schedule (5 minutes)
- **Action**: Find PROCESSING tasks stuck for >10 minutes
- **Recovery**: Reset to PENDING status

#### 5. SLA Prom (Every 15 minutes)
- **Trigger**: Schedule (15 minutes)
- **Action**: Find PENDING tasks older than 30 minutes
- **Escalation**: Set priority to HIGH

## Importing the Workflow

1. Open n8n
2. Click "Import from File"
3. Select `n8n_phase2_workflow.json`
4. Configure environment variables
5. Set up HMAC authentication credentials
6. Activate the workflow

## Testing the Workflow

### Test ACK Handler
```bash
curl -X POST http://your-n8n-instance/webhook/ack \
  -H "Content-Type: application/json" \
  -d '{
    "queue_id": "test-queue-id",
    "encounter_id": "test-encounter-id",
    "experityActions": {"vitals": {}}
  }'
```

### Test FAIL Handler
```bash
curl -X POST http://your-n8n-instance/webhook/fail \
  -H "Content-Type: application/json" \
  -d '{
    "queue_id": "test-queue-id",
    "encounter_id": "test-encounter-id",
    "error_message": "Test error"
  }'
```

## Queue Status Flow

```
PENDING → PROCESSING → DONE ✅
                ↓
              ERROR → (attempts < max?) → PENDING (HIGH priority)
                ↓
              ERROR → (attempts >= max?) → DLQ ❌
```

## Priority Levels

- **HIGH**: Requeued tasks, SLA violations
- **NORMAL**: Regular tasks
- **LOW**: (Future use)

## Dead Letter Queue (DLQ)

Tasks moved to DLQ:
- Have exceeded MAX_RETRY_ATTEMPTS
- Require manual review
- Should be investigated for root cause

## Monitoring

Monitor these metrics:
- ACK/FAIL webhook response times
- Number of tasks in each status
- VT Sweep recovery rate
- SLA Prom escalation rate
- DLQ size

## Troubleshooting

### Webhook not receiving requests
- Check n8n webhook URL is accessible
- Verify webhook path matches VM worker configuration
- Check n8n workflow is active

### Status updates failing
- Verify API endpoints are created
- Check HMAC authentication is configured correctly
- Verify API_BASE_URL is correct

### Tasks stuck in PROCESSING
- Check VT Sweep is running (every 5 minutes)
- Verify heartbeat threshold (2 minutes for heartbeat monitor, 10 minutes for VT Sweep)
- Check VM workers are sending heartbeats

## Next Steps

1. **Create Required API Endpoints**: Implement PATCH endpoints for queue status updates
2. **Add Priority Field**: Add priority column to queue table if not exists
3. **Configure VM Workers**: Update VM workers to send ACK/FAIL to n8n webhooks
4. **Set Up Monitoring**: Configure alerts for DLQ, stuck tasks, and SLA violations
5. **Test End-to-End**: Test complete flow from Phase 1 → Phase 2 → Phase 3

