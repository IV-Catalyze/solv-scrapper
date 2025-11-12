# Intellivisit Patient Queue API

## Integration Guide - Solv Health x Intellivisit

Practical guide for the Intellivisit engineering team to connect with and consume the Solv Health Patient Queue API hosted on Aptible. The API mirrors the Solv dashboard dataset so Intellivisit can retrieve and synchronize patient data in near real time.

---

## Base URLs

| Environment        | Base URL                                   | Description                                     |
|--------------------|---------------------------------------------|-------------------------------------------------|
| Staging / Production | `https://app-97926.on-aptible.com/`       | Aptible-hosted deployment for all integrations. |
| Interactive docs   | `https://app-97926.on-aptible.com/docs`    | Swagger UI for live exploration and testing.    |

During local development you may still run the API with `uvicorn api:app --reload` to serve `http://localhost:8000`, but Intellivisit integrations must target the Aptible environment listed above.

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
    "client_id": "intellivisit-production",
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
  "client_id": "intellivisit-production"
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

## 3. GET /

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



