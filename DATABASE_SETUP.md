# Database Setup Guide

## Quick Setup for PostgreSQL

### Option 1: Install PostgreSQL with Homebrew (Recommended)

```bash
# Install PostgreSQL
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Create database
createdb solvhealth_patients

# Create tables
psql -d solvhealth_patients -f db_schema.sql
```

### Option 2: Use Docker (Alternative)

```bash
# Run PostgreSQL in Docker
docker run --name postgres-patients \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=solvhealth_patients \
  -p 5432:5432 \
  -d postgres:15

# Wait a few seconds for PostgreSQL to start, then create tables
sleep 5
docker exec -i postgres-patients psql -U postgres -d solvhealth_patients < db_schema.sql
```

### Create .env File

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=solvhealth_patients
DB_USER=postgres
DB_PASSWORD=postgres
```

**Note:** Adjust the password if you set a different one during installation.

### Promote Pending Patient Data

After setting up the database, promote any captured submissions from the staging table:

```bash
# Process pending patients captured by the monitor (creates tables if needed)
python3 save_to_db.py --pending --create-tables --on-conflict update
```

If you still have historical JSON exports to backfill, you can import them with:

```bash
python3 save_to_db.py --file path/to/legacy_patient_data.json --on-conflict update
```

### Verify Setup

```bash
# Check database records
python3 check_db_records.py
```

## Troubleshooting

### PostgreSQL not starting

```bash
# Check if PostgreSQL is running
brew services list | grep postgres

# Start manually if needed
brew services start postgresql@15
```

### Connection refused

- Make sure PostgreSQL is running: `brew services list`
- Check if port 5432 is available: `lsof -i :5432`
- Verify `.env` file has correct credentials

### Permission denied

```bash
# Create user if needed (for Homebrew installation)
createuser -s postgres
```

