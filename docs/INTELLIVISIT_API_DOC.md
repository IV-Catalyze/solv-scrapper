# Intellivisit Patient Queue API

## Integration Guide - Solv Health x Intellivisit

Practical guide for the Intellivisit engineering team to connect with and consume the Solv Health Patient Queue API. The API provides real-time access to patient queue data.

---

## Base URLs

| Environment        | Base URL                                   | Description                                     |
|--------------------|---------------------------------------------|-------------------------------------------------|
| Production | `https://app-97926.on-aptible.com/`       | Production deployment for all integrations. |
| Interactive docs   | `https://app-97926.on-aptible.com/docs`    | Swagger UI for live exploration and testing.    |

---

## Authentication

**All API endpoints require HMAC signature authentication.** The API uses HMAC-SHA256 signatures to authenticate each request, providing request-level security without requiring token management.

### HMAC Signature Authentication

HMAC (Hash-based Message Authentication Code) authentication requires each request to include two headers:
- `X-Timestamp`: ISO 8601 UTC timestamp (e.g., `2025-11-21T13:49:04Z`)
- `X-Signature`: Base64-encoded HMAC-SHA256 signature

### How HMAC Authentication Works

**Step 1: Generate the signature**

The signature is computed over a canonical string containing:
```
METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH
```

Where:
- `METHOD`: HTTP method in uppercase (e.g., `GET`, `POST`)
- `PATH`: Request path including query string (e.g., `/summary?emr_id=123`)
- `TIMESTAMP`: ISO 8601 UTC timestamp (e.g., `2025-11-21T13:49:04Z`)
- `BODY_HASH`: SHA256 hash of the request body (hex format, empty string for GET requests)

**Step 2: Compute HMAC signature**

```python
import hmac
import hashlib
import base64
from datetime import datetime, timezone

# Get current UTC timestamp
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Hash the request body (empty for GET requests)
body_str = json.dumps(request_body) if request_body else ""
body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()

# Create canonical string
canonical = f"{METHOD}\n{PATH}\n{timestamp}\n{body_hash}"

# Generate HMAC signature
signature = hmac.new(
    secret_key.encode('utf-8'),
    canonical.encode('utf-8'),
    hashlib.sha256
).digest()

# Base64 encode the signature
signature_b64 = base64.b64encode(signature).decode('utf-8')
```

**Step 3: Include headers in request**

```bash
curl -X POST "https://app-97926.on-aptible.com/summary" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: 2025-11-21T13:49:04Z" \
  -H "X-Signature: abc123xyz789..." \
  -d '{
    "emr_id": "EMR12345",
    "note": "Patient summary text..."
  }'
```

### Example: Complete Request

**POST /summary with HMAC authentication:**

```bash
# Python example
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone

# Configuration
SECRET_KEY = "your-hmac-secret-key"
API_URL = "https://app-97926.on-aptible.com/summary"

# Request data
method = "POST"
path = "/summary"
body = {
    "emr_id": "EMR12345",
    "note": "Patient summary text..."
}

# Generate timestamp
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Hash body
body_str = json.dumps(body)
body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()

# Create canonical string
canonical = f"{method}\n{path}\n{timestamp}\n{body_hash}"

# Generate signature
signature = base64.b64encode(
    hmac.new(
        SECRET_KEY.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
).decode('utf-8')

# Make request
response = requests.post(
    API_URL,
    headers={
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Signature": signature
    },
    json=body
)
```

**GET /summary with query parameters:**

```bash
# For GET requests with query parameters, include them in the path
method = "GET"
path = "/summary?emr_id=EMR12345"
body_str = ""  # Empty for GET requests
body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()

# Rest of the process is the same...
```

### Security Features

- **Timestamp validation**: Requests must be within ±5 minutes of server time (prevents replay attacks)
- **Request integrity**: Any change to method, path, timestamp, or body invalidates the signature
- **Constant-time comparison**: Server uses constant-time comparison to prevent timing attacks
- **No token management**: Each request is independently authenticated; no tokens to store or refresh

### Secret Key Management

- **Secret keys** are provided by Solv during onboarding
- **Storage**: Store secret keys securely using environment variables or secret management systems
- **Never commit** secret keys to version control
- **Contact**: `integrations@solvhealth.com` to obtain your HMAC secret key

### Error Responses

| HTTP Code | Error | Resolution |
|-----------|-------|------------|
| `401 Unauthorized` | Missing HMAC headers | Provide both `X-Timestamp` and `X-Signature` headers |
| `401 Unauthorized` | Invalid HMAC signature | Verify signature computation matches server expectations |
| `401 Unauthorized` | Timestamp expired or invalid | Ensure timestamp is within ±5 minutes of server time |
| `401 Unauthorized` | Invalid secret key | Verify you're using the correct secret key for your environment |

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
| GET    | `/`                   | Render the patient dashboard HTML (visual inspection)    | No            |
| GET    | `/patients`           | Retrieve the active patient queue for a location         | Yes (HMAC)    |
| GET    | `/patient/{emr_id}`   | Retrieve the most recent record for a specific EMR ID    | Yes (HMAC)    |
| POST   | `/encounter`          | Create or update an encounter record                     | Yes (HMAC)    |
| POST   | `/summary`            | Create a summary record for a patient                   | Yes (HMAC)    |
| GET    | `/summary`            | Retrieve summary record by EMR ID                        | Yes (HMAC)    |

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

**With HMAC authentication:**
```bash
# Note: You need to generate the HMAC signature first (see authentication section)
curl -s \
  -H "X-Timestamp: 2025-11-21T13:49:04Z" \
  -H "X-Signature: YOUR_SIGNATURE_HERE" \
  "https://app-97926.on-aptible.com/patients?locationId=AXjwbE&statuses=confirmed&statuses=checked_in&limit=25" \
  | jq
```

### Example response

```json
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
| `401 Unauthorized`    | Authentication required                      | Provide valid HMAC signature headers (`X-Timestamp` and `X-Signature`).        |
| `400 Bad Request`     | Missing or invalid `locationId` or statuses  | Ensure a valid `locationId` and at least one valid status.  |
| `403 Forbidden`       | Client not permitted to access this location | Verify your client has access to the requested location.    |
| `500 Internal Server Error` | Unexpected server or database error    | Retry with exponential backoff; contact Solv if persistent. |

---

## 2. GET /patient/{emr_id}

Retrieve the latest record for a specific EMR (Electronic Medical Record) ID.

### Path parameter

| Name     | Type   | Required | Description                         |
|----------|--------|----------|-------------------------------------|
| `emr_id` | string | Yes      | EMR ID assigned to the patient.     |

### Example request

**With HMAC authentication:**
```bash
# Note: You need to generate the HMAC signature first (see authentication section)
curl -s \
  -H "X-Timestamp: 2025-11-21T13:49:04Z" \
  -H "X-Signature: YOUR_SIGNATURE_HERE" \
  "https://app-97926.on-aptible.com/patient/EMR12345" \
  | jq
```

### Example response

```json
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

### Field Name Support

The endpoint **supports both camelCase and snake_case** field names. You can send either format and the API will handle conversion automatically:

- `encounterId` or `encounter_id` → stored as `encounter_id`
- `patientId` or `patient_id` → stored as `patient_id`
- `clientId` or `client_id` → stored as `client_id`
- `emrId` or `emr_id` → stored as `emr_id`
- `traumaType` or `trauma_type` → stored as `trauma_type`
- `chiefComplaints` or `chief_complaints` → stored as `chief_complaints`
- `createdBy` or `created_by` → stored as `created_by`
- `startedAt` or `started_at` → stored as `started_at`

### Authentication

Provide HMAC signature authentication headers:
- `X-Timestamp`: ISO 8601 UTC timestamp
- `X-Signature`: Base64-encoded HMAC-SHA256 signature

See the [Authentication](#authentication) section above for detailed instructions on generating HMAC signatures.

#### Client IDs by environment

When creating encounters, include the appropriate `clientId` in your request payload:

| Environment | Client ID | Allowed locations |
|-------------|-----------|-------------------|
| Staging | `Stage-1c3dca8d-730f-4a32-9221-4e4277903505` | Demo location only |
| Production | `Prod-1f190fe5-d799-4786-bce2-37c3ad2c1561` | All locations |

- The `clientId` in your request payload should match the client associated with your HMAC secret key.
- Staging clients are restricted to the demo location (`AXjwbE`).
- Production clients can access all locations but must still provide a valid `locationId` in requests.

### Request body schema

| Field             | Type        | Required | Description |
|-------------------|-------------|----------|-------------|
| `id` or `encounter_id` | string (UUID) | Yes | Unique identifier for the encounter. |
| `clientId` or `client_id` | string | Yes | Customer/client identifier supplied by Solv (may include prefix like 'Stage-' or 'Prod-'). |
| `patientId` or `patient_id` | string (UUID) | Yes | Identifier for the patient. |
| `encounterId` or `encounter_id` | string (UUID) | Yes | Encounter identifier; used for idempotent updates. |
| `emrId` or `emr_id` | string | No | EMR identifier for the patient (links encounter to patient EMR record). |
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

**Additional Fields**: You can include any additional fields in your request body (e.g., `attributes`, `orders`, `accessLogs`, `predictedDiagnoses`, `additionalQuestions`, etc.). These will be preserved in the stored payload.

### Example request (camelCase format)

```bash
curl -X POST "https://app-97926.on-aptible.com/encounter" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: 2025-11-21T13:49:04Z" \
  -H "X-Signature: YOUR_SIGNATURE_HERE" \
  -d '{
    "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "clientId": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
    "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "emrId": "EMR12345",
    "traumaType": "BURN",
    "chiefComplaints": [
      {
        "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
        "description": "Chemical burn on left arm",
        "type": "trauma",
        "part": "arm",
        "bodyParts": ["left arm", "forearm"]
      }
    ],
    "status": "COMPLETE",
    "createdBy": "user@example.com",
    "startedAt": "2025-11-12T22:19:01.432Z"
  }'
```

### Example request (snake_case format)

```bash
curl -X POST "https://app-97926.on-aptible.com/encounter" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: 2025-11-21T13:49:04Z" \
  -H "X-Signature: YOUR_SIGNATURE_HERE" \
  -d '{
    "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
    "patient_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
    "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
    "emr_id": "EMR12345",
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
    "created_by": "user@example.com",
    "started_at": "2025-11-12T22:19:01.432Z"
  }'
```

### Example response (201 Created)

The response always uses snake_case field names regardless of input format:

```json
{
  "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
  "client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
  "patient_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
  "emr_id": "EMR12345",
  "trauma_type": "BURN",
  "chief_complaints": [
    {
      "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
      "description": "Chemical burn on left arm",
      "type": "trauma",
      "part": "arm",
      "bodyParts": ["left arm", "forearm"]
    }
  ],
  "status": "COMPLETE",
  "created_by": "user@example.com",
  "started_at": "2025-11-12T22:19:01.432Z",
  "created_at": "2025-11-12T22:19:05.123Z",
  "updated_at": "2025-11-12T22:19:05.123Z"
}
```

### Error responses

| HTTP code | Message | Notes |
|-----------|---------|-------|
| `400 Bad Request` | Missing required fields (`patientId`/`patient_id`, `clientId`/`client_id`, `encounterId`/`encounter_id`) or empty `chiefComplaints`/`chief_complaints` list | Ensure all required fields are present and at least one complaint is provided. Field names can be either camelCase or snake_case. |
| `401 Unauthorized` | Authentication required | Provide valid HMAC signature headers (`X-Timestamp` and `X-Signature`). |
| `403 Forbidden` | Client ID in payload does not match authenticated client | Ensure the `clientId` in your payload matches the client associated with your HMAC secret key. |
| `404 Not Found` | Patient or related record not found (rare) | Confirm identifiers exist in your tenant. |
| `500 Internal Server Error` | Database or server error | Retry with backoff; contact Solv if persistent. |

---

## 4. GET /

Render the internal Solv dashboard HTML view. This is primarily for quality assurance or visual verification.

Example:

```bash
open "https://app-97926.on-aptible.com/?locationId=AXjwbE&statuses=confirmed&limit=25"
```

The response is an HTML table view of the patient queue.

---

## Interactive API Documentation

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
| `403 Forbidden`                | Client not permitted to access location | Verify your client has access to the requested location.     |

---

## Support Contacts

| Type            | Contact                         |
|-----------------|---------------------------------|
| Primary email   | integrations@solvhealth.com     |
| Slack channel   | #intellivisit-solv-integration  |
| Support hours   | 08:00-18:00 CT, Monday-Friday   |

When submitting an incident include the full request URL, timestamp (UTC), response body or error message, and any `x-request-id` header values if available.
