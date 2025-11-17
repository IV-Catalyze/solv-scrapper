#!/bin/bash
# Setup script for Patient Form Data Capture project
# This script helps automate the setup process on macOS and Linux

set -e  # Exit on error

echo "=========================================="
echo "Patient Form Data Capture - Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${GREEN}→${NC} $1"
}

# Check if Python is installed
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    print_success "Python is installed: $PYTHON_VERSION"
else
    print_error "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if pip is installed
echo "Checking pip installation..."
if command -v pip3 &> /dev/null; then
    print_success "pip is installed"
else
    print_error "pip is not installed. Please install pip."
    exit 1
fi

# Check if PostgreSQL is installed
echo "Checking PostgreSQL installation..."
if command -v psql &> /dev/null; then
    POSTGRES_VERSION=$(psql --version)
    print_success "PostgreSQL is installed: $POSTGRES_VERSION"
else
    print_warning "PostgreSQL is not installed or not in PATH."
    print_info "Please install PostgreSQL:"
    print_info "  macOS: brew install postgresql@15"
    print_info "  Linux: sudo apt-get install postgresql"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment
echo ""
echo "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip --quiet
print_success "pip upgraded"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt --quiet
print_success "Python dependencies installed"

# Install Playwright browsers
echo ""
echo "Installing Playwright browsers..."
playwright install chromium --quiet
print_success "Playwright browsers installed"

# Check for .env file
echo ""
echo "Checking configuration..."
if [ ! -f ".env" ]; then
    print_warning ".env file not found"
    print_info "Creating .env file from template..."
    
    cat > .env << EOF
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=your_password_here

# Solvhealth Queue URL (required for monitoring)
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Playwright Configuration
PLAYWRIGHT_HEADLESS=false
EOF
    
    print_success ".env file created"
    print_warning "Please edit .env file and update:"
    print_warning "  1. DB_PASSWORD with your PostgreSQL password"
    print_warning "  2. SOLVHEALTH_QUEUE_URL with your location ID"
else
    print_success ".env file exists"
fi

# Check database connection
echo ""
echo "Checking database setup..."
if command -v psql &> /dev/null; then
    # Try to connect to database
    if psql -U postgres -d solvhealth_patients -c "SELECT 1;" &> /dev/null; then
        print_success "Database connection successful"
        
        # Check if tables exist
        if psql -U postgres -d solvhealth_patients -c "\dt" | grep -q "patients"; then
            print_success "Database tables exist"
        else
            print_warning "Database tables not found"
            print_info "Run the following to create tables:"
            print_info "  psql -U postgres -d solvhealth_patients -f db_schema.sql"
        fi
    else
        print_warning "Cannot connect to database"
        print_info "Please ensure:"
        print_info "  1. PostgreSQL is running"
        print_info "  2. Database 'solvhealth_patients' exists"
        print_info "  3. Database credentials in .env are correct"
        print_info ""
        print_info "To create the database, run:"
        print_info "  psql -U postgres -c 'CREATE DATABASE solvhealth_patients;'"
        print_info "  psql -U postgres -d solvhealth_patients -f db_schema.sql"
    fi
else
    print_warning "Cannot check database (psql not found)"
fi

# Summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
print_info "Next steps:"
echo "  1. Edit .env file with your database credentials"
echo "  2. Create database and tables (if not done):"
echo "     psql -U postgres -c 'CREATE DATABASE solvhealth_patients;'"
echo "     psql -U postgres -d solvhealth_patients -f db_schema.sql"
echo "  3. Activate virtual environment: source venv/bin/activate"
echo "  4. Run the application: python3 run_all.py"
echo ""
print_info "For detailed instructions, see SETUP_GUIDE.md"
echo ""




