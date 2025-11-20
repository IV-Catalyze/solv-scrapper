# Intellivisit Patient Queue API

## Integration Guide - Solv Health x Intellivisit

Practical guide for the Intellivisit engineering team to connect with and consume the Solv Health Patient Queue API hosted on Aptible. The API mirrors the Solv dashboard dataset so Intellivisit can retrieve and synchronize patient data in near real time.

---

## Base URLs

| Environment        | Base URL                                   | Description                                     |
|--------------------|---------------------------------------------|-------------------------------------------------|
| Staging / Production | `https://app-97926.on-aptible.com/`       | Aptible-hosted deployment for all integrations. |
| Interactive docs   | `https://app-97926.on-aptible.com/docs`    | Swagger UI for live exploration and testing.    |

---

## Authentication

**All API endpoints require authentication.** The API supports two authentication methods:

### 1. JWT Bearer Token (Recommended)

JWT tokens provide secure, time-limited access with automatic expiration.

**Step 1: Generate an access token**

```bash
curl -X POST "https://app-97926.on-aptible.com/auth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
    "expires_hours": 24
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_at": "2024-11-07T14:22:03.000Z",
  "expires_in": 86400,
  "client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"
}
```

**Step 2: Use the token in API requests**

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  "https://app-97926.on-aptible.com/patients?locationId=AXjwbE"
```

### 2. API Key (Alternative)

For simpler integrations, you can use a static API key provided by Solv.

```bash
curl -H "X-API-Key: your-api-key-here" \
  "https://app-97926.on-aptible.com/patients?locationId=AXjwbE"
```

**Note:** API keys are provided by Solv during onboarding. Contact `integrations@solvhealth.com` to obtain your API key.

### Token Management

- **Token expiration**: Default tokens expire after 24 hours. You can request custom expiration times (1 hour to 1 year).
- **Token refresh**: Generate a new token before expiration using the `/auth/token` endpoint.
- **Security**: Store tokens securely and never commit them to version control. Use environment variables or secret management systems.
- **Best practice**: Implement token refresh logic in your integration to automatically renew tokens before expiration.

### Error Responses

| HTTP Code | Error | Resolution |
|-----------|-------|------------|
| `401 Unauthorized` | Missing or invalid token/API key | Verify your Authorization header or X-API-Key header |
| `401 Unauthorized` | Token expired | Generate a new token using `/auth/token` |

---

## Conventions

- **Content type**: `application/json`
- **Date and time fields**: ISO 8601 (UTC)
- **Status filters**: Case-insensitive strings
- **Parameter naming**: Camel case query parameters (for example `locationId`)
- **Pagination**: Not cursor-based; use the `limit` query parameter
- **Rate limit**: Soft limit of five requests per second

---

## Endpoints Overview

| Method | Path                  | Description                                              | Auth Required |
|--------|-----------------------|----------------------------------------------------------|---------------|
| POST   | `/auth/token`         | Generate JWT access token                                | No            |
| GET    | `/`                   | Render the patient dashboard HTML (visual inspection)    | No            |
| GET    | `/patients`           | Retrieve the active patient queue for a location         | Yes           |
| GET    | `/patient/{emr_id}`   | Retrieve the most recent record for a specific EMR ID    | Yes           |
| POST   | `/encounter`          | Create or update an encounter record                     | Yes           |

Full interactive documentation: `https://app-97926.on-aptible.com/docs`

---

## 1. GET /patients

Retrieve the active patient queue for a specific clinic location.

### Query parameters

| Name        | Type     | Required | Description                                                                 |
|-------------|----------|----------|-----------------------------------------------------------------------------|
| `locationId`| string   | Yes      | Solv location identifier (for example `AXjwbE`).                            |
| `statuses`  | string[] | No       | One or more patient statuses (for example `confirmed`, `checked_in`). Defaults to `["checked_in", "confirmed"]`. |
| `limit`     | integer  | No       | Maximum number of records to return (sorted by `captured_at` descending, then `updated_at`). |

### Example request

**With Bearer token:**
```
curl -s \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  "https://app-97926.on-aptible.com/patients?locationId=AXjwbE&statuses=confirmed&statuses=checked_in&limit=25" \
  | jq
```

**With API key:**
```
curl -s \
  -H "X-API-Key: YOUR_API_KEY_HERE" \
  "https://app-97926.on-aptible.com/patients?locationId=AXjwbE&statuses=confirmed&statuses=checked_in&limit=25" \
  | jq
```

### Example response

```
[
  {
    "emr_id": "EMR12345",
    "location_id": "AXjwbE",
    "status": "confirmed",
    "status_label": "Confirmed",
    "captured_at": "2024-11-06T14:22:03.000Z",
    "captured_display": "Nov 6, 2024 2:22 PM",
    "reasonForVisit": "Telehealth follow-up",
    "appointment_date": "2024-11-06",
    "appointment_date_at_clinic_tz": "2024-11-06T08:22:03-06:00",
    "calendar_date": "2024-11-06",
    "legalFirstName": "John",
    "legalLastName": "Doe",
    "mobilePhone": "+15551234567"
  }
]
```

### Error responses

| HTTP code             | Message                                      | Notes                                                       |
|-----------------------|----------------------------------------------|-------------------------------------------------------------|
| `401 Unauthorized`    | Authentication required                      | Provide a valid Bearer token or API key in headers.        |
| `400 Bad Request`     | Missing or invalid `locationId` or statuses  | Ensure a valid `locationId` and at least one valid status.  |
| `500 Internal Server Error` | Unexpected server or database error    | Retry with exponential backoff; contact Solv if persistent. |

---

## 2. GET /patient/{emr_id}

Retrieve the latest record for a specific EMR (Electronic Medical Record) ID.

### Path parameter

| Name     | Type   | Required | Description                         |
|----------|--------|----------|-------------------------------------|
| `emr_id` | string | Yes      | EMR ID assigned to the patient.     |

### Example request

**With Bearer token:**
```
curl -s \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  "https://app-97926.on-aptible.com/patient/EMR12345" \
  | jq
```

**With API key:**
```
curl -s \
  -H "X-API-Key: YOUR_API_KEY_HERE" \
  "https://app-97926.on-aptible.com/patient/EMR12345" \
  | jq
```

### Example response

```
{
  "emr_id": "EMR12345",
  "location_id": "AXjwbE",
  "status": "checked_in",
  "status_label": "Checked In",
  "legalFirstName": "Jane",
  "legalLastName": "Smith",
  "dob": "1989-02-17",
  "mobilePhone": "+15557654321",
  "reasonForVisit": "Annual checkup",
  "captured_at": "2024-11-06T14:22:03Z",
  "captured_display": "Nov 6, 2024 2:22 PM"
}
```

### Error responses

| HTTP code             | Reason                                   |
|-----------------------|------------------------------------------|
| `401 Unauthorized`    | Authentication required                  |
| `404 Not Found`       | No record found for the supplied EMR ID. |
| `500 Internal Server Error` | Database or internal error.       |

---

## 3. POST /encounter

Create or update an encounter record for a patient. If an encounter with the same `encounterId` already exists it will be updated in place (idempotent upsert).

### Data Storage

The API stores encounter data in three forms for maximum flexibility:

1. **Individual columns**: Core fields (encounter_id, patient_id, client_id, etc.) are stored in indexed columns for fast queries
2. **raw_payload**: The complete original JSON request body is preserved exactly as received (JSONB)
3. **parsed_payload**: A normalized, simplified structure (snake_case format) optimized for queue processing and UI consumption (JSONB)

This dual-payload approach ensures:
- **Audit trail**: `raw_payload` preserves the exact original request for debugging and compliance
- **Processing efficiency**: `parsed_payload` provides a standardized format for queue processing and UI rendering
- **Query performance**: Individual columns remain indexed for fast filtering and sorting

### Field Name Support

The endpoint **supports both camelCase and snake_case** field names. You can send either format and the API will handle conversion automatically:

- `encounterId` or `encounter_id` → stored as `encounter_id`
- `patientId` or `patient_id` → stored as `patient_id`
- `clientId` or `client_id` → stored as `client_id`
- `traumaType` or `trauma_type` → stored as `trauma_type`
- `chiefComplaints` or `chief_complaints` → stored as `chief_complaints`
- `createdBy` or `created_by` → stored as `created_by`
- `startedAt` or `started_at` → stored as `started_at`

### Authentication

Provide either:
- `Authorization: Bearer <token>` header (recommended), or
- `X-API-Key: <api-key>`

#### Client IDs by environment

| Environment | Client ID | Allowed locations |
|-------------|-----------|-------------------|
| Staging | `Stage-1c3dca8d-730f-4a32-9221-4e4277903505` | `Exer Urgent Care - Demo (AXjwbE)` only |
| Production | `Prod-1f190fe5-d799-4786-bce2-37c3ad2c1561` | All locations listed in `app/utils/locations.py` |

- Tokens are issued only for the client IDs above. Supplying an unknown ID to `/auth/token` returns `403`.
- Staging tokens automatically default to the demo location; supplying a different `locationId` will be rejected.
- Production tokens must still include a valid `locationId`, but every entry from `LOCATION_MAP` is permitted.

### Request body schema

| Field             | Type        | Required | Description |
|-------------------|-------------|----------|-------------|
| `id` or `encounter_id` | string (UUID) | Yes | Unique identifier for the encounter. |
| `clientId` or `client_id` | string (UUID) | Yes | Customer/client identifier supplied by Solv. |
| `patientId` or `patient_id` | string (UUID) | Yes | Identifier for the patient. |
| `encounterId` or `encounter_id` | string (UUID) | Yes | Encounter identifier; used for idempotent updates. |
| `traumaType` or `trauma_type` | string | No | Type of trauma (e.g. `BURN`, `FALL`, `CUT`). |
| `chiefComplaints` or `chief_complaints` | array | Yes | At least one complaint object is required. |
| `chiefComplaints[].id` | string (UUID) | Yes | Unique identifier for the complaint. |
| `chiefComplaints[].description` | string | Yes | Human-readable description of the complaint. |
| `chiefComplaints[].type` | string | Yes | Complaint type (e.g. `trauma`). |
| `chiefComplaints[].part` | string | Yes | Body part affected. |
| `chiefComplaints[].bodyParts` or `chiefComplaints[].body_parts` | array | No | Optional list of detailed body-part strings. |
| `status` | string | No | Encounter status (`COMPLETE`, `IN_PROGRESS`, `PENDING`, etc.). |
| `createdBy` or `created_by` | string | No | Email or identifier of the user/system that created the encounter. |
| `startedAt` or `started_at` | string (ISO 8601) | No | When the encounter began (UTC). |
| `createdAt` or `created_at` | string (ISO 8601) | No | Auto-generated if not provided. |
| `updatedAt` or `updated_at` | string (ISO 8601) | No | Auto-generated if not provided. |

**Additional Fields**: You can include any additional fields in your request body (e.g., `attributes`, `orders`, `accessLogs`, `predictedDiagnoses`, `additionalQuestions`, etc.). These will be:
- ✅ **Preserved in `raw_payload`**: All extra fields are stored exactly as received in the `raw_payload` JSONB column
- ❌ **Not in `parsed_payload`**: Only standardized fields appear in the simplified `parsed_payload`
- ❌ **Not in individual columns**: Only core indexed fields are stored as individual columns

This allows you to send full encounter objects with all metadata while maintaining a clean, standardized structure for queue processing and UI rendering.

### Example request (camelCase format)

```
curl -X POST "https://app-97926.on-aptible.com/encounter" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "traumaType": "BURN",
    "chiefComplaints": [
      {
        "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
        "description": "Chemical burn on left arm",
        "type": "trauma",
        "part": "arm",
        "bodyParts": ["left arm", "forearm"]
      },
      {
        "id": "726c47ab-a7d9-4836-a7a0-b5e99fc13ac7",
        "description": "Second degree burn",
        "type": "trauma",
        "part": "arm",
        "bodyParts": ["left arm"]
      }
    ],
    "status": "COMPLETE",
    "createdBy": "randall.meeker@intellivisit.com",
    "startedAt": "2025-11-12T22:19:01.432Z"
  }'
```

### Example request (complex payload with extra fields)

The endpoint accepts complex payloads with additional fields beyond the core schema. All extra fields are preserved in `raw_payload`:

```
curl -X POST "https://app-97926.on-aptible.com/encounter" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "traumaType": "BURN",
    "status": "COMPLETE",
    "createdBy": "randall.meeker@intellivisit.com",
    "startedAt": "2025-11-12T22:19:01.432Z",
    "chiefComplaints": [
      {
        "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
        "description": "Injury Head",
        "type": "trauma",
        "part": "head",
        "bodyParts": []
      }
    ],
    "attributes": {
      "gender": "male",
      "pulseOx": 99,
      "ageYears": 69,
      "heightCm": 167.64,
      "weightKg": 63.5,
      "pulseRateBpm": 20,
      "bodyTemperatureCelsius": 37
    },
    "orders": [
      {
        "id": "b577ff78-96e5-448f-a614-f99f0f8e7d23",
        "type": "clinical",
        "label": "Notify Provider",
        "performed": true
      }
    ],
    "predictedDiagnoses": [
      {
        "id": "03703469-e4f4-4eb4-9fd7-44c7734c5230",
        "name": "cerebral hemorrhage",
        "probability": 1
      }
    ],
    "additionalQuestions": {
      "conditions": [
        {"name": "history of anxiety", "answer": false}
      ]
    },
    "accessLogs": [...],
    "predictedProcedures": ["Emergency physical exam", "Head CT"],
    "source": "CONCIERGE",
    "esi": 2
  }'
```

All extra fields (attributes, orders, predictedDiagnoses, etc.) will be preserved in `raw_payload` but only standardized fields appear in `parsed_payload` and individual columns.

### Example request (snake_case format)

```
curl -X POST "https://app-97926.on-aptible.com/encounter" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "client_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "patient_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "trauma_type": "BURN",
    "chief_complaints": [
      {
        "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
        "description": "Injury Head",
        "type": "trauma",
        "part": "head",
        "bodyParts": []
      }
    ],
    "status": "COMPLETE",
    "created_by": "randall.meeker@intellivisit.com",
    "started_at": "2025-11-12T22:19:01.432Z"
  }'
```

### Example response (201 Created)

The response always uses snake_case field names regardless of input format:

```
{
  "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "client_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "patient_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "trauma_type": "BURN",
  "chief_complaints": [
    {
      "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
      "description": "Chemical burn on left arm",
      "type": "trauma",
      "part": "arm",
      "bodyParts": ["left arm", "forearm"]
    },
    {
      "id": "726c47ab-a7d9-4836-a7a0-b5e99fc13ac7",
      "description": "Second degree burn",
      "type": "trauma",
      "part": "arm",
      "bodyParts": ["left arm"]
    }
  ],
  "status": "COMPLETE",
  "created_by": "randall.meeker@intellivisit.com",
  "started_at": "2025-11-12T22:19:01.432Z",
  "created_at": "2025-11-12T22:19:05.123Z",
  "updated_at": "2025-11-12T22:19:05.123Z"
}
```

### Database Storage Details

When an encounter is created or updated, the following data structures are stored:

**Individual columns** (for indexed queries):
- `id`, `encounter_id`, `client_id`, `patient_id`
- `trauma_type`, `status`, `created_by`
- `chief_complaints` (as JSONB array)
- `started_at`, `created_at`, `updated_at`

**raw_payload** (JSONB - original request preserved):
```json
{
  "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "traumaType": "BURN",
  "chiefComplaints": [...],
  "status": "COMPLETE",
  "createdBy": "randall.meeker@intellivisit.com",
  "startedAt": "2025-11-12T22:19:01.432Z"
}
```

**parsed_payload** (JSONB - normalized structure):
```json
{
  "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "client_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "patient_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "trauma_type": "BURN",
  "chief_complaints": [...],
  "status": "COMPLETE",
  "created_by": "randall.meeker@intellivisit.com",
  "started_at": "2025-11-12T22:19:01.432Z",
  "created_at": "2025-11-12T22:19:01.432Z",
  "updated_at": "2025-11-12T22:19:01.432Z"
}
```

### Error responses

| HTTP code | Message | Notes |
|-----------|---------|-------|
| `400 Bad Request` | Missing required fields (`patientId`/`patient_id`, `clientId`/`client_id`, `encounterId`/`encounter_id`) or empty `chiefComplaints`/`chief_complaints` list | Ensure all required fields are present and at least one complaint is provided. Field names can be either camelCase or snake_case. |
| `401 Unauthorized` | Authentication required | Provide a valid Bearer token or API key. |
| `404 Not Found` | Patient or related record not found (rare) | Confirm identifiers exist in your tenant. |
| `409 Conflict` | Duplicate `encounterId`/`encounter_id` with conflicting identifiers | Ensure `encounterId` uniquely identifies the encounter for the same patient/client combination. |
| `500 Internal Server Error` | Database or server error | Retry with backoff; contact Solv if persistent. |

---

## 4. GET /

Render the internal Solv dashboard HTML view. This is primarily for quality assurance or visual verification.

Example:

```
open "https://app-97926.on-aptible.com/?locationId=AXjwbE&statuses=confirmed&limit=25"
```

The response is an HTML table view of the patient queue.

---

## 4. Interactive API Documentation

- Swagger UI: `https://app-97926.on-aptible.com/docs`
- Alternate read-only reference: `https://app-97926.on-aptible.com/redoc`

Within Swagger UI you can:

- View endpoint definitions and schema examples.
- Execute live requests with custom parameters.
- Inspect HTTP responses and headers.
- Export generated `curl` commands for automation.

---

## Patient Payload Schema

| Field                               | Type              | Description                                           |
|-------------------------------------|-------------------|-------------------------------------------------------|
| `emr_id`                            | string            | Unique EMR identifier.                                |
| `booking_id`                        | string            | Internal booking reference.                           |
| `patient_number`                    | string            | Clinic-specific patient number.                       |
| `location_id`                       | string            | Clinic location identifier.                           |
| `location_name`                     | string            | Clinic name, if available.                            |
| `legalFirstName`, `legalLastName`   | string            | Patient name fields.                                  |
| `dob`                               | string (ISO date) | Date of birth.                                        |
| `mobilePhone`                       | string            | Contact number.                                       |
| `sexAtBirth`                        | string            | Gender marker on file.                                |
| `reasonForVisit`                    | string            | Visit description.                                    |
| `status`                            | string            | Queue status (for example `confirmed`, `checked_in`).  |
| `status_label`                      | string            | Human-readable version of status.                     |
| `status_class`                      | string            | Lowercase version for UI styling.                     |
| `captured_at`                       | string (ISO datetime) | When the record was captured.                      |
| `captured_display`                  | string            | Formatted display timestamp.                          |
| `appointment_date`                  | string (ISO date) | Scheduled appointment date.                           |
| `appointment_date_at_clinic_tz`     | string            | Localized appointment timestamp.                      |
| `calendar_date`                     | string (ISO date) | Date associated with the visit.                       |
| `created_at`, `updated_at`          | string            | Timestamps from the source system.                    |

Additional fields may appear as the upstream data model evolves. Integrations should ignore unrecognized keys.

---

## Operational Guidelines

- **Retry policy**: Use exponential backoff (for example 1s, 2s, 4s) on transient `500` errors.
- **Monitoring**: Capture `status`, `location_id`, and `emr_id` in your logs for troubleshooting.
- **Data freshness**: Responses represent live operational data; there is no caching layer in front of the API.
- **Change management**: Solv announces schema or behavior changes via the shared Slack channel at least two weeks before deployment.

---

## Troubleshooting

| Issue                          | Possible cause                         | Resolution                                                    |
|--------------------------------|-----------------------------------------|---------------------------------------------------------------|
| Empty response                 | Invalid or missing `locationId`.        | Verify the `locationId` parameter and supplied statuses.      |
| `500 Internal Server Error`    | Database connection issue.              | Retry with backoff; escalate to Solv Integration Team.        |
| Dashboard HTML empty           | No patients matching supplied status.   | Retry with broader statuses such as `confirmed` or `checked_in`. |

---

## Support Contacts

| Type            | Contact                         |
|-----------------|---------------------------------|
| Primary email   | integrations@solvhealth.com     |
| Slack channel   | #intellivisit-solv-integration  |
| Support hours   | 08:00-18:00 CT, Monday-Friday   |

When submitting an incident include the full request URL, timestamp (UTC), response body or error message, and any `x-request-id` header values if available.



