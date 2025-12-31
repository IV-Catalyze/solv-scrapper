# Solv Health API - Complete Integration Guide

**Version:** 1.0  
**Last Updated:** November 2025  
**Base URL:** `https://app-97926.on-aptible.com`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [Base URL & Environment](#base-url--environment)
4. [API Endpoints](#api-endpoints)
   - [Patient Endpoints](#patient-endpoints)
   - [Encounter Endpoints](#encounter-endpoints)
   - [Queue Endpoints](#queue-endpoints)
   - [Summary Endpoints](#summary-endpoints)
   - [Experity Endpoints](#experity-endpoints)
5. [Request/Response Examples](#requestresponse-examples)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Code Examples](#code-examples)

---

## Quick Start

### 1. Get Your HMAC Secret Key

Contact your API administrator to receive your HMAC secret key. **Never commit this key to version control.**

### 2. Install Required Libraries

**Python:**
```bash
pip install requests
```

**Node.js:**
```bash
npm install axios crypto
```

### 3. Make Your First Request

See [Authentication](#authentication) section for HMAC signature generation, then use any endpoint below.

---

## Authentication

All API endpoints (except web UI endpoints) require **HMAC-SHA256 authentication**.

### Required Headers

Every API request must include:

- **`X-Timestamp`**: ISO 8601 UTC timestamp (e.g., `2025-11-21T13:49:04Z`)
- **`X-Signature`**: Base64-encoded HMAC-SHA256 signature
- **`Content-Type`**: `application/json` (for POST/PATCH requests)

### How HMAC Authentication Works

1. **Create canonical string:**
   ```
   METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH
   ```

2. **Hash request body** (SHA256, hex format):
   - For GET requests: use empty string `""`
   - For POST/PATCH: hash the JSON body exactly as sent

3. **Generate HMAC signature:**
   - Compute HMAC-SHA256 using your secret key
   - Base64 encode the result

### Quick Example

```python
import hmac
import hashlib
import base64
from datetime import datetime, timezone

# Configuration
SECRET_KEY = "your-secret-key-here"
METHOD = "POST"
PATH = "/patients/create"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
BODY = '{"emr_id":"EMR12345","status":"confirmed"}'

# Hash body
body_hash = hashlib.sha256(BODY.encode('utf-8')).hexdigest()

# Create canonical string
canonical = f"{METHOD}\n{PATH}\n{TIMESTAMP}\n{body_hash}"

# Generate signature
signature = base64.b64encode(
    hmac.new(SECRET_KEY.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).digest()
).decode('utf-8')

# Headers
headers = {
    "Content-Type": "application/json",
    "X-Timestamp": TIMESTAMP,
    "X-Signature": signature
}
```

**📖 For detailed HMAC implementation guide, see:** [`docs/HMAC_AUTHENTICATION_GUIDE.md`](./HMAC_AUTHENTICATION_GUIDE.md)

---

## Base URL & Environment

**Production Base URL:** `https://app-97926.on-aptible.com`

All endpoints are relative to this base URL. For example:
- Full URL for `/patients`: `https://app-97926.on-aptible.com/patients`

---

## API Endpoints

### Patient Endpoints

#### 1. List Patients

**`GET /patients`**

Retrieve a list of patients filtered by location and status.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `locationId` | string | Yes* | Location identifier to filter patients |
| `statuses` | string[] | No | Filter by status (repeatable). Default: `["confirmed", "checked_in", "pending"]` |
| `limit` | integer | No | Maximum number of records (≥ 1) |

*Required unless `DEFAULT_LOCATION_ID` environment variable is set.

**Example Request:**
```bash
GET /patients?locationId=AXjwbE&statuses=confirmed&statuses=checked_in&limit=50
```

**Response:** `200 OK`
```json
[
  {
    "emr_id": "EMR12345",
    "booking_id": "booking-123",
    "booking_number": "BK-001",
    "patient_number": "PN-456",
    "location_id": "AXjwbE",
    "location_name": "Demo Clinic",
    "legalFirstName": "John",
    "legalLastName": "Doe",
    "dob": "1990-01-15",
    "mobilePhone": "+1234567890",
    "sexAtBirth": "M",
    "status": "confirmed",
    "status_class": "confirmed",
    "status_label": "Confirmed",
    "reasonForVisit": "Annual checkup",
    "captured_at": "2025-11-21T10:30:00Z",
    "captured_display": "Nov 21, 2025 10:30 AM",
    "created_at": "2025-11-21T10:30:00Z",
    "updated_at": "2025-11-21T10:30:00Z"
  }
]
```

---

#### 2. Get Patient by EMR ID

**`GET /patient/{emr_id}`**

Retrieve the most recent patient record for a specific EMR ID.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `emr_id` | string | Yes | EMR identifier for the patient |

**Example Request:**
```bash
GET /patient/EMR12345
```

**Response:** `200 OK`
```json
{
  "emr_id": "EMR12345",
  "booking_id": "booking-123",
  "booking_number": "BK-001",
  "patient_number": "PN-456",
  "location_id": "AXjwbE",
  "location_name": "Demo Clinic",
  "legalFirstName": "John",
  "legalLastName": "Doe",
  "dob": "1990-01-15",
  "mobilePhone": "+1234567890",
  "sexAtBirth": "M",
  "status": "confirmed",
  "reasonForVisit": "Annual checkup",
  "captured_at": "2025-11-21T10:30:00Z",
  "created_at": "2025-11-21T10:30:00Z",
  "updated_at": "2025-11-21T10:30:00Z"
}
```

**Error Responses:**
- `404 Not Found`: Patient with the specified EMR ID not found

---

#### 3. Create Patient

**`POST /patients/create`**

Create a new patient record or update an existing one.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `emr_id` | string | Yes | EMR identifier for the patient |
| `location_id` | string | Yes* | Location identifier |
| `booking_id` | string | No | Internal booking identifier |
| `booking_number` | string | No | Human-readable booking number |
| `patient_number` | string | No | Clinic-specific patient number |
| `location_name` | string | No | Display name of the clinic location |
| `legalFirstName` | string | No | Patient legal first name |
| `legalLastName` | string | No | Patient legal last name |
| `dob` | string | No | Date of birth (ISO 8601 format) |
| `mobilePhone` | string | No | Primary phone number |
| `sexAtBirth` | string | No | Sex at birth or recorded gender marker |
| `reasonForVisit` | string | No | Reason provided for the visit |
| `status` | string | No | Current queue status |
| `captured_at` | string | No | Timestamp when record was captured (ISO 8601) |

*Required for new patients. For existing patients, location_id can be inferred from previous records.

**Example Request:**
```json
POST /patients/create
{
  "emr_id": "EMR12345",
  "location_id": "AXjwbE",
  "legalFirstName": "John",
  "legalLastName": "Doe",
  "dob": "1990-01-15",
  "mobilePhone": "+1234567890",
  "sexAtBirth": "M",
  "status": "confirmed",
  "reasonForVisit": "Annual checkup"
}
```

**Response:** `201 Created`
```json
{
  "message": "Patient record created successfully",
  "emr_id": "EMR12345",
  "status": "created",
  "inserted_count": 1
}
```

**Note:** If a patient with the same `emr_id` already exists, the record will be updated and the response will show `"status": "updated"`.

---

#### 4. Update Patient Status

**`PATCH /patients/{emr_id}`**

Update the queue status for a patient.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `emr_id` | string | Yes | EMR identifier for the patient |

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | New queue status (e.g., "confirmed", "checked_in", "pending") |

**Example Request:**
```json
PATCH /patients/EMR12345
{
  "status": "checked_in"
}
```

**Response:** `200 OK`
```json
{
  "message": "Patient status updated successfully",
  "emr_id": "EMR12345",
  "status": "checked_in"
}
```

**Error Responses:**
- `404 Not Found`: Patient with the specified EMR ID not found
- `400 Bad Request`: Invalid status value or missing status field

---

### Encounter Endpoints

#### 5. Create or Update Encounter

**`POST /encounter`**

Create a new encounter record or update an existing one.

**Request Body:**

**Required Fields:**
- `encounterId` or `encounter_id` (string, UUID): Encounter identifier - **REQUIRED**
- `emrId` or `emr_id` (string): EMR identifier for the patient - **REQUIRED**
- `chiefComplaints` or `chief_complaints` (array): List of chief complaint objects - **REQUIRED** (must be non-empty)

**Optional Fields:**
- `id` (string, UUID): Unique identifier (defaults to `encounterId` if not provided)
- `clientId` or `client_id` (string): Client identifier (optional if provided via HMAC auth)
- `traumaType` or `trauma_type` (string): Type of trauma (e.g., "BURN")
- `status` (string): Status of the encounter (e.g., "COMPLETE")
- `createdBy` or `created_by` (string): Email or identifier of the user who created the encounter
- `startedAt` or `started_at` (string): ISO 8601 timestamp when the encounter started

**Chief Complaints Structure:**
Each complaint object should contain:
- `mainProblem` (string): Main problem description
- `bodyParts` (array of strings, optional): List of affected body parts
- Other complaint-related fields as needed

**Field Name Conventions:**
The endpoint supports both camelCase (e.g., `encounterId`, `chiefComplaints`) and snake_case (e.g., `encounter_id`, `chief_complaints`).

**Example Request:**
```json
POST /encounter
{
  "encounterId": "550e8400-e29b-41d4-a716-446655440000",
  "emrId": "EMR12345",
  "chiefComplaints": [
    {
      "mainProblem": "Fever and cough",
      "bodyParts": ["chest", "throat"]
    }
  ],
  "traumaType": "BURN",
  "status": "COMPLETE",
  "startedAt": "2025-11-21T10:30:00Z"
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
  "emr_id": "EMR12345",
  "trauma_type": "BURN",
  "chief_complaints": [
    {
      "mainProblem": "Fever and cough",
      "bodyParts": ["chest", "throat"]
    }
  ],
  "status": "COMPLETE",
  "started_at": "2025-11-21T10:30:00Z",
  "created_at": "2025-11-21T10:30:00Z",
  "updated_at": "2025-11-21T10:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required fields or invalid data
- `401 Unauthorized`: Invalid HMAC signature

**Note:** If an encounter with the same `encounterId` already exists, it will be updated.

---

### Queue Endpoints

#### 6. List Queue Entries

**`GET /queue`**

Retrieve queue entries with optional filters.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `queue_id` | string (UUID) | No | Filter by queue identifier |
| `encounter_id` | string (UUID) | No | Filter by encounter identifier |
| `status` | string | No | Filter by status: `PENDING`, `PROCESSING`, `DONE`, or `ERROR` |
| `emr_id` | string | No | Filter by EMR identifier |
| `limit` | integer | No | Maximum number of records (≥ 1) |

**Example Request:**
```bash
GET /queue?status=PENDING&limit=10
```

**Response:** `200 OK`
```json
[
  {
    "queue_id": "660e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
    "emr_id": "EMR12345",
    "status": "PENDING",
    "raw_payload": {...},
    "parsed_payload": {
      "experityAction": []
    },
    "attempts": 0,
    "created_at": "2025-11-21T10:30:00Z",
    "updated_at": "2025-11-21T10:30:00Z"
  }
]
```

---

#### 7. Update Queue Experity Action

**`POST /queue`**

Update the `experityAction` field in a queue entry's `parsed_payload`.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `queue_id` | string (UUID) | No* | Queue identifier |
| `encounter_id` | string (UUID) | No* | Encounter identifier |
| `experityAction` | array | No | Array of Experity action objects |

*Either `queue_id` or `encounter_id` must be provided.

**Example Request:**
```json
POST /queue
{
  "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
  "experityAction": [
    {
      "action": "UPDATE_VITALS",
      "data": {
        "temperature": 98.6,
        "bloodPressure": "120/80"
      }
    }
  ]
}
```

**Response:** `200 OK`
```json
{
  "queue_id": "660e8400-e29b-41d4-a716-446655440000",
  "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
  "emr_id": "EMR12345",
  "status": "PENDING",
  "parsed_payload": {
    "experityAction": [
      {
        "action": "UPDATE_VITALS",
        "data": {
          "temperature": 98.6,
          "bloodPressure": "120/80"
        }
      }
    ]
  },
  "updated_at": "2025-11-21T10:35:00Z"
}
```

**Error Responses:**
- `404 Not Found`: Queue entry not found
- `400 Bad Request`: Missing both `queue_id` and `encounter_id`

---

### Summary Endpoints

#### 8. Create Summary

**`POST /summary`**

Create a summary record for a patient.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `emr_id` | string | Yes | EMR identifier for the patient |
| `note` | string | Yes | Summary note text |

**Example Request:**
```json
POST /summary
{
  "emr_id": "EMR12345",
  "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days."
}
```

**Response:** `201 Created`
```json
{
  "id": 123,
  "emr_id": "EMR12345",
  "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
  "created_at": "2025-11-21T10:30:00Z",
  "updated_at": "2025-11-21T10:30:00Z"
}
```

---

#### 9. Get Summary by EMR ID

**`GET /summary`**

Retrieve the most recent summary record for a patient.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `emr_id` | string | Yes | EMR identifier for the patient |

**Example Request:**
```bash
GET /summary?emr_id=EMR12345
```

**Response:** `200 OK`
```json
{
  "id": 123,
  "emr_id": "EMR12345",
  "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
  "created_at": "2025-11-21T10:30:00Z",
  "updated_at": "2025-11-21T10:30:00Z"
}
```

**Error Responses:**
- `404 Not Found`: Summary not found for the specified EMR ID

---

### Experity Endpoints

#### 10. Map Queue Entry to Experity Actions

**`POST /experity/map`**

Map a queue entry to Experity actions using Azure AI.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `queue_entry` | object | Yes | Queue entry object containing: |
| `queue_entry.queue_id` | string (UUID) | No | Queue identifier (used for database updates) |
| `queue_entry.encounter_id` | string (UUID) | Yes | Encounter identifier |
| `queue_entry.raw_payload` | object | Yes | Dictionary with encounter data |
| `queue_entry.parsed_payload` | object | No | Optional parsed payload dictionary |

**Example Request:**
```json
POST /experity/map
{
  "queue_entry": {
    "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
    "raw_payload": {
      "encounterId": "550e8400-e29b-41d4-a716-446655440000",
      "emrId": "EMR12345",
      "chiefComplaints": [
        {
          "mainProblem": "Fever and cough",
          "bodyParts": ["chest", "throat"]
        }
      ]
    }
  }
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "experity_actions": {
      "emrId": "EMR12345",
      "vitals": {
        "temperature": 98.6,
        "bloodPressure": "120/80"
      },
      "guardianAssistedInterview": null,
      "labOrders": [],
      "icdUpdates": [],
      "complaints": [
        {
          "mainProblem": "Fever and cough",
          "bodyParts": ["chest", "throat"]
        }
      ]
    },
    "queue_id": "660e8400-e29b-41d4-a716-446655440000",
    "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
    "processed_at": "2025-11-21T10:30:00Z"
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data or missing required fields
- `404 Not Found`: Queue entry not found in database
- `502 Bad Gateway`: Azure AI agent returned an error
- `504 Gateway Timeout`: Request to Azure AI agent timed out

**Note:** This endpoint calls Azure AI to generate Experity mapping. The queue entry status is set to `PROCESSING` during the request. On success, experity_actions are stored in parsed_payload but status remains `PROCESSING` (not automatically set to `DONE`). On error, status is set to `ERROR`. Use `PATCH /queue/{queue_id}/status` to manually set status to `DONE` when ready.

---

## Request/Response Examples

### Complete Python Example

```python
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone
from urllib.parse import urlencode

class SolvAPIClient:
    """Client for making HMAC-authenticated requests to Solv Health API."""
    
    def __init__(self, secret_key: str, base_url: str = "https://app-97926.on-aptible.com"):
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
    
    def _generate_signature(self, method: str, path: str, body: str) -> tuple:
        """Generate HMAC signature for a request."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body_str = body if body else ""
        body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()
        canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode('utf-8'),
                canonical.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        return signature, timestamp
    
    def request(self, method: str, endpoint: str, body: dict = None, params: dict = None):
        """Make an HMAC-authenticated request."""
        path = endpoint
        if params:
            query_string = urlencode(params, doseq=True)
            path = f"{endpoint}?{query_string}"
        
        body_str = json.dumps(body) if body else ""
        signature, timestamp = self._generate_signature(method, path, body_str)
        
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }
        
        url = f"{self.base_url}{endpoint}"
        if method.upper() == "GET":
            return requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            return requests.post(url, headers=headers, json=body, timeout=30)
        elif method.upper() == "PATCH":
            return requests.patch(url, headers=headers, json=body, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")

# Usage
client = SolvAPIClient(secret_key="your-secret-key-here")

# Example 1: List patients
response = client.request("GET", "/patients", params={"locationId": "AXjwbE", "limit": 10})
patients = response.json()
print(f"Found {len(patients)} patients")

# Example 2: Create patient
response = client.request("POST", "/patients/create", body={
    "emr_id": "EMR12345",
    "location_id": "AXjwbE",
    "legalFirstName": "John",
    "legalLastName": "Doe",
    "status": "confirmed"
})
print(response.json())

# Example 3: Update patient status
response = client.request("PATCH", "/patients/EMR12345", body={"status": "checked_in"})
print(response.json())

# Example 4: Create encounter
response = client.request("POST", "/encounter", body={
    "encounterId": "550e8400-e29b-41d4-a716-446655440000",
    "emrId": "EMR12345",
    "chiefComplaints": [
        {"mainProblem": "Fever and cough", "bodyParts": ["chest", "throat"]}
    ]
})
print(response.json())
```

### Complete JavaScript/Node.js Example

```javascript
const crypto = require('crypto');
const https = require('https');

class SolvAPIClient {
    constructor(secretKey, baseUrl = 'https://app-97926.on-aptible.com') {
        this.secretKey = secretKey;
        this.baseUrl = baseUrl.replace(/\/$/, '');
    }

    _generateSignature(method, path, body) {
        const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
        const bodyStr = body || '';
        const bodyHash = crypto.createHash('sha256')
            .update(bodyStr)
            .digest('hex');
        const canonical = `${method.toUpperCase()}\n${path}\n${timestamp}\n${bodyHash}`;
        const signature = crypto
            .createHmac('sha256', this.secretKey)
            .update(canonical)
            .digest('base64');
        return { signature, timestamp };
    }

    request(method, endpoint, body = null, params = null) {
        return new Promise((resolve, reject) => {
            let path = endpoint;
            if (params) {
                const queryString = new URLSearchParams(params).toString();
                path = `${endpoint}?${queryString}`;
            }

            const bodyStr = body ? JSON.stringify(body) : '';
            const { signature, timestamp } = this._generateSignature(method, path, bodyStr);

            const url = new URL(`${this.baseUrl}${endpoint}`);
            if (params) {
                Object.keys(params).forEach(key => {
                    url.searchParams.append(key, params[key]);
                });
            }

            const options = {
                hostname: url.hostname,
                path: url.pathname + url.search,
                method: method.toUpperCase(),
                headers: {
                    'Content-Type': 'application/json',
                    'X-Timestamp': timestamp,
                    'X-Signature': signature
                }
            };

            const req = https.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    resolve({
                        statusCode: res.statusCode,
                        body: JSON.parse(data || '{}')
                    });
                });
            });

            req.on('error', reject);
            if (body) {
                req.write(bodyStr);
            }
            req.end();
        });
    }
}

// Usage
const client = new SolvAPIClient('your-secret-key-here');

// Example: List patients
client.request('GET', '/patients', null, { locationId: 'AXjwbE', limit: 10 })
    .then(response => {
        console.log('Status:', response.statusCode);
        console.log('Patients:', response.body);
    })
    .catch(console.error);
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| `200` | OK | Request successful |
| `201` | Created | Resource created successfully |
| `400` | Bad Request | Invalid request data or missing required fields |
| `401` | Unauthorized | Invalid or missing HMAC signature |
| `404` | Not Found | Resource not found |
| `500` | Internal Server Error | Server error |
| `502` | Bad Gateway | External service (e.g., Azure AI) error |
| `504` | Gateway Timeout | Request timeout |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Error Scenarios

#### 1. Invalid HMAC Signature

**Response:** `401 Unauthorized`
```json
{
  "detail": "Invalid HMAC signature"
}
```

**Solutions:**
- Verify your secret key is correct
- Check that the canonical string format is correct
- Ensure body hash matches the exact request body
- Verify timestamp is within ±5 minutes of server time

#### 2. Missing Required Fields

**Response:** `400 Bad Request`
```json
{
  "detail": "emr_id is required. Please provide an EMR identifier for the patient."
}
```

**Solutions:**
- Review endpoint documentation for required fields
- Ensure all required fields are included in the request body

#### 3. Resource Not Found

**Response:** `404 Not Found`
```json
{
  "detail": "Patient with EMR ID 'EMR12345' not found"
}
```

**Solutions:**
- Verify the resource identifier is correct
- Check if the resource exists before updating

#### 4. Timestamp Expired

**Response:** `401 Unauthorized`
```json
{
  "detail": "Timestamp expired or invalid"
}
```

**Solutions:**
- Generate timestamp just before making the request
- Ensure system clock is synchronized (use NTP)
- Verify timestamp format: `YYYY-MM-DDTHH:MM:SSZ`

---

## Best Practices

### 1. Security

✅ **DO:**
- Store secret keys in environment variables or secure vaults
- Use HTTPS for all requests
- Generate timestamps just before making requests
- Implement request retry logic with exponential backoff
- Log requests without exposing sensitive data

❌ **DON'T:**
- Commit secret keys to version control
- Share keys in plain text emails
- Hardcode keys in source code
- Reuse timestamps across requests
- Send requests over HTTP

### 2. Error Handling

✅ **DO:**
- Handle 401 errors gracefully (regenerate signature)
- Implement automatic retry for transient errors (500, 502, 504)
- Log errors for debugging (without sensitive data)
- Alert on authentication failures

❌ **DON'T:**
- Retry indefinitely on 401 errors
- Ignore error responses
- Expose secret keys in error messages

### 3. Performance

✅ **DO:**
- Use appropriate `limit` parameters to avoid large responses
- Implement pagination for large datasets
- Cache responses when appropriate
- Use connection pooling for multiple requests

### 4. Data Validation

✅ **DO:**
- Validate data before sending requests
- Use consistent date/time formats (ISO 8601)
- Ensure UUIDs are properly formatted
- Verify required fields are present

---

## Code Examples

### Python: Complete Client Implementation

See [Request/Response Examples](#requestresponse-examples) section above for a complete Python client.

### JavaScript: Complete Client Implementation

See [Request/Response Examples](#requestresponse-examples) section above for a complete JavaScript client.

### cURL Examples

```bash
#!/bin/bash

SECRET_KEY="your-secret-key-here"
API_URL="https://app-97926.on-aptible.com"
METHOD="POST"
PATH="/patients/create"
BODY='{"emr_id":"EMR12345","location_id":"AXjwbE","status":"confirmed"}'

# Generate timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Hash body
BODY_HASH=$(echo -n "$BODY" | sha256sum | cut -d' ' -f1)

# Create canonical string
CANONICAL="${METHOD}
${PATH}
${TIMESTAMP}
${BODY_HASH}"

# Generate HMAC signature
SIGNATURE=$(echo -n "$CANONICAL" | openssl dgst -sha256 -hmac "$SECRET_KEY" -binary | base64)

# Make request
curl -X POST "${API_URL}${PATH}" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

---

## Additional Resources

- **HMAC Authentication Guide:** [`docs/HMAC_AUTHENTICATION_GUIDE.md`](./HMAC_AUTHENTICATION_GUIDE.md)
- **Interactive API Documentation:** `https://app-97926.on-aptible.com/docs` (Swagger UI)
- **Alternative API Documentation:** `https://app-97926.on-aptible.com/redoc` (ReDoc)

---

## Support

For API support, please contact your API administrator or development team.

---

**Document Version:** 1.0  
**Last Updated:** November 2025

