# Intellivisit Integration Guide

Custom guide for the Intellivisit engineering team to consume the patient queue API exposed by Solv Health.

---

## Base URLs

| Environment | Base URL | Notes |
|-------------|----------|-------|
| Staging | `https://{staging-host}/` | Replace `{staging-host}` with the hostname provided by Solv. |
| Production | `https://{production-host}/` | Confirm the hostname and TLS requirements with Solv before go-live. |

> During local development the API runs on `http://localhost:8000`, but Intellivisit integrations should target the staging or production hosts above.

## Authentication

The current API does **not** enforce authentication. If credentials or API keys are added later, Solv will provide separate onboarding instructions. Intellivisit should, however, originate requests from an allow-listed IP range (coordinate with Solv DevOps if firewall rules are needed).

## Shared Conventions

- **Content type**: `application/json` for all JSON endpoints.
- **Date/time fields**: ISO 8601 strings (UTC). Some responses also include human-friendly renderings such as `captured_display`.
- **Case sensitivity**: Status filters are case-insensitive; parameter names are camelCase (`locationId`).
- **Pagination**: No cursor-based pagination yet. Use the `limit` query parameter to control payload size.
- **Rate limits**: Not enforced today; please keep request bursts reasonable (≤ 5 req/sec baseline).

---

## Endpoints

### `GET /patients`

Retrieve the active queue for a single clinic location. This mirrors the dataset rendered in the dashboard UI.

- **Query parameters**
  - `locationId` *(required, string)* – Unique identifier for the clinic location.
  - `statuses` *(optional, repeatable)* – One or more patient statuses. Valid values include `confirmed`, `checked_in`, `completed`, etc. Omit to default to `["checked_in", "confirmed"]`.
  - `limit` *(optional, integer ≥ 1)* – Maximum number of records to return after sorting by `captured_at` (desc) then `updated_at`.
- **Response**: `200 OK` with an array of patient objects (see [Patient payload](#patient-payload)).

Example request:

```
curl -s \
  "https://{staging-host}/patients?locationId=AXjwbE&statuses=confirmed&statuses=checked_in&limit=25" \
  | jq
```

Sample response (abridged):

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
    "calendar_date": "2024-11-06"
    // ...
  }
]
```

**Error responses**

| HTTP code | Reason | How to resolve |
|-----------|--------|----------------|
| `400 Bad Request` | `locationId` missing or all provided statuses invalid | Supply a valid `locationId` and at least one allowed status. |
| `500 Internal Server Error` | Database connectivity or unexpected error | Retry and contact Solv if the issue persists. |

### `GET /patient/{emr_id}`

Fetch the most recent record for a specific EMR identifier.

- **Path parameters**
  - `emr_id` *(string)* – EMR ID to search for.
- **Response**: `200 OK` with a single patient object (same schema as `/patients`).

Example:

```
curl -s "https://{staging-host}/patient/EMR12345" | jq
```

Possible errors:

| HTTP code | Reason |
|-----------|--------|
| `404 Not Found` | No record found for the supplied EMR ID |
| `500 Internal Server Error` | Database or server failure |

### `GET /`

Renders the HTML dashboard used internally by Solv. This is *not* required for programmatic integrations, but the same query parameters apply as `/patients`. Useful for visual verification during testing.

```
https://{staging-host}/?locationId=AXjwbE&statuses=confirmed&limit=25
```

---

## Patient Payload

Every patient object follows the schema implemented in `api.py`. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `emr_id` | string | EMR identifier (unique per patient). |
| `booking_id` | string | Internal booking identifier. |
| `booking_number` | string | Human-readable booking number. |
| `patient_number` | string | Clinic-specific patient number. |
| `location_id` / `location_name` | string | Location metadata. |
| `legalFirstName` / `legalLastName` | string | Patient identity. |
| `dob` | string (ISO date) | Birthdate. |
| `mobilePhone` | string | Primary phone number. |
| `sexAtBirth` | string | Recorded gender marker. |
| `captured_at` | string (ISO datetime) | When the record was captured. |
| `captured_display` | string | Human-readable capture time. |
| `reasonForVisit` | string | Visit reason notes. |
| `created_at`, `updated_at` | string (ISO datetime) | Timestamps from the source system. |
| `status` | string | Normalized queue status. |
| `status_label` | string | Title-cased label derived from `status`. |
| `status_class` | string | Lowercase variant for styling. |
| `appointment_date` | string (ISO date) | Scheduled appointment date, if provided. |
| `appointment_date_at_clinic_tz` | string (ISO datetime) | Appointment time localized to clinic timezone. |
| `calendar_date` | string (ISO date) | Calendar date associated with the visit. |
| `source` | string | Indicates `confirmed` or `pending` origin. |

> Additional fields may appear as the upstream data model evolves. Intellivisit should handle unknown keys gracefully.

---

## Operational Guidelines

- **Retry policy**: Use exponential backoff (e.g., 1s, 2s, 4s) for transient `500` errors.
- **Monitoring**: Log the `status`, `location_id`, and `emr_id` for downstream troubleshooting.
- **Data freshness**: Responses are live views of the operational database; no caching layer is currently in front of the API.
- **Change management**: Solv will announce schema or behavior changes via the shared Slack channel at least two weeks in advance.

## Support

For questions or incident reports, contact:

- **Primary contact**: Solv Health Integration Team – `integrations@solvhealth.com`
- **Slack**: `#intellivisit-solv-integration` (shared)
- **Hours**: 8am–6pm CT, Monday–Friday

Please include request samples, timestamps, and x-request-id headers (if available) when reporting issues.


