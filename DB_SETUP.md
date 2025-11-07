# PostgreSQL Database Setup Guide

This guide explains how to set up PostgreSQL and save JSON patient data to the database.

## Prerequisites

1. **PostgreSQL installed** on your system
   - macOS: `brew install postgresql@14` or download from [postgresql.org](https://www.postgresql.org/download/)
   - Linux: `sudo apt-get install postgresql` (Ubuntu/Debian) or use your package manager
   - Windows: Download from [postgresql.org](https://www.postgresql.org/download/windows/)

2. **Python dependencies** installed:
   ```bash
   pip install -r requirements.txt
   ```

## Database Setup

### Step 1: Create Database

Connect to PostgreSQL and create the database:

```bash
# Connect to PostgreSQL (default user is usually 'postgres')
psql -U postgres

# Create database
CREATE DATABASE solvhealth_patients;

# Connect to the new database
\c solvhealth_patients

# Run the schema file
\i db_schema.sql

# Exit
\q
```

Or run the schema file directly:

```bash
psql -U postgres -d solvhealth_patients -f db_schema.sql
```

### Step 2: Configure Database Connection

Set environment variables for database connection. You can either:

**Option A: Use environment variables**
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=solvhealth_patients
export DB_USER=postgres
export DB_PASSWORD=your_password
```

**Option B: Create a .env file** (recommended)
```bash
# Create .env file in the project root
cat > .env << EOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=your_password
EOF
```

## Usage

### Process pending patients captured by monitor

```bash
python save_to_db.py --pending --on-conflict update
```

### Include pending patients that do not yet have an EMR ID (for troubleshooting)

```bash
python save_to_db.py --pending --include-pending-without-emr
```

### Import a specific legacy JSON file

```bash
python save_to_db.py --file path/to/legacy_patient_data.json --on-conflict update
```

### Import all JSON files from a directory

```bash
python save_to_db.py --all --directory /path/to/json/files --on-conflict update
```

### Create tables and process pending patients in one step

```bash
python save_to_db.py --pending --create-tables
```

## Command Line Options

- `--file FILE`: Import a specific JSON file
- `--directory DIR`: Directory containing JSON files (default: scraped-data)
- `--all`: Import all JSON files from the directory
- `--create-tables`: Create database tables before importing
- `--on-conflict {ignore,update}`: What to do when duplicate records are found (default: ignore)

## Database Schema

The `patients` table includes the following fields:

- `id`: Auto-incrementing primary key
- `patient_id`: Patient identifier
- `solv_id`: Solv health identifier
- `emr_id`: EMR identifier
- `location_id`: Location identifier
- `location_name`: Location name
- `legal_first_name`, `legal_last_name`: Legal names
- `first_name`, `last_name`: Preferred names
- `mobile_phone`: Phone number
- `dob`: Date of birth (string format)
- `date_of_birth`: Date of birth (DATE type)
- `reason_for_visit`: Visit reason
- `sex_at_birth`, `gender`: Gender information
- `room`: Room assignment
- `captured_at`: Timestamp when data was captured
- `created_at`, `updated_at`: Record timestamps
- `raw_data`: Full JSON data (JSONB type)

## Troubleshooting

### Connection Error

If you get a connection error, check:
1. PostgreSQL is running: `pg_isready` or `brew services list` (macOS)
2. Database credentials are correct
3. Database exists: `psql -U postgres -l`

### Permission Error

If you get permission errors:
```bash
# Grant permissions (run as postgres superuser)
psql -U postgres
GRANT ALL PRIVILEGES ON DATABASE solvhealth_patients TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

### Table Already Exists

If tables already exist, the script will skip creation. To recreate:
```sql
DROP TABLE IF EXISTS patients CASCADE;
```
Then run `db_schema.sql` again.

## Querying Data

Once data is imported, you can query it:

```bash
psql -U postgres -d solvhealth_patients

# Count total patients
SELECT COUNT(*) FROM patients;

# View recent patients
SELECT * FROM patients ORDER BY created_at DESC LIMIT 10;

# Find patients by location
SELECT * FROM patients WHERE location_id = 'AXjwbE';

# Find patients with EMR IDs
SELECT patient_id, emr_id, first_name, last_name FROM patients WHERE emr_id IS NOT NULL;
```

