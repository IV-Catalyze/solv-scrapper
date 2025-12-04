# API Quick Reference

**Base URL:** `https://app-97926.on-aptible.com`

---

## Authentication

All endpoints require HMAC-SHA256 authentication with these headers:
- `X-Timestamp`: ISO 8601 UTC timestamp
- `X-Signature`: Base64-encoded HMAC-SHA256 signature
- `Content-Type`: `application/json` (for POST/PATCH)

**Canonical String Format:**
```
METHOD\nPATH\nTIMESTAMP\nBODY_HASH
```

---

## Endpoints

### Patients

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/patients` | List patients (requires `locationId` query param) |
| `GET` | `/patient/{emr_id}` | Get patient by EMR ID |
| `POST` | `/patients/create` | Create or update patient |
| `PATCH` | `/patients/{emr_id}` | Update patient status |

### Encounters

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/encounter` | Create or update encounter |

### Queue

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/queue` | List queue entries (optional filters) |
| `POST` | `/queue` | Update queue experityAction |

### Summaries

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/summary` | Create summary |
| `GET` | `/summary?emr_id={emr_id}` | Get summary by EMR ID |

### Experity

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/experity/map` | Map queue entry to Experity actions |

---

## Common Request Examples

### List Patients
```bash
GET /patients?locationId=AXjwbE&statuses=confirmed&limit=50
```

### Create Patient
```json
POST /patients/create
{
  "emr_id": "EMR12345",
  "location_id": "AXjwbE",
  "legalFirstName": "John",
  "legalLastName": "Doe",
  "status": "confirmed"
}
```

### Update Patient Status
```json
PATCH /patients/EMR12345
{
  "status": "checked_in"
}
```

### Create Encounter
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
  ]
}
```

### Create Summary
```json
POST /summary
{
  "emr_id": "EMR12345",
  "note": "Patient summary text"
}
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | OK |
| `201` | Created |
| `400` | Bad Request |
| `401` | Unauthorized |
| `404` | Not Found |
| `500` | Internal Server Error |
| `502` | Bad Gateway |
| `504` | Gateway Timeout |

---

## Required Fields Quick Reference

### Create Patient (`POST /patients/create`)
- ✅ `emr_id` (required)
- ✅ `location_id` (required for new patients)

### Create Encounter (`POST /encounter`)
- ✅ `encounterId` or `encounter_id` (required)
- ✅ `emrId` or `emr_id` (required)
- ✅ `chiefComplaints` or `chief_complaints` (required, non-empty array)

### Create Summary (`POST /summary`)
- ✅ `emr_id` (required)
- ✅ `note` (required)

### Update Patient Status (`PATCH /patients/{emr_id}`)
- ✅ `status` (required in body)

---

## Field Name Conventions

Most endpoints support both:
- **camelCase**: `encounterId`, `emrId`, `chiefComplaints`
- **snake_case**: `encounter_id`, `emr_id`, `chief_complaints`

Use whichever format is more convenient for your application.

---

## Common Status Values

### Patient Status
- `confirmed`
- `checked_in`
- `pending`

### Queue Status
- `PENDING`
- `PROCESSING`
- `DONE`
- `ERROR`

---

## Quick Python Example

```python
from solv_api_client import SolvAPIClient

client = SolvAPIClient(secret_key="your-secret-key")

# List patients
patients = client.request("GET", "/patients", params={"locationId": "AXjwbE"})

# Create patient
result = client.request("POST", "/patients/create", body={
    "emr_id": "EMR12345",
    "location_id": "AXjwbE",
    "status": "confirmed"
})

# Update status
result = client.request("PATCH", "/patients/EMR12345", body={"status": "checked_in"})
```

---

**For detailed documentation, see:** [`API_COMPLETE_GUIDE.md`](./API_COMPLETE_GUIDE.md)

