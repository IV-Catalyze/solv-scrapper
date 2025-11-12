#!/usr/bin/env python3
"""Check database records"""

import os
import sys
from pathlib import Path

try:
    import psycopg2
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Check if DATABASE_URL is set (preferred for cloud deployments)
database_url = os.getenv('DATABASE_URL')

if database_url:
    # Parse the connection URL
    try:
        from urllib.parse import urlparse
        # Handle postgres:// and postgresql:// URLs
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
        # Enable SSL for remote databases (Aptible requires SSL)
        if parsed.hostname and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            db_config['sslmode'] = 'require'
    except Exception as e:
        print(f"Error parsing DATABASE_URL: {e}")
        print("DATABASE_URL format should be: postgresql://user:password@host:port/database")
        sys.exit(1)
else:
    # Fall back to individual environment variables
    db_host = os.getenv('DB_HOST', 'localhost')
    db_config = {
        'host': db_host,
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'solvhealth_patients'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    # Enable SSL for remote databases (Aptible requires SSL)
    if db_host and db_host not in ('localhost', '127.0.0.1', '::1'):
        db_config['sslmode'] = 'require'

try:
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor()
    
    # Check if patients table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'patients'
        );
    """)
    table_exists = cursor.fetchone()[0]
    
    if not table_exists:
        print("❌ Patients table does not exist yet.")
        print("   Run: psql -U postgres -d solvhealth_patients -f db_schema.sql")
    else:
        # Get count of records
        cursor.execute("SELECT COUNT(*) FROM patients;")
        count = cursor.fetchone()[0]
        print(f"✅ Found {count} patient record(s) in the database\n")
        
        if count > 0:
            # Get all records
            cursor.execute("""
                SELECT 
                    patient_id, solv_id, emr_id, location_id, location_name,
                    legal_first_name, legal_last_name, first_name, last_name,
                    mobile_phone, dob, date_of_birth, reason_for_visit,
                    sex_at_birth, gender, room, captured_at, updated_at
                FROM patients
                ORDER BY captured_at DESC
                LIMIT 50;
            """)
            
            records = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            print("=" * 100)
            for i, record in enumerate(records, 1):
                print(f"\n📋 Record #{i}:")
                print("-" * 100)
                for col, val in zip(columns, record):
                    if val is not None:
                        print(f"  {col:20s}: {val}")
                print()
        else:
            print("   No records found. The table exists but is empty.")
            print("   Submit a patient form to capture data.")
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    print("\nPlease check:")
    print("  1. PostgreSQL is running")
    print("  2. Database credentials in .env file are correct")
    print("  3. Database 'solvhealth_patients' exists")
    print("  4. Table 'patients' exists (run db_schema.sql if needed)")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

