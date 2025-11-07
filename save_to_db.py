#!/usr/bin/env python3
"""
Utilities for promoting patient records to PostgreSQL.

Supports importing historical JSON files as well as processing
pending records captured by the monitor script.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from psycopg2 import sql
except ImportError:
    print("Error: psycopg2-binary is not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


def get_db_connection():
    """Get PostgreSQL database connection from environment variables."""
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'solvhealth_patients'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        print("\nPlease set the following environment variables:")
        print("  DB_HOST=localhost")
        print("  DB_PORT=5432")
        print("  DB_NAME=solvhealth_patients")
        print("  DB_USER=postgres")
        print("  DB_PASSWORD=your_password")
        print("\nOr create a .env file with these variables.")
        sys.exit(1)


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize date string to YYYY-MM-DD format."""
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    # Try to parse various date formats
    formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%m-%d-%Y',
        '%d/%m/%Y',
        '%d-%m-%Y',
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    # If all formats fail, return None
    return None


def normalize_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Normalize timestamp string to datetime object."""
    if not timestamp_str or timestamp_str.strip() == '':
        return None
    
    timestamp_str = timestamp_str.strip()
    
    # Try ISO format first
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Try other common formats
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    return None


def normalize_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize patient record for database insertion."""
    emr_id = record.get('emrId') or record.get('emr_id') or record.get('emrID')

    normalized = {
        'emr_id': emr_id.strip() if isinstance(emr_id, str) else emr_id,
        'booking_id': record.get('booking_id') or record.get('bookingId') or None,
        'booking_number': record.get('booking_number') or record.get('bookingNumber') or None,
        'patient_number': record.get('patient_number') or record.get('patientNumber') or None,
        'location_id': record.get('locationId') or record.get('location_id') or None,
        'location_name': record.get('location_name') or record.get('locationName') or None,
        'legal_first_name': record.get('legalFirstName') or record.get('legal_first_name') or record.get('firstName') or None,
        'legal_last_name': record.get('legalLastName') or record.get('legal_last_name') or record.get('lastName') or None,
        'dob': record.get('dob') or record.get('dateOfBirth') or record.get('date_of_birth') or None,
        'mobile_phone': record.get('mobilePhone') or record.get('mobile_phone') or record.get('phone') or None,
        'sex_at_birth': record.get('sexAtBirth') or record.get('sex_at_birth') or record.get('gender') or None,
        'captured_at': normalize_timestamp(record.get('captured_at') or record.get('capturedAt')) or datetime.now(),
        'reason_for_visit': record.get('reasonForVisit') or record.get('reason_for_visit') or record.get('reason') or None
    }

    for key, value in list(normalized.items()):
        if isinstance(value, str):
            value = value.strip()
            normalized[key] = value or None

    return normalized


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    """Load and parse JSON file, handling different structures."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different JSON structures
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Check for common keys that contain patient arrays
            for key in ['patients', 'data', 'items', 'results']:
                if key in data and isinstance(data[key], list):
                    return data[key]
            # If it's a single patient object
            if 'patientId' in data or 'patient_id' in data or 'legalFirstName' in data:
                return [data]
        
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file {file_path}: {e}")
        return []
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []


def insert_patients(conn, patients: List[Dict[str, Any]], on_conflict: str = 'ignore'):
    """Insert patient records into database."""
    if not patients:
        return 0
    
    cursor = conn.cursor()
    
    insert_query = """
        INSERT INTO patients (
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
            reason_for_visit
        ) VALUES %s
    """
    
    if on_conflict == 'ignore':
        insert_query += """
            ON CONFLICT (emr_id) DO NOTHING
        """
    elif on_conflict == 'update':
        insert_query += """
            ON CONFLICT (emr_id) DO UPDATE SET
                booking_id = EXCLUDED.booking_id,
                booking_number = EXCLUDED.booking_number,
                patient_number = EXCLUDED.patient_number,
                location_name = EXCLUDED.location_name,
                legal_first_name = EXCLUDED.legal_first_name,
                legal_last_name = EXCLUDED.legal_last_name,
                dob = EXCLUDED.dob,
                mobile_phone = EXCLUDED.mobile_phone,
                sex_at_birth = EXCLUDED.sex_at_birth,
                captured_at = EXCLUDED.captured_at,
                reason_for_visit = EXCLUDED.reason_for_visit,
                updated_at = CURRENT_TIMESTAMP
        """
    
    values = []
    for patient in patients:
        normalized = normalize_patient_record(patient)
        if not normalized.get('emr_id'):
            continue
        values.append((
            normalized['emr_id'],
            normalized['booking_id'],
            normalized['booking_number'],
            normalized['patient_number'],
            normalized['location_id'],
            normalized['location_name'],
            normalized['legal_first_name'],
            normalized['legal_last_name'],
            normalized['dob'],
            normalized['mobile_phone'],
            normalized['sex_at_birth'],
            normalized['captured_at'],
            normalized['reason_for_visit']
        ))
    
    if not values:
        cursor.close()
        return 0

    try:
        execute_values(cursor, insert_query, values)
        conn.commit()
        inserted_count = cursor.rowcount
        cursor.close()
        return inserted_count
    except psycopg2.Error as e:
        conn.rollback()
        cursor.close()
        print(f"Error inserting patients: {e}")
        raise


def fetch_pending_patients(
    conn,
    statuses: Optional[List[str]] = None,
    include_without_emr: bool = False
) -> List[Dict[str, Any]]:
    """Load pending patients from staging table."""
    if statuses is None:
        statuses = ['pending', 'ready']

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT pending_id,
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
        FROM pending_patients
        WHERE status = ANY(%s)
        ORDER BY created_at
        """,
        (statuses,)
    )

    rows = cursor.fetchall()
    cursor.close()

    pending_records: List[Dict[str, Any]] = []
    for (
        pending_id,
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
        status,
    ) in rows:
        if isinstance(raw_payload, dict):
            payload = raw_payload.copy()
        else:
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except (TypeError, json.JSONDecodeError):
                payload = {}

        payload.setdefault('emr_id', emr_id)
        payload.setdefault('booking_id', booking_id)
        payload.setdefault('booking_number', booking_number)
        payload.setdefault('patient_number', patient_number)
        payload.setdefault('location_id', location_id)
        payload.setdefault('location_name', location_name)
        payload.setdefault('legalFirstName', legal_first_name)
        payload.setdefault('legalLastName', legal_last_name)
        payload.setdefault('dob', dob)
        payload.setdefault('mobilePhone', mobile_phone)
        payload.setdefault('sexAtBirth', sex_at_birth)
        if captured_at and not payload.get('captured_at'):
            payload['captured_at'] = captured_at.isoformat()
        if reason_for_visit and not payload.get('reasonForVisit'):
            payload['reasonForVisit'] = reason_for_visit

        payload['pending_id'] = pending_id
        payload['pending_status'] = status

        if not include_without_emr and not payload.get('emr_id'):
            continue

        pending_records.append(payload)

    return pending_records


def mark_pending_records(
    conn,
    pending_ids: List[int],
    status: str,
    error_message: Optional[str] = None
) -> None:
    """Update status for a batch of pending patient records."""
    if not pending_ids:
        return

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE pending_patients
        SET status = %s,
            error_message = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE pending_id = ANY(%s)
        """,
        (status, error_message, pending_ids)
    )
    conn.commit()
    cursor.close()


def process_pending_patients(
    on_conflict: str = 'update',
    include_without_emr: bool = False
) -> int:
    """Process pending patients and promote them to the patients table."""
    conn = get_db_connection()
    try:
        create_tables(conn)

        pending_records = fetch_pending_patients(conn, include_without_emr=include_without_emr)
        if not pending_records:
            print("No pending patients found with EMR IDs ready for import.")
            return 0

        print(f"Found {len(pending_records)} pending patient(s) ready for import")

        inserted = insert_patients(conn, pending_records, on_conflict=on_conflict)
        if inserted:
            print(f"✅ Inserted/updated {inserted} patient(s) from pending staging table")
        else:
            print("⚠️  No pending patient records were inserted (missing EMR IDs?)")

        pending_ids = [record['pending_id'] for record in pending_records if record.get('emr_id')]
        if pending_ids:
            mark_pending_records(conn, pending_ids, 'completed')

        return inserted
    finally:
        conn.close()


def save_json_to_db(json_file: Path, on_conflict: str = 'ignore'):
    """Save a single JSON file to database."""
    print(f"Processing {json_file.name}...")
    
    patients = load_json_file(json_file)
    if not patients:
        print(f"  ⚠️  No patient data found in {json_file.name}")
        return 0
    
    print(f"  📊 Found {len(patients)} patient record(s)")
    
    conn = get_db_connection()
    try:
        inserted = insert_patients(conn, patients, on_conflict=on_conflict)
        print(f"  ✅ Inserted {inserted} record(s) into database")
        return inserted
    finally:
        conn.close()


def save_all_json_files(directory: Path, on_conflict: str = 'ignore'):
    """Save all JSON files in a directory to database."""
    json_files = list(directory.glob('*.json'))
    
    if not json_files:
        print(f"No JSON files found in {directory}")
        return
    
    print(f"Found {len(json_files)} JSON file(s) to process\n")
    
    total_inserted = 0
    for json_file in sorted(json_files):
        try:
            inserted = save_json_to_db(json_file, on_conflict=on_conflict)
            total_inserted += inserted
        except Exception as e:
            print(f"  ❌ Error processing {json_file.name}: {e}")
    
    print(f"\n✨ Total records inserted: {total_inserted}")


def create_tables(conn):
    """Create database tables if they don't exist."""
    schema_file = Path(__file__).parent / 'db_schema.sql'
    
    if not schema_file.exists():
        print(f"Schema file not found: {schema_file}")
        return False
    
    try:
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        # Remove CREATE DATABASE command if present (we're already connected)
        schema_sql = schema_sql.replace('CREATE DATABASE', '-- CREATE DATABASE')
        schema_sql = schema_sql.replace('\\c', '-- \\c')
        
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        print("✅ Database tables created successfully")
        return True
    except Exception as e:
        print(f"Error creating tables: {e}")
        conn.rollback()
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Save JSON patient data to PostgreSQL")
    parser.add_argument(
        '--file',
        type=str,
        help='Path to a specific JSON file to import'
    )
    parser.add_argument(
        '--directory',
        type=str,
        default='scraped-data',
        help='Directory containing JSON files to import (default: scraped-data)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Import all JSON files from the directory'
    )
    parser.add_argument(
        '--create-tables',
        action='store_true',
        help='Create database tables before importing'
    )
    parser.add_argument(
        '--pending',
        action='store_true',
        help='Process pending patients from the staging table (default when no file options provided)'
    )
    parser.add_argument(
        '--include-pending-without-emr',
        action='store_true',
        help='Include pending patients without EMR IDs when processing the staging table'
    )
    parser.add_argument(
        '--on-conflict',
        choices=['ignore', 'update'],
        default='ignore',
        help='What to do on conflict: ignore (default) or update existing records'
    )
    
    args = parser.parse_args()
    
    # Create tables if requested
    if args.create_tables:
        print("Creating database tables...")
        conn = get_db_connection()
        try:
            create_tables(conn)
        finally:
            conn.close()
        print()
    
    # Process pending records by default unless file options are explicitly provided
    ran_action = False

    if args.pending or not (args.file or args.all):
        process_pending_patients(
            on_conflict=args.on_conflict,
            include_without_emr=args.include_pending_without_emr
        )
        ran_action = True

    if args.file:
        json_file = Path(args.file)
        if not json_file.exists():
            print(f"Error: File not found: {json_file}")
            sys.exit(1)
        save_json_to_db(json_file, on_conflict=args.on_conflict)
        ran_action = True

    if args.all:
        directory = Path(args.directory)
        if not directory.exists():
            print(f"Error: Directory not found: {directory}")
            sys.exit(1)
        save_all_json_files(directory, on_conflict=args.on_conflict)
        ran_action = True

    if not ran_action:
        print("Nothing to do. Use --help to see available options.")


if __name__ == '__main__':
    main()

