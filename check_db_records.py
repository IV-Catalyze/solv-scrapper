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

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'solvhealth_patients'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

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

