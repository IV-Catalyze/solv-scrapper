#!/usr/bin/env python3
"""
Test script to save a record to pending_patients table on server database.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

def get_db_connection():
    """Get database connection using the same logic as the application."""
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
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
    else:
        db_host = os.getenv('DB_HOST', 'localhost')
        db_config = {
            'host': db_host,
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'solvhealth_patients'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
        if db_host and db_host not in ('localhost', '127.0.0.1', '::1'):
            db_config['sslmode'] = 'require'
    
    return psycopg2.connect(**db_config)

def ensure_table_exists(conn):
    """Ensure pending_patients table exists."""
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'pending_patients'
        );
    """)
    
    if not cursor.fetchone()[0]:
        print("Creating pending_patients table...")
        schema_file = Path(__file__).parent / 'db_schema.sql'
        if schema_file.exists():
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
                schema_sql = schema_sql.replace('CREATE DATABASE', '-- CREATE DATABASE')
                schema_sql = schema_sql.replace('\\c', '-- \\c')
                cursor.execute(schema_sql)
                conn.commit()
                print("✅ Table created")
        else:
            print("❌ Schema file not found")
            cursor.close()
            return False
    
    cursor.close()
    return True

def test_save_pending_patient():
    """Test saving a patient to pending_patients table."""
    print("=" * 60)
    print("Testing Save to pending_patients (Server Database)")
    print("=" * 60)
    print()
    
    # Get connection info
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'db')
    
    print(f"Connecting to: {db_host}:{db_port}/{db_name}")
    print()
    
    try:
        conn = get_db_connection()
        print("✅ Connected to database")
        
        # Ensure table exists
        if not ensure_table_exists(conn):
            return False
        
        cursor = conn.cursor()
        
        # Create test patient data
        test_timestamp = datetime.now()
        test_data = {
            'emr_id': None,  # Will be filled later
            'booking_id': f'TEST_BOOK_{int(test_timestamp.timestamp())}',
            'booking_number': f'TEST{int(test_timestamp.timestamp())}',
            'patient_number': None,
            'location_id': 'TEST_LOC',
            'location_name': 'Test Location',
            'legal_first_name': 'Test',
            'legal_last_name': 'Patient',
            'dob': '01/01/1990',
            'mobile_phone': '(555) 123-4567',
            'sex_at_birth': 'Male',
            'captured_at': test_timestamp,
            'reason_for_visit': 'Test visit',
            'raw_payload': {
                'test': True,
                'timestamp': test_timestamp.isoformat(),
                'source': 'test_script'
            },
            'status': 'pending'
        }
        
        print("Inserting test record...")
        print(f"  Name: {test_data['legal_first_name']} {test_data['legal_last_name']}")
        print(f"  Booking ID: {test_data['booking_id']}")
        print(f"  Location: {test_data['location_name']}")
        print()
        
        # Insert into pending_patients
        cursor.execute("""
            INSERT INTO pending_patients (
                emr_id,
                booking_id,
                booking_number,
                patient_number,
                location_id,
                location_name,
                legal_first_name,
                legal_last_name,
                dob,
                mobile_phone,
                sex_at_birth,
                captured_at,
                reason_for_visit,
                raw_payload,
                status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING pending_id, created_at;
        """, (
            test_data['emr_id'],
            test_data['booking_id'],
            test_data['booking_number'],
            test_data['patient_number'],
            test_data['location_id'],
            test_data['location_name'],
            test_data['legal_first_name'],
            test_data['legal_last_name'],
            test_data['dob'],
            test_data['mobile_phone'],
            test_data['sex_at_birth'],
            test_data['captured_at'],
            test_data['reason_for_visit'],
            Json(test_data['raw_payload']),
            test_data['status']
        ))
        
        result = cursor.fetchone()
        pending_id = result[0]
        created_at = result[1]
        conn.commit()
        
        print(f"✅ Record saved successfully!")
        print(f"   Pending ID: {pending_id}")
        print(f"   Created at: {created_at}")
        print()
        
        # Verify the record
        print("Verifying record in database...")
        cursor.execute("""
            SELECT 
                pending_id, emr_id, booking_id, booking_number,
                location_id, location_name,
                legal_first_name, legal_last_name,
                status, created_at
            FROM pending_patients
            WHERE pending_id = %s;
        """, (pending_id,))
        
        record = cursor.fetchone()
        if record:
            print("✅ Record verified in database:")
            print(f"   Pending ID: {record[0]}")
            print(f"   EMR ID: {record[1] or '(not assigned yet)'}")
            print(f"   Booking ID: {record[2]}")
            print(f"   Booking Number: {record[3]}")
            print(f"   Location: {record[5]} ({record[4]})")
            print(f"   Name: {record[6]} {record[7]}")
            print(f"   Status: {record[8]}")
            print(f"   Created: {record[9]}")
        
        # Show count of pending records
        cursor.execute("SELECT COUNT(*) FROM pending_patients WHERE status = 'pending';")
        pending_count = cursor.fetchone()[0]
        print()
        print(f"📊 Total pending records: {pending_count}")
        
        cursor.close()
        conn.close()
        
        print()
        print("=" * 60)
        print("✅ SUCCESS! Test record saved to server database!")
        print("=" * 60)
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_save_pending_patient()
    sys.exit(0 if success else 1)

