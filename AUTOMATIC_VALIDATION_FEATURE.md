# Automatic Validation Feature - High-Level Documentation

## Overview

The automatic validation feature automatically validates queue entries when they are marked as "DONE". It compares the data extracted from HPI (History of Present Illness) screenshots against the JSON data stored in the queue entry's `experityAction`.

## When Validation Triggers

Validation runs automatically in the background when:

1. **Queue status becomes "DONE"** via:
   - `PATCH /queue/{queue_id}/status` with `status: "DONE"`
   - Note: `POST /experity/map` endpoint no longer automatically sets status to DONE - it stores experity_actions but keeps status as PROCESSING

2. **AND** the queue entry has `experityAction` in its `parsed_payload`

3. **AND** an HPI image exists in Azure Blob Storage for that encounter

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Queue Entry Status → DONE                                    │
│    (via PATCH /queue/{id}/status or POST /experity/map)        │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. System Checks:                                               │
│    • Does experityAction exist in parsed_payload?              │
│    • Does encounter_id exist?                                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼ (if yes)
┌─────────────────────────────────────────────────────────────────┐
│ 3. Background Task Triggered                                    │
│    (runs asynchronously, doesn't block API response)           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Find HPI Image                                               │
│    • Search Azure Blob Storage                                  │
│    • Look in: encounters/{encounter_id}/                        │
│    • Find first image with "hpi" in filename (case-insensitive)│
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Download HPI Image                                           │
│    • Download image bytes from Azure Blob Storage               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Run Validation via Azure AI                                  │
│    • Use Azure AI ImageMapper agent                             │
│    • Send: HPI image + experityAction JSON                      │
│    • Agent compares image content vs JSON data                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Get Validation Results                                       │
│    • Overall status: PASS, PARTIAL, FAIL, or ERROR             │
│    • Field-by-field comparison (Main Problem, Body Area, etc.) │
│    • Match/Mismatch indicators                                  │
│    • List of any mismatches found                               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. Save Results to Database                                     │
│    • Store in queue_validations table                           │
│    • Upsert: Update if exists, Insert if new                    │
│    • Links to queue_id and encounter_id                         │
└─────────────────────────────────────────────────────────────────┘
```

## What Gets Validated

The system validates the following fields from the `experityAction` JSON against what's extracted from the HPI screenshot:

- **Main Problem** - The primary complaint/problem
- **Body Area** - The body area/part affected
- **Notes** - Additional notes/text
- **Quality** - Quality descriptors (e.g., "sharp pain", "dull ache")
- **Severity** - Severity level/numeric value

For each field, the system:
- Compares JSON value vs Screenshot value
- Determines if they MATCH or MISMATCH
- Flags any discrepancies

## Where Results Are Stored

Validation results are stored in the `queue_validations` table:

```sql
queue_validations
├── validation_id (UUID, primary key)
├── queue_id (UUID, foreign key → queue.queue_id, unique)
├── encounter_id (UUID)
├── validation_result (JSONB) - Contains:
│   ├── overall_status (PASS/PARTIAL/FAIL/ERROR)
│   ├── results (field-by-field comparison)
│   ├── mismatches (array of mismatch descriptions)
│   └── error (if validation failed)
├── created_at (timestamp)
└── updated_at (timestamp, auto-updated)
```

## How to View Validation Results

### Via UI (Web Interface)

1. Navigate to `/queue/list` page
2. Find the queue entry with status "DONE"
3. Click **"View Verification"** button
4. Modal opens showing:
   - Overall status badge (color-coded)
   - Field-by-field comparison results
   - Match/Mismatch indicators
   - Any mismatches found

### Via API

```
GET /queue/{queue_id}/validation

Response:
{
  "validation_result": {
    "overall_status": "PASS",
    "results": {
      "main_problem": {
        "match": true,
        "json": "Cough",
        "screenshot": "Cough"
      },
      "body_area": {
        "match": true,
        "json": "Chest",
        "screenshot": "Chest"
      },
      ...
    },
    "mismatches": []
  },
  "experity_action": {...},
  "encounter_id": "uuid"
}
```

## Important Notes

### Background Processing
- Validation runs asynchronously in the background
- The API response returns immediately (doesn't wait for validation)
- Validation typically takes 10-30 seconds to complete
- Check application logs to monitor validation progress

### Error Handling
If validation fails at any step:
- Error is logged with details
- Validation result is saved with `overall_status: "ERROR"`
- Error message is stored in `validation_result.error`
- The queue entry status is NOT affected (remains "DONE")

### Common Failure Reasons
- **No HPI image found**: Image doesn't exist or doesn't contain "hpi" in filename
- **Image download failed**: Azure Blob Storage connection issue
- **Azure AI error**: Agent timeout, network issue, or parsing error
- **Missing experityAction**: Validation won't trigger if experityAction doesn't exist

### Manual Trigger
To manually trigger validation for an existing entry:
```bash
# Update status to DONE (will trigger validation if experityAction exists)
PATCH /queue/{queue_id}/status
{
  "status": "DONE"
}
```

Or use the provided script:
```bash
python3 trigger_validation.py {queue_id}
```

## Architecture Components

1. **Background Tasks** - FastAPI `BackgroundTasks` for async processing
2. **Azure Blob Storage** - Stores HPI images for encounters
3. **Azure AI ImageMapper Agent** - Performs the validation comparison
4. **PostgreSQL** - Stores validation results in `queue_validations` table
5. **FastAPI Endpoints** - Trigger validation and retrieve results

## Status Codes

- **PASS** - All fields match correctly
- **PARTIAL** - Some fields match, some don't
- **FAIL** - Fields don't match (validation failed)
- **ERROR** - Validation process encountered an error

## Related Endpoints

- `PATCH /queue/{queue_id}/status` - Updates queue status (triggers validation if DONE)
- `POST /experity/map` - Maps encounter to experityActions (triggers validation)
- `GET /queue/{queue_id}/validation` - Retrieves validation results
- `GET /queue/list` - Lists queue entries with validation status (UI)

## Database Schema

The validation system uses the `queue_validations` table which:
- Has a one-to-one relationship with `queue` table (unique `queue_id`)
- Automatically updates `updated_at` timestamp on changes
- Uses JSONB for flexible storage of validation results
- Cascades deletion when queue entry is deleted

