# Windows VM Setup Guide

Complete guide for cloning and running this project on a Windows Virtual Machine.

## Prerequisites

Before starting, ensure you have:
- Windows 10/11 VM with internet access
- Administrator access to install software
- At least 4GB RAM and 10GB free disk space

## Step 1: Install Python

1. **Download Python 3.8+**
   - Visit [https://www.python.org/downloads/](https://www.python.org/downloads/)
   - Download the latest Python 3.11 or 3.12 (64-bit)
   - Run the installer

2. **During Installation:**
   - ✅ Check "Add Python to PATH" (IMPORTANT!)
   - ✅ Check "Install pip"
   - Click "Install Now"

3. **Verify Installation:**
   Open PowerShell or Command Prompt and run:
   ```powershell
   python --version
   pip --version
   ```
   Both should show version numbers.

## Step 2: Install Git

1. **Download Git for Windows**
   - Visit [https://git-scm.com/download/win](https://git-scm.com/download/win)
   - Download and run the installer
   - Use default settings (recommended)

2. **Verify Installation:**
   ```powershell
   git --version
   ```

## Step 3: Clone the Repository

1. **Open PowerShell or Command Prompt**

2. **Navigate to your desired directory:**
   ```powershell
   cd C:\Users\YourUsername\Documents
   ```

3. **Clone the repository:**
   ```powershell
   git clone https://github.com/kleyessa-prog/solv-scrapper-clone.git
   ```
   *(Replace with your actual repository URL)*

4. **Navigate into the project directory:**
   ```powershell
   cd solv-scrapper-clone
   ```

## Step 4: Install Python Dependencies

### Option A: Automated Setup (Recommended)

Run the automated setup script:

```powershell
.\setup-windows.ps1
```

**Note:** If you get an execution policy error, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run the script again:
```powershell
.\setup-windows.ps1
```

This script will:
- Check Python and pip installation
- Install all dependencies
- Install Playwright browsers
- Create `.env` file if it doesn't exist
- Check for PostgreSQL installation
- Provide next steps

### Option B: Manual Setup

1. **Upgrade pip (recommended):**
   ```powershell
   python -m pip install --upgrade pip
   ```

2. **Install project dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers:**
   ```powershell
   playwright install chromium
   ```
   This will download Chromium browser (required for the script).

## Step 5: Set Up PostgreSQL Database

You have two options:

### Option A: Install PostgreSQL (Recommended for Production)

1. **Download PostgreSQL:**
   - Visit [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
   - Download PostgreSQL installer (latest version)
   - Run the installer

2. **During Installation:**
   - Set a password for the `postgres` user (remember this!)
   - Default port: 5432 (keep as-is)
   - Keep default installation directory

3. **Create Database:**
   - Open "SQL Shell (psql)" from Start Menu
   - Press Enter to accept defaults (localhost, postgres user, etc.)
   - Enter your postgres password
   - Run:
     ```sql
     CREATE DATABASE solvhealth_patients;
     \q
     ```

4. **Run Database Schema:**
   Open PowerShell in the project directory:
   ```powershell
   psql -U postgres -d solvhealth_patients -f db_schema.sql
   ```
   Enter your postgres password when prompted.

### Option B: Use Docker (Easier Setup)

1. **Install Docker Desktop for Windows:**
   - Visit [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
   - Download and install Docker Desktop
   - Restart your computer if prompted
   - Start Docker Desktop

2. **Run PostgreSQL in Docker:**
   ```powershell
   docker run --name postgres-patients `
     -e POSTGRES_PASSWORD=postgres `
     -e POSTGRES_DB=solvhealth_patients `
     -p 5432:5432 `
     -d postgres:15
   ```

3. **Wait a few seconds, then create tables:**
   ```powershell
   docker exec -i postgres-patients psql -U postgres -d solvhealth_patients < db_schema.sql
   ```

## Step 6: Configure Environment Variables

1. **Create `.env` file:**
   - In the project root directory, create a new file named `.env`
   - You can use Notepad or any text editor

2. **Add database configuration:**
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=solvhealth_patients
   DB_USER=postgres
   DB_PASSWORD=postgres
   ```
   *(Change password if you set a different one during PostgreSQL installation)*

3. **Add Solvhealth Queue URL:**
   ```env
   SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
   ```
   *(Replace with your actual location ID)*

4. **Add optional authentication (for API):**
   ```env
   JWT_SECRET_KEY=your-very-secure-secret-key-minimum-32-characters-long
   API_KEY=your-static-api-key-here
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   ```

5. **Save the file** as `.env` (make sure it's not `.env.txt`)

## Step 7: Verify Database Connection

1. **Test database connection:**
   ```powershell
   python check_db_records.py
   ```
   This should connect to the database and show any existing records (or empty if new).

## Step 8: Run the Project

You have two options:

### Option A: Run Everything Together (Recommended)

This runs both the API server and the patient form monitor:

```powershell
python run_all.py
```

This will:
- Start the API server on `http://localhost:8000`
- Start the patient form monitor
- Both run concurrently
- Press `Ctrl+C` to stop both

### Option B: Run Separately

1. **Run API server only:**
   Open one PowerShell window:
   ```powershell
   python api.py
   ```
   Server will be available at `http://localhost:8000`

2. **Run monitor only:**
   Open another PowerShell window:
   ```powershell
   python monitor_patient_form.py
   ```
   This will open a browser window and start monitoring for form submissions.

## Step 9: Access the API

1. **Open browser and navigate to:**
   ```
   http://localhost:8000
   ```
   This shows the patient dashboard.

2. **Access API documentation:**
   ```
   http://localhost:8000/docs
   ```
   This is the interactive Swagger UI where you can test all endpoints.

3. **Get an access token:**
   ```powershell
   curl -X POST "http://localhost:8000/auth/token" `
     -H "Content-Type: application/json" `
     -d '{\"client_id\": \"test-client\", \"expires_hours\": 24}'
   ```
   *(Note: Windows PowerShell uses backticks ` for line continuation)*

## Windows-Specific Notes

### PowerShell vs Command Prompt

- **PowerShell** (recommended): More modern, better error handling
- **Command Prompt (CMD)**: Works, but use `^` instead of `` ` `` for line continuation

### Path Separators

- Windows uses backslashes `\` in paths
- Python accepts both `\` and `/` in paths
- Use forward slashes `/` in URLs and environment variables

### Environment Variables in PowerShell

Set environment variables temporarily:
```powershell
$env:SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"
```

Or permanently:
```powershell
[System.Environment]::SetEnvironmentVariable('SOLVHEALTH_QUEUE_URL', 'https://manage.solvhealth.com/queue?location_ids=AXjwbE', 'User')
```

### Playwright on Windows

Playwright browsers are installed in:
```
%USERPROFILE%\AppData\Local\ms-playwright\
```

If you encounter issues, try:
```powershell
playwright install --force chromium
```

### Firewall Settings

Windows Firewall may block:
- PostgreSQL (port 5432)
- FastAPI server (port 8000)

If you can't connect:
1. Open Windows Defender Firewall
2. Allow Python and PostgreSQL through firewall
3. Or temporarily disable firewall for testing

## Troubleshooting

### Python not found

**Problem:** `python` command not found

**Solution:**
- Reinstall Python and check "Add Python to PATH"
- Or use `py` command instead: `py -m pip install -r requirements.txt`
- Or use full path: `C:\Python311\python.exe`

### pip not found

**Problem:** `pip` command not found

**Solution:**
```powershell
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```

### Playwright browsers not installing

**Problem:** `playwright install` fails

**Solution:**
```powershell
# Run as Administrator
playwright install --with-deps chromium
```

### Database connection error

**Problem:** Can't connect to PostgreSQL

**Solution:**
1. Verify PostgreSQL is running:
   ```powershell
   # Check if PostgreSQL service is running
   Get-Service -Name postgresql*
   ```
2. Check `.env` file has correct credentials
3. Test connection manually:
   ```powershell
   psql -U postgres -d solvhealth_patients
   ```

### Port already in use

**Problem:** Port 8000 or 5432 already in use

**Solution:**
1. Find process using the port:
   ```powershell
   netstat -ano | findstr :8000
   ```
2. Kill the process:
   ```powershell
   taskkill /PID <process_id> /F
   ```
3. Or change port in `.env`:
   ```env
   API_PORT=8001
   ```

### Module not found errors

**Problem:** `ModuleNotFoundError` when running scripts

**Solution:**
```powershell
# Make sure you're in the project directory
cd C:\Users\YourUsername\Documents\solv-scrapper-clone

# Reinstall dependencies
pip install -r requirements.txt
```

### Browser won't open

**Problem:** Playwright browser doesn't open

**Solution:**
1. Install browsers:
   ```powershell
   playwright install chromium
   ```
2. Check if headless mode is enabled (should show browser by default)
3. Try running with explicit browser:
   ```powershell
   $env:PLAYWRIGHT_HEADLESS="false"
   python monitor_patient_form.py
   ```

## Quick Start Checklist

- [ ] Python 3.8+ installed and in PATH
- [ ] Git installed
- [ ] Repository cloned
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Playwright browsers installed (`playwright install chromium`)
- [ ] PostgreSQL installed and running (or Docker container running)
- [ ] Database created (`solvhealth_patients`)
- [ ] Database schema applied (`db_schema.sql`)
- [ ] `.env` file created with correct credentials
- [ ] Database connection tested (`python check_db_records.py`)
- [ ] Project runs successfully (`python run_all.py`)

## Next Steps

1. **Configure location:** Update `SOLVHEALTH_QUEUE_URL` in `.env` with your location ID
2. **Set up authentication:** Generate a secure `JWT_SECRET_KEY` for production
3. **Test the monitor:** Submit a test patient form and verify it's captured
4. **Access the API:** Visit `http://localhost:8000/docs` to explore the API
5. **Review documentation:** Read `API_GUIDE.md` and `AUTHENTICATION.md` for details

## Additional Resources

- **API Guide:** See `API_GUIDE.md` for detailed API documentation
- **Authentication:** See `AUTHENTICATION.md` for authentication setup
- **Database Setup:** See `DATABASE_SETUP.md` for database configuration
- **Tunnel Setup:** See `README_TUNNEL.md` if you need to access remote database

## Getting Help

If you encounter issues:
1. Check the Troubleshooting section above
2. Review error messages carefully
3. Verify all prerequisites are installed
4. Check that `.env` file is configured correctly
5. Ensure PostgreSQL is running and accessible
6. Check Windows Firewall settings

## Security Notes

- Never commit `.env` file to version control
- Use strong passwords for PostgreSQL
- Generate a secure `JWT_SECRET_KEY` (minimum 32 characters)
- Use HTTPS in production (not HTTP)
- Keep dependencies up to date

