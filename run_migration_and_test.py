#!/usr/bin/env python3
"""
Script to run the alerts table migration and test the endpoints.

This script:
1. Connects to the database
2. Runs the alerts table migration
3. Verifies the table was created
4. Tests all alert endpoints
"""

import os
import sys
import subprocess
import psycopg2
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_step(message: str):
    """Print a step message."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{message}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_success(message: str):
    """Print success message."""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message: str):
    """Print error message."""
    print(f"{RED}✗ {message}{RESET}")


def print_info(message: str):
    """Print info message."""
    print(f"{YELLOW}ℹ {message}{RESET}")


def get_db_connection():
    """Get database connection from environment variables."""
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        # Parse the connection URL
        try:
            from urllib.parse import urlparse
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            parsed = urlparse(database_url)
            
            db_config = {
                'host': parsed.hostname,
                'port': parsed.port or 5432,
                'database': parsed.path.lstrip('/'),
                'user': parsed.username,
                'password': parsed.password or ''
            }
            if parsed.hostname and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                db_config['sslmode'] = 'require'
        except Exception as e:
            print_error(f"Error parsing DATABASE_URL: {str(e)}")
            return None
    else:
        # Fall back to individual environment variables
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'solvhealth_patients'),
            'user': os.getenv('DB_USER', os.getenv('USER', 'postgres')),
            'password': os.getenv('DB_PASSWORD', '')
        }
        if db_config['host'] and db_config['host'] not in ('localhost', '127.0.0.1', '::1'):
            db_config['sslmode'] = 'require'
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except psycopg2.Error as e:
        print_error(f"Database connection error: {str(e)}")
        return None


def run_migration(conn):
    """Run the alerts table migration."""
    print_step("Step 1: Running Migration")
    
    migration_file = Path(__file__).parent / 'migrate_alerts_table.sql'
    
    if not migration_file.exists():
        print_error(f"Migration file not found: {migration_file}")
        return False
    
    try:
        cursor = conn.cursor()
        
        # Read and execute migration SQL
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print_info("Executing migration SQL...")
        cursor.execute(migration_sql)
        conn.commit()
        cursor.close()
        
        print_success("Migration executed successfully")
        return True
        
    except psycopg2.Error as e:
        conn.rollback()
        print_error(f"Migration failed: {str(e)}")
        return False


def verify_table(conn):
    """Verify the alerts table was created correctly."""
    print_step("Step 2: Verifying Table")
    
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'alerts'
            );
        """)
        exists = cursor.fetchone()[0]
        
        if not exists:
            print_error("Alerts table does not exist")
            return False
        
        print_success("Alerts table exists")
        
        # Check columns
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'alerts'
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        
        print_info(f"Table has {len(columns)} columns:")
        for col_name, col_type, is_nullable in columns:
            nullable = "NULL" if is_nullable == 'YES' else "NOT NULL"
            print(f"  - {col_name}: {col_type} ({nullable})")
        
        # Check indexes
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'alerts';
        """)
        indexes = cursor.fetchall()
        
        print_info(f"Table has {len(indexes)} indexes:")
        for (index_name,) in indexes:
            print(f"  - {index_name}")
        
        cursor.close()
        return True
        
    except psycopg2.Error as e:
        print_error(f"Verification failed: {str(e)}")
        return False


def test_endpoints():
    """Test the alert endpoints."""
    print_step("Step 3: Testing Endpoints")
    
    # Check if API server is running
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    print_info(f"Testing API at: {api_url}")
    
    try:
        import requests
        response = requests.get(f"{api_url}/docs", timeout=5)
        if response.status_code not in [200, 404]:
            print_error(f"API server not responding (status: {response.status_code})")
            print_info("Please start the API server first:")
            print_info("  python3 -m uvicorn app.api.routes:app --reload")
            return False
    except requests.exceptions.RequestException:
        print_error("Cannot connect to API server")
        print_info("Please start the API server first:")
        print_info("  python3 -m uvicorn app.api.routes:app --reload")
        return False
    
    print_success("API server is running")
    
    # Run the test script
    test_script = Path(__file__).parent / 'test_alerts.py'
    
    if not test_script.exists():
        print_error(f"Test script not found: {test_script}")
        return False
    
    print_info("Running test script...")
    try:
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=False,
            text=True
        )
        
        if result.returncode == 0:
            print_success("All tests passed!")
            return True
        else:
            print_error(f"Tests failed with exit code {result.returncode}")
            return False
            
    except Exception as e:
        print_error(f"Failed to run tests: {str(e)}")
        return False


def main():
    """Main function."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Alerts Migration and Test Script{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    # Check database connection
    print_info("Connecting to database...")
    conn = get_db_connection()
    
    if not conn:
        print_error("Cannot connect to database")
        print_info("Please set database connection variables:")
        print_info("  DATABASE_URL or DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        sys.exit(1)
    
    print_success("Database connection established")
    
    try:
        # Run migration
        if not run_migration(conn):
            print_error("Migration failed")
            sys.exit(1)
        
        # Verify table
        if not verify_table(conn):
            print_error("Table verification failed")
            sys.exit(1)
        
        # Test endpoints
        if not test_endpoints():
            print_error("Endpoint tests failed")
            sys.exit(1)
        
        # Success
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{GREEN}✓ All steps completed successfully!{RESET}")
        print(f"{BLUE}{'='*60}{RESET}\n")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
