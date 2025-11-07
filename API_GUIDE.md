# API Guide - How to Run and Test

This guide explains how to run and test the FastAPI patient data API.

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Database setup:**
   - Make sure PostgreSQL is running
   - Ensure your `.env` file has the correct database credentials:
     ```env
     DB_HOST=localhost
     DB_PORT=5432
     DB_NAME=solvhealth_patients
     DB_USER=postgres
     DB_PASSWORD=your_password
     ```
   - Verify you have patient records in the database (you can check with `python check_db_records.py`)

## Running the API

### Method 1: Using Python directly

```bash
python api.py
```

The API will start on `http://localhost:8000` by default.

### Method 2: Using uvicorn directly (recommended for development)

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

- `--reload`: Automatically reloads the server when you make code changes
- `--host 0.0.0.0`: Makes the API accessible from other machines on your network
- `--port 8000`: Sets the port (default is 8000)

### Custom Port/Host

You can also set custom host and port via environment variables:

```bash
export API_HOST=127.0.0.1
export API_PORT=8080
python api.py
```

## Testing the API

### 1. Check if the API is running

Open your browser or use curl:

```bash
curl http://localhost:8000/
```

You should see:
```json
{
  "message": "Patient Data API",
  "version": "1.0.0",
  "endpoints": {
    "GET /patient/{emr_id}": "Get patient record by EMR ID"
  }
}
```

### 2. Get a patient by EMR ID

First, you need to know an EMR ID from your database. You can:

**Option A: Check database records**
```bash
python check_db_records.py
```

Look for the `emr_id` field in the output.

**Option B: Query the database directly**
```bash
psql -U postgres -d solvhealth_patients -c "SELECT emr_id FROM patients WHERE emr_id IS NOT NULL LIMIT 5;"
```

**Then test the endpoint:**

Using curl:
```bash
curl http://localhost:8000/patient/YOUR_EMR_ID_HERE
```

Replace `YOUR_EMR_ID_HERE` with an actual EMR ID from your database.

**Example:**
```bash
curl http://localhost:8000/patient/12345
```


**Expected response (success):**
```json
{
  "id": 1,
  "patient_id": "ABC123",
  "solv_id": "SOLV456",
  "emr_id": "12345",
  "location_id": "AXjwbE",
  "location_name": "Exer Urgent Care - Demo",
  "legal_first_name": "John",
  "legal_last_name": "Doe",
  "first_name": "John",
  "last_name": "Doe",
  "mobile_phone": "(555) 123-4567",
  "dob": "01/15/1990",
  "date_of_birth": "1990-01-15",
  "reason_for_visit": "General checkup",
  "sex_at_birth": "Male",
  "gender": "Male",
  "room": "101",
  "captured_at": "2024-01-15T10:30:00",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "raw_data": {...}
}
```

**Expected response (not found):**
```json
{
  "detail": "Patient with EMR ID '99999' not found"
}
```

### 3. Using the Interactive API Documentation

FastAPI automatically generates interactive API documentation:

**Swagger UI (recommended):**
Open in your browser:
```
http://localhost:8000/docs
```

This provides:
- Interactive API documentation
- Try it out functionality - you can test endpoints directly from the browser
- Request/response schemas

**ReDoc:**
Open in your browser:
```
http://localhost:8000/redoc
```

Alternative documentation format with a cleaner interface.

### 4. Testing with Python requests

Create a test script `test_api.py`:

```python
import requests

# Test root endpoint
response = requests.get("http://localhost:8000/")
print("Root endpoint:", response.json())

# Test patient endpoint (replace with actual EMR ID)
emr_id = "12345"  # Replace with an actual EMR ID from your database
response = requests.get(f"http://localhost:8000/patient/{emr_id}")

if response.status_code == 200:
    print(f"\nPatient found:")
    print(response.json())
elif response.status_code == 404:
    print(f"\nPatient not found: {response.json()}")
else:
    print(f"\nError: {response.status_code}")
    print(response.json())
```

Run it:
```bash
pip install requests  # if not already installed
python test_api.py
```

### 5. Testing with HTTPie (if installed)

```bash
# Install HTTPie: pip install httpie

# Get root
http GET http://localhost:8000/

# Get patient
http GET http://localhost:8000/patient/12345
```

## Common Issues and Solutions

### Issue: "Database connection error"

**Solution:**
- Check that PostgreSQL is running: `pg_isready` or `psql -U postgres -c "SELECT 1;"`
- Verify `.env` file has correct credentials
- Test connection: `python check_db_records.py`

### Issue: "Patient with EMR ID 'X' not found"

**Solution:**
- Verify the EMR ID exists in the database: `python check_db_records.py`
- Check that `emr_id` is not NULL in the database
- Note: EMR IDs are case-sensitive

### Issue: "ModuleNotFoundError: No module named 'fastapi'"

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: Port already in use

**Solution:**
- Use a different port: `uvicorn api:app --port 8001`
- Or find and kill the process using port 8000:
  ```bash
  # On macOS/Linux:
  lsof -ti:8000 | xargs kill -9
  
  # Or:
  kill $(lsof -t -i:8000)
  ```

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information and available endpoints |
| GET | `/patient/{emr_id}` | Get patient record by EMR ID (returns most recent if multiple exist) |

## Response Codes

- `200 OK`: Patient found and returned successfully
- `404 Not Found`: Patient with the given EMR ID does not exist
- `500 Internal Server Error`: Database connection error or server error

## Notes

- The API returns the **most recent** patient record if multiple records exist with the same EMR ID (ordered by `captured_at DESC`)
- All datetime fields are returned in ISO 8601 format
- The `raw_data` field contains the complete original JSON data captured from the form

