# Running in API-Only Mode (No Database Required)

You can now run the patient form monitor **without any database setup**. It will capture patient data and send it directly to your API endpoint.

## Quick Start

1. **Set the required environment variables:**

```bash
# Required: API endpoint URL
export API_URL="https://your-api-endpoint.com"

# Required: Solvhealth queue URL
export SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"

# Optional: Disable database (defaults to true if not set)
export USE_DATABASE="false"

# Optional: Enable/disable API sending (defaults to true)
export USE_API="true"
```

2. **Run the monitor:**

```bash
python monitor_patient_form.py
```

That's it! The monitor will:
- ✅ Capture patient form data when forms are submitted
- ✅ Wait for EMR IDs to be assigned
- ✅ Send patient data directly to your API endpoint
- ❌ **Skip all database operations** (no database required)

## Environment Variables

### Required

- **`API_URL`**: Your API endpoint base URL (e.g., `https://app.example.com`)
  - The monitor will send POST requests to `{API_URL}/patients/create`
  - Example: `export API_URL="https://app-97926.on-aptible.com"`

- **`SOLVHEALTH_QUEUE_URL`**: The Solvhealth queue page URL to monitor
  - Example: `export SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"`

### Optional

- **`USE_DATABASE`**: Set to `"false"` to disable database operations (default: `"true"`)
  - When `false`, no database connection is attempted
  - Patient data will only be sent to API
  
- **`USE_API`**: Set to `"false"` to disable API sending (default: `"true"`)
  - When `false`, patient data will not be sent to API
  - Only useful if you want database-only mode

## Example `.env` File

Create a `.env` file in the project root:

```env
# Required for API-only mode
API_URL=https://your-production-api.com
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE

# Disable database
USE_DATABASE=false

# Enable API sending (default)
USE_API=true
```

## How It Works

1. **Form Monitoring**: The monitor watches for patient form submissions on the Solvhealth queue page

2. **Data Capture**: When a form is submitted, it captures:
   - Patient name (legal first/last name)
   - Date of birth
   - Mobile phone
   - Sex at birth
   - Reason for visit
   - Location information
   - Booking information

3. **EMR ID Detection**: The monitor waits for EMR IDs to be assigned (from API responses)

4. **API Sending**: Once an EMR ID is available, the patient data is automatically sent to your API endpoint:
   - Endpoint: `POST {API_URL}/patients/create`
   - Headers: Includes authentication token if `API_TOKEN` is set
   - Payload: Normalized patient data in JSON format

5. **Database Skipped**: When `USE_DATABASE=false`, all database operations are skipped:
   - No connection to PostgreSQL
   - No saving to `pending_patients` table
   - No saving to `patients` table

## API Request Format

The monitor sends patient data as a JSON POST request:

**Endpoint**: `POST {API_URL}/patients/create`

**Headers**:
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer {API_TOKEN}"  // If API_TOKEN is set
}
```

**Body**:
```json
{
  "emr_id": "12345",
  "booking_id": "booking-123",
  "booking_number": "BK-001",
  "patient_number": "PN-001",
  "location_id": "AXjwbE",
  "location_name": "Example Clinic",
  "legalFirstName": "John",
  "legalLastName": "Doe",
  "dob": "1990-01-01",
  "mobilePhone": "555-1234",
  "sexAtBirth": "M",
  "reasonForVisit": "Annual checkup",
  "status": "checked_in",
  "captured_at": "2024-01-01T12:00:00"
}
```

## Troubleshooting

### "API_URL not set" Error

Make sure you've set the `API_URL` environment variable:
```bash
export API_URL="https://your-api-endpoint.com"
```

Or add it to your `.env` file.

### "httpx not available" Warning

If you see this warning, install httpx:
```bash
pip install httpx
```

### Database Still Required Error

If you see database connection errors even with `USE_DATABASE=false`, make sure:
1. The environment variable is set: `export USE_DATABASE=false`
2. You're not importing or calling database functions elsewhere
3. You restart the monitor after changing environment variables

### API Authentication

If your API requires authentication, set the `API_TOKEN` environment variable:
```bash
export API_TOKEN="your-api-token-here"
```

The monitor will automatically include it in the `Authorization` header.

## Benefits of API-Only Mode

✅ **Simpler Setup**: No need to install or configure PostgreSQL  
✅ **Faster Startup**: No database connection overhead  
✅ **Lightweight**: Works on any machine without database dependencies  
✅ **Direct Integration**: Data goes straight to your API endpoint  
✅ **Production Ready**: Perfect for deployments where your API handles all data storage

## Switching Between Modes

- **API-Only Mode**: `USE_DATABASE=false` (no database required)
- **Database-Only Mode**: `USE_DATABASE=true`, `USE_API=false` (local storage only)
- **Hybrid Mode**: `USE_DATABASE=true`, `USE_API=true` (saves to both database and API)

