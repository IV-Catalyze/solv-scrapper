# Windows Quick Start Guide

Quick reference for setting up and running the project on Windows.

## Prerequisites Checklist

- [ ] Python 3.8+ installed with "Add Python to PATH" checked
- [ ] Git installed
- [ ] PostgreSQL installed OR Docker Desktop installed
- [ ] PowerShell or Command Prompt ready

## Quick Setup (5 minutes)

### 1. Clone Repository
```powershell
git clone https://github.com/your-username/solv-scrapper-clone.git
cd solv-scrapper-clone
```

### 2. Run Automated Setup
```powershell
# If you get execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then run the setup script:
.\setup-windows.ps1
```

### 3. Set Up Database

**Option A: PostgreSQL (Local)**
```powershell
# Create database
psql -U postgres -c "CREATE DATABASE solvhealth_patients;"

# Create tables
psql -U postgres -d solvhealth_patients -f db_schema.sql
```

**Option B: Docker**
```powershell
# Run PostgreSQL in Docker
docker run --name postgres-patients `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=solvhealth_patients `
  -p 5432:5432 `
  -d postgres:15

# Wait a few seconds, then create tables
docker exec -i postgres-patients psql -U postgres -d solvhealth_patients < db_schema.sql
```

### 4. Configure Environment

Edit `.env` file with your settings:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=postgres
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
```

### 5. Test Database Connection
```powershell
python check_db_records.py
```

### 6. Run the Project
```powershell
python run_all.py
```

## Access Points

- **API Dashboard:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs
- **API Endpoint:** http://localhost:8000/patients?locationId=AXjwbE

## Common Commands

### Start Everything
```powershell
python run_all.py
```

### Start API Only
```powershell
python api.py
```

### Start Monitor Only
```powershell
python monitor_patient_form.py
```

### Get API Token
```powershell
curl -X POST "http://localhost:8000/auth/token" `
  -H "Content-Type: application/json" `
  -d '{\"client_id\": \"test-client\", \"expires_hours\": 24}'
```

### Use API with Token
```powershell
curl -H "Authorization: Bearer YOUR_TOKEN" `
  "http://localhost:8000/patients?locationId=AXjwbE"
```

## Troubleshooting Quick Fixes

### Python not found
```powershell
# Use py launcher instead
py -m pip install -r requirements.txt
```

### Port already in use
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID with actual process ID)
taskkill /PID <process_id> /F
```

### Playwright browsers not installing
```powershell
# Install with dependencies
playwright install --with-deps chromium
```

### Database connection error
```powershell
# Check if PostgreSQL is running
Get-Service -Name postgresql*

# Test connection manually
psql -U postgres -d solvhealth_patients
```

### Execution policy error
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Next Steps

1. Update `SOLVHEALTH_QUEUE_URL` in `.env` with your location ID
2. Generate a secure `JWT_SECRET_KEY` for production
3. Configure authentication (see `AUTHENTICATION.md`)
4. Review API documentation at http://localhost:8000/docs

## Full Documentation

For detailed instructions, see:
- **WINDOWS_SETUP.md** - Complete Windows setup guide
- **API_GUIDE.md** - API documentation
- **AUTHENTICATION.md** - Authentication setup
- **DATABASE_SETUP.md** - Database configuration

## Need Help?

1. Check the troubleshooting section in `WINDOWS_SETUP.md`
2. Review error messages carefully
3. Verify all prerequisites are installed
4. Check that `.env` file is configured correctly
5. Ensure PostgreSQL is running and accessible

