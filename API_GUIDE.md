# Patient Data API Guide

Practical guide for running, exploring, and integrating with the FastAPI service defined in `api.py`.

## Prerequisites

- **Install dependencies**
  ```bash
  pip install -r requirements.txt
  ```
- **Configure database access**
  - PostgreSQL must be running locally or reachable from your machine.
  - Ensure `.env` contains valid credentials (used by `get_db_connection()` in `api.py`):
    ```env
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=solvhealth_patients
    DB_USER=postgres
    DB_PASSWORD=your_password
    ```
  - Seed the database with test data. Run `python check_db_records.py` to confirm records exist.

## Running the service

```bash
python api.py
```

The app launches on `http://localhost:8000` (override with `API_HOST` / `API_PORT` env vars). During development, `uvicorn api:app --reload` offers hot reloading.

## Architecture tour

Key pieces live in `api.py`:
- `prepare_dashboard_patients()` consolidates queue data by calling `fetch_confirmed_records()` and `fetch_pending_records()`.
- `build_patient_payload()` normalizes raw database rows into API-friendly dictionaries.
- `decorate_patient_payload()` adds presentation fields used by the dashboard template `templates/patients_table.html`.

Understanding these helpers clarifies the behavior you see in each endpoint response.

## Endpoint reference

All endpoints are visible (and testable) in Swagger UI: `http://localhost:8000/docs`. Use “Try it out” to make real requests once the server is running.

| Method | Path | Summary |
|--------|------|---------|
| GET | `/` | Render the patient dashboard HTML view |
| GET | `/patients` | Return queue data as JSON for a specific location |
| GET | `/patient/{emr_id}` | Return the latest patient record for an EMR ID |

### `GET /`

- **Purpose**: Serve the HTML dashboard (`patients_table.html`) populated with queue data.
- **Key code**: `root()` view in `api.py`.
- **Query parameters**:
  - `locationId` (optional): limits the dashboard to one location ID.
- `statuses` (optional, repeatable): filters queue statuses; defaults to `["checked_in", "confirmed"]` via `DEFAULT_STATUSES`. Non-string values or unknown statuses are ignored; if none remain after normalization, the defaults apply.
  - `limit` (optional int ≥ 1): trims the number of rendered rows.
- **Response**: HTML (not JSON). Use a browser or save output to a file if you curl it.

Example request (rendered HTML):
```bash
curl -H "Accept: text/html" "http://localhost:8000/?locationId=AXjwbE&statuses=confirmed&limit=25" -o dashboard.html
open dashboard.html  # macOS helper to preview
```

### `GET /patients`

- **Purpose**: Provide the same queue data as JSON (for automation or integration tests).
- **Key code**: `list_patients()` calls `prepare_dashboard_patients()` and returns JSON.
- **Required query parameters**:
  - `locationId`: filters results to a single site. The endpoint rejects requests without it.
- **Optional query parameters**:
  - `statuses`: repeat per value, e.g. `&statuses=confirmed&statuses=checked_in`. Valid values are case-insensitive; defaults to `["checked_in", "confirmed"]` when omitted. Requests that normalize to no valid statuses return `400 Bad Request`.
  - `limit`: max records to include after sorting (descending by `captured_at`, then `updated_at`).
- **Response shape** (fields produced by `build_patient_payload()` plus `decorate_patient_payload()`):

```startLine:endLine:api.py
    payload = {
        "emr_id": record.get("emr_id"),
        "booking_id": record.get("booking_id"),
        "booking_number": record.get("booking_number"),
        "patient_number": record.get("patient_number"),
        "location_id": record.get("location_id"),
        "location_name": record.get("location_name"),
        "legalFirstName": record.get("legal_first_name"),
        "legalLastName": record.get("legal_last_name"),
        "dob": record.get("dob"),
        "mobilePhone": record.get("mobile_phone"),
        "sexAtBirth": record.get("sex_at_birth"),
        "captured_at": captured,
        "reasonForVisit": record.get("reason_for_visit"),
        "created_at": created,
        "updated_at": updated,
    }

    status = record.get("patient_status") or record.get("status")
    if status:
        payload["status"] = status

    if appointment_date:
        payload["appointment_date"] = appointment_date

    if appointment_date_clinic_tz:
        payload["appointment_date_at_clinic_tz"] = appointment_date_clinic_tz

    if calendar_date:
        payload["calendar_date"] = calendar_date
```

```startLine:endLine:api.py
    status_class = normalize_status(payload.get("status")) or "unknown"
    payload["status_class"] = status_class
    payload["status_label"] = status_class.replace("_", " ").title()

    captured_display = None
    captured_raw = payload.get("captured_at")
    captured_dt = parse_datetime(captured_raw)
    if captured_dt > datetime.min:
        captured_display = captured_dt.strftime("%b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")
    payload["captured_display"] = captured_display
```

Together, these helpers ensure each record may expose scheduling metadata (`status`, `appointment_date`, `appointment_date_at_clinic_tz`, `calendar_date`) and presentation helpers (`status_class`, `status_label`, `captured_display`) in addition to the base identity fields.

Sample call:
```bash
curl "http://localhost:8000/patients?locationId=AXjwbE&statuses=confirmed&limit=10" | jq
```

### `GET /patient/{emr_id}`

- **Purpose**: Fetch the latest record matching a specific EMR ID.
- **Key code**: `get_patient_by_emr_id()` in `api.py`.
- **Behavior**:
  - Queries the `patients` table.
  - Orders by `captured_at DESC` and returns the first record.
  - Uses `build_patient_payload()` to shape the response.
- **Responses**:
  - `200 OK`: JSON payload with normalized field names.
  - `404 Not Found`: when no record exists for the supplied EMR ID.

Example:
```bash
curl http://localhost:8000/patient/EMR12345 | jq
```

## Working with the interactive docs

- Navigate to `http://localhost:8000/docs` (Swagger UI).
- Authorize (if auth is added later; none today).
- Expand an endpoint, click **Try it out**, fill query params, and **Execute**.
- Review the auto-generated curl command and server response.
- Alternate view: `http://localhost:8000/redoc` (read-only but cleaner layout).

## Verifying data in the database

Use the helper script or run SQL manually:

```bash
python check_db_records.py  # prints sample rows
psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT emr_id, location_id FROM patients LIMIT 5;"
```

These values map directly to the fields returned from `build_patient_payload()`.

## Troubleshooting

- **Database connection error**: Confirm PostgreSQL is reachable and credentials in `.env` match. The stack trace originates from `get_db_connection()`.
- **Empty dashboard/JSON**: Ensure `locationId` matches real data. Inspect `prepare_dashboard_patients()` to see how `statuses` filters data.
- **Missing Python packages**: Run `pip install -r requirements.txt`.
- **Port in use**: Launch on another port (`uvicorn api:app --port 8001`) or free the existing process (`lsof -ti:8000 | xargs kill`).

## Testing with Python

Quick smoke test using `requests`:

```python
import requests

response = requests.get("http://localhost:8000/patients", params={"locationId": "AXjwbE"})
response.raise_for_status()
for patient in response.json():
    print(patient["emr_id"], patient.get("status_label"))
```

Run with:
```bash
pip install requests
python test_api.py
```

## HTTP status reference

- `200 OK`: Successful request.
- `400 Bad Request`: Missing `locationId` or invalid `statuses` on `/patients`.
- `404 Not Found`: Unknown EMR ID on `/patient/{emr_id}`.
- `500 Internal Server Error`: Database or unexpected server error (see FastAPI logs).

## Field notes

- All date/time values are ISO 8601 strings after normalization in `build_patient_payload()`.
- The dashboard output augments payloads with `status_*` fields for templating (`patients_table.html`).
- Extend behavior by modifying helpers in `api.py`; the docs above map each endpoint to the supporting functions to make navigation easier.

