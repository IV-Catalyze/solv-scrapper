# Quick Setup Checklist

Use this checklist to quickly set up the project on a new machine.

## Prerequisites Checklist

- [ ] Python 3.8+ installed (`python3 --version`)
- [ ] pip installed (`pip --version`)
- [ ] PostgreSQL installed (`psql --version`)
- [ ] Git installed (if cloning from repository)

## Setup Steps

### 1. Clone/Download Project
- [ ] Project files are in the working directory

### 2. Install PostgreSQL
- [ ] PostgreSQL is installed
- [ ] PostgreSQL service is running
- [ ] Database `solvhealth_patients` is created
- [ ] Database tables are created (run `db_schema.sql`)

### 3. Python Environment
- [ ] Virtual environment is created (`python3 -m venv venv`)
- [ ] Virtual environment is activated
- [ ] Python dependencies are installed (`pip install -r requirements.txt`)
- [ ] Playwright browsers are installed (`playwright install chromium`)

### 4. Configuration
- [ ] `.env` file is created (copy from `.env.example`)
- [ ] Database credentials are set in `.env`
- [ ] `SOLVHEALTH_QUEUE_URL` is set in `.env`
- [ ] Optional: Authentication keys are set in `.env`

### 5. Verification
- [ ] Database connection works (`python3 check_db_records.py`)
- [ ] API server starts (`python3 -m uvicorn api:app --port 8000`)
- [ ] Monitor script runs (`python3 monitor_patient_form.py`)

### 6. Run Application
- [ ] All services run successfully (`python3 run_all.py`)
- [ ] API docs are accessible (`http://localhost:8000/docs`)
- [ ] Dashboard is accessible (`http://localhost:8000/`)

## Quick Commands Reference

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set up database
psql -U postgres -c "CREATE DATABASE solvhealth_patients;"
psql -U postgres -d solvhealth_patients -f db_schema.sql

# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Verify setup
python3 check_db_records.py

# Run application
python3 run_all.py
```

## Common Issues

- **PostgreSQL not running**: Start the service (`brew services start postgresql@15` on macOS)
- **Port 8000 in use**: Change `API_PORT` in `.env` or kill the process using port 8000
- **Database connection failed**: Check credentials in `.env` and verify PostgreSQL is running
- **Playwright browsers not found**: Run `playwright install chromium`
- **Module not found**: Activate virtual environment and reinstall dependencies

## Need Help?

See `SETUP_GUIDE.md` for detailed instructions and troubleshooting.




