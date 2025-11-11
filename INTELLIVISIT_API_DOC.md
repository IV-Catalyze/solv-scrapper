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

- No authentication is currently required.
- Requests should originate from Intellivisit's allow-listed IP range; coordinate with Solv DevOps if firewall updates are needed.
- If API keys or other credentials are introduced later, Solv will deliver updated onboarding materials.

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

| Method | Path                  | Description                                              |
|--------|-----------------------|----------------------------------------------------------|
| GET    | `/`                   | Render the patient dashboard HTML (visual inspection)    |
| GET    | `/patients`           | Retrieve the active patient queue for a location         |
| GET    | `/patient/{emr_id}`   | Retrieve the most recent record for a specific EMR ID    |

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

```
curl -s \
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

```
curl -s "https://app-97926.on-aptible.com/patient/EMR12345" | jq
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



