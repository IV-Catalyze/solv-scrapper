# Windows Setup Script for Solv-Scraper-Clone
# This script helps automate the setup process on Windows

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "Solv-Scraper-Clone Windows Setup Script" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    exit 1
}

# Check if pip is installed
Write-Host "Checking pip installation..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version 2>&1
    Write-Host "✓ pip found: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ pip not found!" -ForegroundColor Red
    Write-Host "Installing pip..." -ForegroundColor Yellow
    python -m ensurepip --upgrade
}

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Install Playwright browsers
Write-Host "Installing Playwright browsers..." -ForegroundColor Yellow
playwright install chromium
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Playwright browsers installed successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install Playwright browsers" -ForegroundColor Red
    Write-Host "Try running: playwright install --with-deps chromium" -ForegroundColor Yellow
}

# Check if .env file exists
Write-Host "Checking for .env file..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✓ .env file exists" -ForegroundColor Green
} else {
    Write-Host "✗ .env file not found" -ForegroundColor Yellow
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    
    $envContent = @"
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=postgres
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
JWT_SECRET_KEY=your-very-secure-secret-key-minimum-32-characters-long
API_KEY=your-static-api-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=1440
"@
    
    $envContent | Out-File -FilePath ".env" -Encoding utf8
    Write-Host "✓ .env file created" -ForegroundColor Green
    Write-Host "⚠ Please edit .env file with your actual database credentials" -ForegroundColor Yellow
}

# Check if PostgreSQL is accessible
Write-Host "Checking PostgreSQL connection..." -ForegroundColor Yellow
if (Get-Command psql -ErrorAction SilentlyContinue) {
    Write-Host "✓ psql command found" -ForegroundColor Green
    Write-Host "You can test the connection with: psql -U postgres -d solvhealth_patients" -ForegroundColor Cyan
} else {
    Write-Host "⚠ psql command not found" -ForegroundColor Yellow
    Write-Host "PostgreSQL may not be installed or not in PATH" -ForegroundColor Yellow
    Write-Host "Install PostgreSQL from https://www.postgresql.org/download/windows/" -ForegroundColor Yellow
    Write-Host "Or use Docker: docker run --name postgres-patients -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=solvhealth_patients -p 5432:5432 -d postgres:15" -ForegroundColor Cyan
}

# Check if database schema file exists
Write-Host "Checking for database schema file..." -ForegroundColor Yellow
if (Test-Path "db_schema.sql") {
    Write-Host "✓ db_schema.sql found" -ForegroundColor Green
    Write-Host "Run this command to create tables: psql -U postgres -d solvhealth_patients -f db_schema.sql" -ForegroundColor Cyan
} else {
    Write-Host "✗ db_schema.sql not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Edit .env file with your database credentials" -ForegroundColor White
Write-Host "2. Set up PostgreSQL database (if not already done)" -ForegroundColor White
Write-Host "3. Run database schema: psql -U postgres -d solvhealth_patients -f db_schema.sql" -ForegroundColor White
Write-Host "4. Test database connection: python check_db_records.py" -ForegroundColor White
Write-Host "5. Run the project: python run_all.py" -ForegroundColor White
Write-Host ""
Write-Host "For detailed instructions, see WINDOWS_SETUP.md" -ForegroundColor Cyan
Write-Host ""

