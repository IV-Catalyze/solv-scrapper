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

### Quick Start

**For a complete step-by-step setup guide, see [SETUP_GUIDE.md](SETUP_GUIDE.md)**

This guide covers:
- Installing PostgreSQL
- Setting up Python environment
- Configuring database
- Running the application
- Troubleshooting common issues

### Platform-Specific Setup

- **New Machine Setup**: See [SETUP_GUIDE.md](SETUP_GUIDE.md) for complete step-by-step instructions
- **Windows VM**: See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for Windows-specific installation instructions
- **macOS/Linux**: Follow the instructions below or use the automated setup script:
  ```bash
  chmod +x setup.sh
  ./setup.sh
  ```

### General Installation

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
psql -U postgres -d solvhealth_patients -f app/database/schema.sql
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
python -m app.core.monitor
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
python3 -m app.core.monitor
```

The script will extract the `location_ids` parameter from the URL. See `app/utils/locations.py` for all available locations.

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

## Project Structure

```
solv-scrapper-clone/
├── app/                    # Main application code
│   ├── api/               # API routes and endpoints
│   │   └── routes.py     # FastAPI application
│   ├── core/             # Core monitoring functionality
│   │   └── monitor.py    # Patient form monitor
│   ├── database/         # Database utilities
│   │   ├── utils.py      # Database helper functions
│   │   └── schema.sql    # Database schema
│   ├── utils/            # Utility modules
│   │   ├── api_client.py # External API client
│   │   ├── auth.py       # Authentication
│   │   ├── locations.py  # Location mappings
│   │   └── patient.py    # Patient data utilities
│   └── templates/        # HTML templates
├── scripts/              # Setup and utility scripts
├── tests/                # Test files
├── docs/                 # Documentation
├── deployment/           # Deployment configuration
├── run_all.py           # Main entry point (runs both monitor and API)
└── requirements.txt     # Python dependencies
```

## Files

- `run_all.py` - **Run both monitor and API server together** (recommended)
- `app/core/monitor.py` - Main script for form monitoring
- `app/api/routes.py` - FastAPI server to access patient data
- `tests/save_to_db.py` - Database saving utilities
- `app/utils/locations.py` - Location ID to name mapping
- `app/database/schema.sql` - Database schema

## License

ISC
# playwright-test-python
