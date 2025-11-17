# Step-by-Step Setup Guide (Without Docker)

This guide will help you set up and run the Patient Form Data Capture project on a new machine without using Docker.

## Prerequisites

- Python 3.8 or higher
- PostgreSQL 12 or higher
- pip (Python package manager)
- Git (to clone the repository, if not already done)

## Step 1: Clone the Repository

If you haven't already cloned the repository:

```bash
git clone <repository-url>
cd solv-scrapper-clone
```

## Step 2: Install PostgreSQL

### macOS (using Homebrew)

```bash
# Install PostgreSQL
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Verify PostgreSQL is running
brew services list | grep postgresql
```

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt-get update

# Install PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify PostgreSQL is running
sudo systemctl status postgresql
```

### Linux (Fedora/CentOS/RHEL)

```bash
# Install PostgreSQL
sudo dnf install postgresql postgresql-server

# Initialize and start PostgreSQL
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Windows

1. Download PostgreSQL from [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
2. Run the installer and follow the installation wizard
3. Remember the password you set for the `postgres` user
4. PostgreSQL service should start automatically

## Step 3: Set Up PostgreSQL Database

### Create Database and User

```bash
# Connect to PostgreSQL (default user is usually 'postgres')
psql -U postgres
```

In the PostgreSQL prompt, run:

```sql
-- Create database
CREATE DATABASE solvhealth_patients;

-- Create user (optional, you can use postgres user)
CREATE USER solvuser WITH PASSWORD 'your_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE solvhealth_patients TO solvuser;

-- Exit PostgreSQL
\q
```

### Create Database Tables

```bash
# Run the schema file to create tables
psql -U postgres -d solvhealth_patients -f db_schema.sql
```

**Note:** On Windows, you might need to use the full path to `psql.exe`, typically located in:
`C:\Program Files\PostgreSQL\<version>\bin\psql.exe`

## Step 4: Install Python Dependencies

### Create a Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### Install Python Packages

```bash
# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Step 5: Install Playwright Browsers

```bash
# Install Playwright browsers
playwright install chromium

# On Linux, you may also need to install system dependencies
playwright install-deps chromium
```

## Step 6: Configure Environment Variables

Create a `.env` file in the project root directory:

```bash
# Create .env file
touch .env
```

Edit the `.env` file with your database credentials:

```env
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=your_password_here

# Solvhealth Queue URL (required for monitoring)
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE

# API Configuration (optional)
API_HOST=0.0.0.0
API_PORT=8000

# Authentication (optional, for production)
JWT_SECRET_KEY=your-very-secure-secret-key-minimum-32-characters-long
API_KEY=your-static-api-key-here

# Playwright Configuration (optional)
PLAYWRIGHT_HEADLESS=false
```

**Important Notes:**
- Replace `your_password_here` with your actual PostgreSQL password
- Replace `your-very-secure-secret-key-minimum-32-characters-long` with a secure random string (you can generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- The `SOLVHEALTH_QUEUE_URL` should point to the correct Solvhealth queue page with the appropriate location ID
- Set `PLAYWRIGHT_HEADLESS=false` if you want to see the browser window (useful for debugging)

## Step 7: Verify Database Connection

Test the database connection:

```bash
# Check database records (this will test the connection)
python3 check_db_records.py
```

If you see connection errors, verify:
1. PostgreSQL is running: `pg_isready` or `brew services list` (macOS)
2. Database credentials in `.env` are correct
3. Database exists: `psql -U postgres -l`

## Step 8: Run the Application

You have two options for running the application:

### Option A: Run Everything Together (Recommended)

This runs both the API server and the patient form monitor simultaneously:

```bash
python3 run_all.py
```

This will:
1. Start the PostgreSQL database (if not already running, on macOS with Homebrew)
2. Start the FastAPI server on `http://localhost:8000`
3. Start the patient form monitor
4. Both run concurrently and can be stopped with Ctrl+C

### Option B: Run Components Separately

#### Start the API Server

```bash
# In one terminal
python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

#### Start the Patient Form Monitor

```bash
# In another terminal
python3 monitor_patient_form.py
```

## Step 9: Verify the Setup

### Test the API Server

1. Open your browser and navigate to:
   - API Docs: `http://localhost:8000/docs`
   - Dashboard: `http://localhost:8000/`

2. Test the API endpoint:
   ```bash
   curl http://localhost:8000/
   ```

### Test the Patient Form Monitor

1. The monitor will open a browser window
2. Navigate to the Solvhealth queue page
3. Click 'Add Patient' button
4. Fill out the form and submit
5. The form data should be captured automatically

## Step 10: Process Pending Patients (Optional)

If you have existing patient data to process:

```bash
# Process pending patients from the staging table
python3 save_to_db.py --pending --create-tables --on-conflict update
```

## Troubleshooting

### PostgreSQL Connection Issues

**Error: "connection refused" or "could not connect to server"**

- Check if PostgreSQL is running:
  ```bash
  # macOS
  brew services list
  
  # Linux
  sudo systemctl status postgresql
  
  # Windows
  # Check Services in Control Panel
  ```

- Verify the port is correct (default is 5432):
  ```bash
  # Check if port is in use
  lsof -i :5432  # macOS/Linux
  netstat -an | findstr :5432  # Windows
  ```

- Check PostgreSQL logs for errors

**Error: "password authentication failed"**

- Verify the password in `.env` matches your PostgreSQL password
- Try connecting manually: `psql -U postgres -d solvhealth_patients`

**Error: "database does not exist"**

- Create the database: `createdb solvhealth_patients`
- Or run: `psql -U postgres -c "CREATE DATABASE solvhealth_patients;"`

### Python/Playwright Issues

**Error: "playwright not installed"**

```bash
# Install Playwright browsers
playwright install chromium
```

**Error: "module not found"**

```bash
# Make sure you're in the virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

**Error: "browser not found"**

```bash
# Install Playwright system dependencies (Linux)
playwright install-deps chromium

# Reinstall browsers
playwright install chromium
```

### API Server Issues

**Error: "Address already in use"**

- Another process is using port 8000
- Change the port in `.env`: `API_PORT=8001`
- Or find and kill the process using port 8000:
  ```bash
  # macOS/Linux
  lsof -ti:8000 | xargs kill -9
  
  # Windows
  netstat -ano | findstr :8000
  taskkill /PID <PID> /F
  ```

### Authentication Issues

**Error: "Could not validate credentials"**

- If using JWT tokens, verify `JWT_SECRET_KEY` is set in `.env`
- Generate a new token from `/auth/token` endpoint
- Check token expiration time

**Error: "API key invalid"**

- Verify `API_KEY` is set in `.env` if using API key authentication
- Check the header name is exactly `X-API-Key` (case-sensitive)

### Monitor Issues

**Error: "Browser not opening"**

- Make sure Playwright browsers are installed: `playwright install chromium`
- Check `PLAYWRIGHT_HEADLESS` setting in `.env`
- Try running with `PLAYWRIGHT_HEADLESS=false` to see the browser

**Error: "Form data not captured"**

- Check browser console for JavaScript errors
- Verify the `SOLVHEALTH_QUEUE_URL` is correct
- Make sure you're clicking 'Add Patient' and submitting the form correctly

## Next Steps

1. **Configure Authentication**: Set up JWT secret key and API keys for production use
2. **Set Up Monitoring**: Consider adding logging and monitoring for production
3. **Backup Database**: Set up regular database backups
4. **Secure Configuration**: Ensure `.env` file is in `.gitignore` and never committed
5. **Review Documentation**: Read `API_GUIDE.md`, `AUTHENTICATION.md`, and `TESTING_GUIDE.md` for more details

## Additional Resources

- **API Documentation**: See `API_GUIDE.md` for API endpoint documentation
- **Authentication Guide**: See `AUTHENTICATION.md` for authentication setup
- **Database Setup**: See `DATABASE_SETUP.md` for more database configuration options
- **Testing Guide**: See `TESTING_GUIDE.md` for testing instructions

## Support

If you encounter issues not covered in this guide:

1. Check the project's existing documentation files
2. Review error messages in the terminal output
3. Check PostgreSQL logs for database-related issues
4. Verify all environment variables are set correctly
5. Ensure all dependencies are installed and up to date


