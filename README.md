# Patient Form Data Capture

A Python-based Playwright script that monitors the Solvhealth queue page and automatically captures patient form data when forms are submitted.

## Purpose

This project captures patient form data in real-time when the "Add Patient" form is submitted on the Solvhealth management portal. It automatically:

- Monitors for form submissions
- Captures all form field data (name, phone, DOB, reason for visit, etc.)
- Tracks EMR ID assignment from API responses
- Persists submissions to a PostgreSQL staging table and promotes them once an EMR ID is assigned

## Features

- **Real-time Form Monitoring**: Automatically detects when patient forms are submitted
- **Complete Data Capture**: Captures all form fields including:
  - Legal first name and last name
  - Mobile phone
  - Date of birth
  - Reason for visit
  - Sex at birth
  - Location information
- **EMR ID Tracking**: Monitors API responses to capture EMR IDs when assigned
- **Data Storage**: Writes every submission to the `pending_patients` staging table and promotes it to `patients` once an EMR ID is available
- **Location Management**: Supports multiple locations via location mapping

## Installation

1. **Install Python dependencies:**

```bash
pip install -r requirements.txt
```

2. **Install Playwright browsers:**

```bash
playwright install chromium
```

3. **Set up database (optional):**

Create a `.env` file with database credentials:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=your_password
```

Then run the database schema:

```bash
psql -U postgres -d solvhealth_patients -f db_schema.sql
```

## Usage

### Quick Start - Run Everything Together

**Run both the monitor and API server simultaneously:**

```bash
export SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"
python run_all.py
```

This will:
1. Start the API server on `http://localhost:8000`
2. Start the patient form monitor
3. Both run concurrently and can be stopped with Ctrl+C

### Basic Usage - Monitor Only

Run the form monitor (opens browser window):

```bash
python monitor_patient_form.py
```

The script will:
1. Open a browser window and navigate to the Solvhealth queue page
2. Set up form monitoring
3. Wait for you to submit patient forms
4. Automatically capture and persist form data when forms are submitted

### Instructions

1. Click 'Add Patient' button (modal will open)
2. Select location from dropdown in the modal
3. Fill out the form fields that appear
4. Click 'Add' button to submit
5. Form data will be captured and saved automatically

## Output

### Database

- Every captured submission is inserted into the `pending_patients` staging table immediately, even before an EMR ID exists.
- Background monitoring tasks update the staging row as soon as an EMR ID is detected.
- Once an EMR ID is present, the record is upserted into the primary `patients` table.
- The `save_to_db.py` utility can be used at any time to reprocess pending rows.

## Requirements

- Python 3.8+
- Playwright for Python
- PostgreSQL (optional, for database storage)
- psycopg2-binary (optional, for database support)

## Configuration

### Location

**Required**: The location must be specified via the `SOLVHEALTH_QUEUE_URL` environment variable with a `location_ids` parameter:

```bash
export SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"
python3 monitor_patient_form.py
```

The script will extract the `location_ids` parameter from the URL. See `locations.py` for all available locations.

## Troubleshooting

1. **Browser not opening**: Make sure Playwright browsers are installed with `playwright install chromium`
2. **Form data not captured**: Check browser console for JavaScript errors
3. **Database errors**: Ensure PostgreSQL is running and credentials in `.env` are correct
4. **EMR ID not captured**: EMR IDs are captured from API responses; they may take a few seconds to appear

## Deployment (Aptible)

1. Build the image using the included `Dockerfile` (Playwright browsers and system libraries are pre-installed).
2. Provision a PostgreSQL database on Aptible and capture its credentials.
3. Set the required environment variables on your Aptible app: `SOLVHEALTH_QUEUE_URL`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and optionally override `PLAYWRIGHT_HEADLESS` if you need interactive mode.
4. Deploy with `aptible deploy --app <APP_NAME>`; Aptible reads the `Procfile` to launch the `web` (FastAPI) and `worker` (Playwright monitor) services defined in `aptible.yml`.
5. Tail logs with `aptible logs --app <APP_NAME> --process web` or `--process worker` to verify the services are healthy.
6. See `APTIBLE_DEPLOYMENT.md` for a full end-to-end runbook, including pre-deploy smoke tests and troubleshooting tips.

## Files

- `run_all.py` - **Run both monitor and API server together** (recommended)
- `monitor_patient_form.py` - Main script for form monitoring
- `api.py` - FastAPI server to access patient data
- `save_to_db.py` - Database saving utilities
- `locations.py` - Location ID to name mapping
- `db_schema.sql` - Database schema

## License

ISC
# playwright-test-python
