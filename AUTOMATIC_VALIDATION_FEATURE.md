# Automatic Validation Feature - High-Level Documentation

## Overview

The automatic validation feature automatically validates queue entries when they are marked as "DONE". It compares the data extracted from HPI (History of Present Illness) screenshots against the JSON data stored in the queue entry's `experityAction`.

**Important:** The system now validates each complaint separately. Each complaint has its own HPI image (named `{complaint_id}_hpi.{ext}`) and its own validation result.

## When Validation Triggers

Validation runs automatically in the background when:

1. **Queue status becomes "DONE"** via:
   - `PATCH /queue/{queue_id}/status` with `status: "DONE"`
   - Note: `POST /experity/map` endpoint no longer automatically sets status to DONE - it stores experity_actions but keeps status as PROCESSING

2. **AND** the queue entry has `experityAction` in its `parsed_payload`

3. **AND** HPI images exist in Azure Blob Storage for the complaints (format: `{complaint_id}_hpi.{ext}`)

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
│ 4. Extract Complaints from experityAction                      │
│    • Get complaints array from experityAction.complaints[]      │
│    • Each complaint must have a complaintId                     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. For Each Complaint:                                          │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ 5a. Find HPI Image                                      │ │
│    │    • Search: encounters/{encounter_id}/                │ │
│    │    • Pattern: {complaint_id}_hpi.{ext}                  │ │
│    │    • Supports: .png, .jpg, .jpeg, .gif, .webp          │ │
│    └──────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ 5b. Download HPI Image                                  │ │
│    │    • Download image bytes from Azure Blob Storage        │ │
│    └──────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ 5c. Run Validation via Azure AI                         │ │
│    │    • Use Azure AI ImageMapper agent                     │ │
│    │    • Send: HPI image + complaint JSON                   │ │
│    │    • Agent compares image content vs complaint data     │ │
│    └──────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ 5d. Get Validation Results                               │ │
│    │    • Overall status: PASS, PARTIAL, FAIL, or ERROR     │ │
│    │    • Field-by-field comparison                          │ │
│    │    • Match/Mismatch indicators                          │ │
│    └──────────────────────┬──────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│    ┌─────────────────────────────────────────────────────────┐ │
│    │ 5e. Save Result to Database                            │ │
│    │    • Store in queue_validations table                   │ │
│    │    • Upsert: Update if exists, Insert if new            │ │
│    │    • Links to queue_id, encounter_id, and complaint_id  │ │
│    └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## What Gets Validated

The system validates each complaint separately. For each complaint, it validates the following fields from the complaint object against what's extracted from that complaint's HPI screenshot:

- **Main Problem** - The primary complaint/problem
- **Body Area** - The body area/part affected
- **Notes** - Additional notes/text
- **Quality** - Quality descriptors (e.g., "sharp pain", "dull ache")
- **Severity** - Severity level/numeric value

For each field, the system:
- Compares JSON value vs Screenshot value
- Determines if they MATCH or MISMATCH
- Flags any discrepancies

**Note:** Each complaint is validated independently. A queue entry with 3 complaints will have 3 separate validation results.

## Where Results Are Stored

Validation results are stored in the `queue_validations` table. **Multiple validations can exist per queue** (one per complaint):

```sql
queue_validations
├── validation_id (UUID, primary key)
├── queue_id (UUID, foreign key → queue.queue_id)
├── encounter_id (UUID)
├── complaint_id (UUID, nullable) - Links to specific complaint
├── validation_result (JSONB) - Contains:
│   ├── overall_status (PASS/PARTIAL/FAIL/ERROR)
│   ├── results (field-by-field comparison)
│   ├── mismatches (array of mismatch descriptions)
│   └── error (if validation failed)
├── created_at (timestamp)
└── updated_at (timestamp, auto-updated)

Unique constraint: (queue_id, complaint_id)
```

**Important:** The unique constraint is on `(queue_id, complaint_id)`, allowing multiple validations per queue (one per complaint).

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
  "validations": [
    {
      "complaint_id": "00f9612e-f37d-451b-9172-25cbddee58a9",
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
      "hpi_image_path": "encounters/{encounter_id}/{complaint_id}_hpi.png"
    },
    {
      "complaint_id": "another-complaint-uuid",
      "validation_result": {...},
      "hpi_image_path": "..."
    }
  ],
  "experity_action": {...},
  "encounter_id": "uuid"
}
```

**Note:** The response now returns an array of validations (one per complaint) instead of a single validation result.

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
- **No HPI image found**: Image doesn't exist or doesn't match expected format `{complaint_id}_hpi.{ext}`
- **Missing complaintId**: Complaint doesn't have a complaintId (required for finding the correct HPI image)
- **Image download failed**: Azure Blob Storage connection issue
- **Azure AI error**: Agent timeout, network issue, or parsing error
- **Missing experityAction**: Validation won't trigger if experityAction doesn't exist
- **No complaints**: experityAction exists but has no complaints array

### HPI Image Naming Convention

HPI images must be named using the format: `{complaint_id}_hpi.{ext}`

- **Location**: `encounters/{encounter_id}/{complaint_id}_hpi.{ext}`
- **Supported formats**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
- **Example**: `encounters/abc-123/00f9612e-f37d-451b-9172-25cbddee58a9_hpi.png`

**Important:** Each complaint must have its own HPI image file. The system searches for images matching the complaint's `complaintId`.

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
- Has a one-to-many relationship with `queue` table (multiple validations per queue)
- Unique constraint on `(queue_id, complaint_id)` - allows one validation per complaint
- Automatically updates `updated_at` timestamp on changes
- Uses JSONB for flexible storage of validation results
- Cascades deletion when queue entry is deleted
- `complaint_id` is required for all new validations (guaranteed by `azure_ai_agent_client.py`)

## Migration Notes

If you're upgrading from the old single-validation system:

1. **Database Migration**: Run the schema update to add `complaint_id` column and update the unique constraint
2. **Image Naming**: Rename existing HPI images to use the format `{complaint_id}_hpi.{ext}`
3. **API Changes**: The `GET /queue/{queue_id}/validation` endpoint now returns an array of validations instead of a single result
4. **Important**: All new validations will have `complaint_id` (guaranteed by `azure_ai_agent_client.py`). The system expects `complaint_id` to always be present.

