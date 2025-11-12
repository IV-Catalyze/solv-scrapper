#!/usr/bin/env python3
"""
Patient Form Monitor
A background Playwright script that monitors the Solvhealth queue page and captures
patient form data when the "Add Patient" button is clicked and the form is submitted.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List, Set, Tuple
import threading

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from locations import LOCATION_ID_TO_NAME

# Import database functions
try:
    import psycopg2
    from psycopg2.extras import Json
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  psycopg2-binary not installed. Database saving will be disabled.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Import HTTP client for API calls
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("⚠️  httpx not installed. API saving will be disabled. Install with: pip install httpx")


def str_to_bool(value: Optional[str]) -> bool:
    """Convert common truthy/falsey strings to boolean."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def extract_location_id_from_url(url):
    """
    Extract location_ids query parameter from URL.
    
    Args:
        url: Full URL string
    
    Returns:
        Location ID string, or None if not found
    """
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        location_ids = query_params.get('location_ids', [])
        if location_ids:
            # location_ids can be a list, get the first one
            return location_ids[0] if isinstance(location_ids, list) else location_ids
        return None
    except Exception as e:
        print(f"⚠️  Error extracting location_id from URL: {e}")
        return None


def get_location_name(location_id):
    """
    Get location name from location ID using the mapping.
    
    Args:
        location_id: Location ID string
    
    Returns:
        Location name string, or "Unknown Location" if not found
    """
    return LOCATION_ID_TO_NAME.get(location_id, f"Unknown Location ({location_id})")


def get_db_connection():
    """Get PostgreSQL database connection from environment variables.
    
    Supports two methods:
    1. DATABASE_URL (recommended for cloud deployments like Aptible)
       Format: postgresql://user:password@host:port/database
    2. Individual environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    """
    if not DB_AVAILABLE:
        return None
    
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
            print(f"   ⚠️  Error parsing DATABASE_URL: {e}")
            print("   DATABASE_URL format should be: postgresql://user:password@host:port/database")
            return None
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
        return conn
    except psycopg2.Error as e:
        print(f"   ⚠️  Database connection error: {e}")
        return None


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


STATUS_ALIAS_MAP = {
    "mark_as_ready": "ready",
    "mark_ready": "ready",
    "ready_for_visit": "ready",
    "ready_to_be_seen": "ready",
    "check_in": "checked_in",
    "checkedin": "checked_in",
    "in_room": "in_exam_room",
    "in_room_exam": "in_exam_room",
    "inroom": "in_exam_room",
}


def normalize_status_value(status: Any) -> Optional[str]:
    """Normalize queue status text to lowercase underscore format with known aliases."""
    if status is None:
        return None

    if isinstance(status, str):
        text = status.strip()
    else:
        text = str(status).strip()

    if not text:
        return None

    normalized = text.lower().replace(" ", "_").replace("-", "_")
    return STATUS_ALIAS_MAP.get(normalized, normalized)


def _sanitize_emr_value(value: Any) -> Optional[str]:
    """Convert a raw EMR value into a cleaned string representation."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if value.is_integer():
            text = str(int(value))
        else:
            text = f"{value}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    text = text.strip()
    return text or None


def extract_emr_id(record: Any) -> Optional[str]:
    """
    Attempt to extract an EMR ID from a nested patient payload.
    Prioritises explicit EMR fields, then integration status details,
    then patient match metadata, finally falling back to any key that
    resembles an EMR identifier.
    """
    if not isinstance(record, (dict, list)):
        return None

    candidates: List[Tuple[int, str]] = []
    visited: Set[int] = set()

    priority_fields = (
        ("emr_id", 0),
        ("emrId", 0),
        ("emrID", 0),
        ("emrid", 0),
    )

    def add_candidate(raw: Any, priority: int) -> None:
        cleaned = _sanitize_emr_value(raw)
        if cleaned:
            candidates.append((priority, cleaned))

    def walk(node: Any, depth: int = 0) -> None:
        node_id = id(node)
        if node_id in visited:
            return
        visited.add(node_id)

        if isinstance(node, dict):
            for field, base_priority in priority_fields:
                if field in node:
                    add_candidate(node.get(field), base_priority + depth)

            integration = node.get("integration_status") or node.get("integrationStatus")
            if isinstance(integration, list):
                for item in integration:
                    if isinstance(item, dict):
                        add_candidate(item.get("emr_id") or item.get("emrId"), 2 + depth)
                        requests = item.get("requests")
                        if isinstance(requests, list):
                            for request in requests:
                                if isinstance(request, dict):
                                    add_candidate(
                                        request.get("patient_number")
                                        or request.get("patientNumber")
                                        or request.get("emr_id")
                                        or request.get("emrId"),
                                        6 + depth,
                                    )

            patient_match = node.get("patient_match_details") or node.get("patientMatchDetails")
            if isinstance(patient_match, dict):
                add_candidate(patient_match.get("external_user_profile_id"), 4 + depth)
                add_candidate(patient_match.get("patient_number") or patient_match.get("patientNumber"), 7 + depth)

            raw_payload = node.get("raw_payload")
            if isinstance(raw_payload, (dict, list)):
                walk(raw_payload, depth + 1)

            for key, value in node.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in ("emr_id", "emrid")):
                    add_candidate(value, 3 + depth)
                elif key_lower in {"external_user_profile_id", "patient_number", "patientnumber"}:
                    add_candidate(value, 8 + depth)

                if key not in {"integration_status", "integrationStatus", "patient_match_details", "patientMatchDetails", "raw_payload"}:
                    if isinstance(value, (dict, list)):
                        walk(value, depth + 1)

        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(record, 0)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def normalize_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize patient record from JSON to database format."""
    emr_id = extract_emr_id(record)

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
        'reason_for_visit': record.get('reasonForVisit') or record.get('reason_for_visit') or record.get('reason') or None,
        'status': normalize_status_value(
            record.get('status') or
            record.get('patient_status') or
            record.get('status_class') or
            record.get('statusLabel') or
            record.get('status_label')
        )
    }

    # Clean up empty strings to None
    for key, value in list(normalized.items()):
        if isinstance(value, str):
            value = value.strip()
            normalized[key] = value or None

    return normalized


def ensure_db_tables_exist(conn):
    """Ensure database tables exist, create them if they don't."""
    if not conn:
        return False
    
    try:
        schema_file = Path(__file__).parent / 'db_schema.sql'
        
        if not schema_file.exists():
            print(f"   ⚠️  Schema file not found: {schema_file}")
            return False
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        # Remove CREATE DATABASE command if present (we're already connected)
        schema_sql = schema_sql.replace('CREATE DATABASE', '-- CREATE DATABASE')
        schema_sql = schema_sql.replace('\\c', '-- \\c')
        
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        # Table might already exist, which is fine
        if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
            return True
        print(f"   ⚠️  Error ensuring tables exist: {e}")
        conn.rollback()
        return False


def _serialize_patient_payload(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON-serializable copy of the patient payload."""
    try:
        return json.loads(json.dumps(patient_data, default=str))
    except (TypeError, ValueError):
        # Fallback: convert datetimes manually
        serializable = {}
        for key, value in patient_data.items():
            if isinstance(value, datetime):
                serializable[key] = value.isoformat()
            else:
                serializable[key] = value
        return serializable


def persist_pending_patient(patient_data: Dict[str, Any]) -> Optional[int]:
    """Insert a pending patient record and return its pending_id."""
    if not DB_AVAILABLE:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        ensure_db_tables_exist(conn)

        normalized = normalize_patient_record(patient_data)
        raw_payload = _serialize_patient_payload(patient_data)

        cursor = conn.cursor()
        cursor.execute(
            """
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
            RETURNING pending_id
            """,
            (
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
                normalized['reason_for_visit'],
                Json(raw_payload),
                'pending'
            )
        )
        pending_id_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        if pending_id_row:
            return pending_id_row[0]
        return None
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error saving pending patient: {e}")
        return None
    finally:
        conn.close()


def update_pending_patient_record(
    patient_data: Dict[str, Any],
    status: Optional[str] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update an existing pending patient entry."""
    if not DB_AVAILABLE:
        return False

    pending_id = patient_data.get('pending_id')
    if not pending_id:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        normalized = normalize_patient_record(patient_data)
        raw_payload = _serialize_patient_payload(patient_data)

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE pending_patients
            SET emr_id = %s,
                booking_id = %s,
                booking_number = %s,
                patient_number = %s,
                location_id = %s,
                location_name = %s,
                legal_first_name = %s,
                legal_last_name = %s,
                dob = %s,
                mobile_phone = %s,
                sex_at_birth = %s,
                captured_at = %s,
                reason_for_visit = %s,
                raw_payload = %s,
                status = COALESCE(%s, status),
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE pending_id = %s
            """,
            (
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
                normalized['reason_for_visit'],
                Json(raw_payload),
                status,
                error_message,
                pending_id
            )
        )
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        return updated
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient: {e}")
        return False
    finally:
        conn.close()


def mark_pending_patient_status(
    pending_id: int,
    status: str,
    error_message: Optional[str] = None
) -> bool:
    """Update only the status/error message for a pending patient."""
    if not DB_AVAILABLE:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE pending_patients
            SET status = %s,
                error_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE pending_id = %s
            """,
            (status, error_message, pending_id)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        return updated
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient status: {e}")
        return False
    finally:
        conn.close()


def update_pending_status_by_identifiers(
    status: str,
    *,
    booking_id: Optional[str] = None,
    booking_number: Optional[str] = None,
    patient_number: Optional[str] = None,
    emr_id: Optional[str] = None,
) -> List[int]:
    """
    Update pending patients' status using identifiers when pending_id is unknown.

    Returns list of pending_id values that were updated.
    """
    if not DB_AVAILABLE:
        return []

    status_normalized = normalize_status_value(status)
    if not status_normalized:
        return []

    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
        else:
            cleaned = str(value).strip()
        return cleaned or None

    identifiers: List[Tuple[str, Optional[str]]] = [
        ("booking_id", _clean(booking_id)),
        ("booking_number", _clean(booking_number)),
        ("patient_number", _clean(patient_number)),
        ("emr_id", _clean(emr_id)),
    ]

    conditions = []
    params: List[str] = []
    for column, value in identifiers:
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)

    if not conditions:
        return []

    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = f"""
            UPDATE pending_patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE {" OR ".join(conditions)}
            RETURNING pending_id
        """
        cursor.execute(query, (status_normalized, *params))
        rows = cursor.fetchall()
        conn.commit()
        cursor.close()

        updated_ids = [row[0] for row in rows] if rows else []
        if updated_ids:
            print(f"   💾 Updated pending patient status to '{status_normalized}' for pending_id(s): {updated_ids}")
        return updated_ids
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating pending patient status by identifiers: {e}")
        return []
    finally:
        conn.close()


def update_patient_status_by_identifiers(
    status: str,
    *,
    booking_id: Optional[str] = None,
    booking_number: Optional[str] = None,
    patient_number: Optional[str] = None,
    emr_id: Optional[str] = None,
) -> List[int]:
    """
    Update patients table status using identifiers.

    Returns list of patient ids that were updated.
    """
    if not DB_AVAILABLE:
        return []

    status_normalized = normalize_status_value(status)
    if not status_normalized:
        return []

    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
        else:
            cleaned = str(value).strip()
        return cleaned or None

    identifiers: List[Tuple[str, Optional[str]]] = [
        ("booking_id", _clean(booking_id)),
        ("booking_number", _clean(booking_number)),
        ("patient_number", _clean(patient_number)),
        ("emr_id", _clean(emr_id)),
    ]

    conditions = []
    params: List[str] = []
    for column, value in identifiers:
        if value:
            conditions.append(f"{column} = %s")
            params.append(value)

    if not conditions:
        return []

    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = f"""
            UPDATE patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE {" OR ".join(conditions)}
            RETURNING id
        """
        cursor.execute(query, (status_normalized, *params))
        rows = cursor.fetchall()
        conn.commit()
        cursor.close()

        updated_ids = [row[0] for row in rows] if rows else []
        if updated_ids:
            print(f"   💾 Updated patients status to '{status_normalized}' for id(s): {updated_ids}")
        return updated_ids
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error updating patients status by identifiers: {e}")
        return []
    finally:
        conn.close()


def find_pending_patient_id(patient_data: Dict[str, Any]) -> Optional[int]:
    """Attempt to locate the pending patient row matching provided data."""
    if not DB_AVAILABLE:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        normalized = normalize_patient_record(patient_data)

        # Prefer exact booking identifiers when available
        for column in ('booking_id', 'booking_number', 'patient_number'):
            value = normalized.get(column)
            if value:
                cursor.execute(
                    f"""
                    SELECT pending_id
                    FROM pending_patients
                    WHERE status IN ('pending', 'ready')
                      AND {column} = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (value,)
                )
                row = cursor.fetchone()
                if row:
                    conn.commit()
                    cursor.close()
                    return row[0]

        # Fall back to matching by name + captured_at timestamp
        first = normalized.get('legal_first_name')
        last = normalized.get('legal_last_name')
        captured_at = normalized.get('captured_at')

        if first and last and captured_at:
            cursor.execute(
                """
                SELECT pending_id
                FROM pending_patients
                WHERE status IN ('pending', 'ready')
                  AND LOWER(COALESCE(legal_first_name, '')) = LOWER(%s)
                  AND LOWER(COALESCE(legal_last_name, '')) = LOWER(%s)
                  AND captured_at = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (first, last, captured_at)
            )
            row = cursor.fetchone()
            if row:
                conn.commit()
                cursor.close()
                return row[0]

        # As a last resort, match by recent pending entries without EMR ID
        cursor.execute(
            """
            SELECT pending_id
            FROM pending_patients
            WHERE status IN ('pending', 'ready')
              AND emr_id IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.commit()
        cursor.close()
        if row:
            return row[0]
        return None
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def save_patient_to_db(patient_data: Dict[str, Any], on_conflict: str = 'update') -> bool:
    """
    Save a single patient record to PostgreSQL database.
    
    Args:
        patient_data: Dictionary with patient data
        on_conflict: What to do on conflict ('ignore' or 'update')
    
    Returns:
        True if saved successfully, False otherwise
    """
    if not DB_AVAILABLE:
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        # Ensure tables exist
        ensure_db_tables_exist(conn)
        
        normalized = normalize_patient_record(patient_data)

        if not normalized.get('emr_id'):
            print("   ⚠️  Skipping database save: missing emr_id")
            return False

        cursor = conn.cursor()

        if normalized['emr_id']:
            lookup_fields: List[Tuple[str, Optional[str]]] = [
                ("booking_id", normalized.get('booking_id')),
                ("booking_number", normalized.get('booking_number')),
                ("patient_number", normalized.get('patient_number')),
            ]
            for column, value in lookup_fields:
                if not value:
                    continue
                cursor.execute(
                    f"""
                    SELECT id, emr_id
                    FROM patients
                    WHERE {column} = %s
                    ORDER BY updated_at DESC NULLS LAST, captured_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (value,)
                )
                existing = cursor.fetchone()
                if existing:
                    existing_id, existing_emr = existing
                    if existing_emr != normalized['emr_id']:
                        cursor.execute(
                            """
                            UPDATE patients
                            SET emr_id = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (normalized['emr_id'], existing_id)
                        )
                    break

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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

        values = (
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
        )

        cursor.execute(insert_query, values)
        conn.commit()
        cursor.close()
        
        print(f"   💾 Saved to database (EMR ID: {normalized['emr_id']})")
        return True
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"   ⚠️  Database error: {e}")
        return False
    except Exception as e:
        print(f"   ⚠️  Error saving to database: {e}")
        return False
    finally:
        if conn:
            conn.close()


async def capture_form_data(page):
    """
    Capture all form field values from the patient modal.
    
    Args:
        page: Playwright page object
    
    Returns:
        Dictionary with captured form data
    """
    form_data = {}
    
    try:
        # Wait for the modal to be visible
        # The modal might have various selectors, try common ones
        modal_selectors = [
            '[role="dialog"]',
            '.modal',
            '[data-testid*="modal"]',
            '[class*="Modal"]',
        ]
        
        modal_visible = False
        for selector in modal_selectors:
            try:
                await page.wait_for_selector(selector, timeout=2000, state="visible")
                modal_visible = True
                break
            except PlaywrightTimeoutError:
                continue
        
        if not modal_visible:
            print("⚠️  Modal not found, trying to capture data anyway...")
        
        # Capture text input fields - using actual field names from HTML
        field_mappings = [
            {
                'key': 'legalFirstName',
                'selectors': [
                    '[name="firstName"]',
                    '[data-testid="addPatientFirstName"]',
                    'input[name="firstName"]',
                    'input[data-testid="addPatientFirstName"]'
                ]
            },
            {
                'key': 'legalLastName',
                'selectors': [
                    '[name="lastName"]',
                    '[data-testid="addPatientLastName"]',
                    'input[name="lastName"]',
                    'input[data-testid="addPatientLastName"]'
                ]
            },
            {
                'key': 'mobilePhone',
                'selectors': [
                    '[data-testid="addPatientMobilePhone"]',
                    '[name="phone"]',
                    'input[type="tel"][data-testid*="Phone"]',
                    'input[data-testid="addPatientMobilePhone"]'
                ]
            },
            {
                'key': 'dob',
                'selectors': [
                    '[data-testid="addPatientDob"]',
                    '[name="birthDate"]',
                    'input[placeholder*="MM/DD/YYYY"]',
                    'input[data-testid="addPatientDob"]'
                ]
            },
            {
                'key': 'reasonForVisit',
                'selectors': [
                    '[name="reasonForVisit"]',
                    '[data-testid*="addPatientReasonForVisit"]',
                    '[id="reasonForVisit"]',
                    '[data-testid="addPatientReasonForVisit-0"]',
                    'input[name="reasonForVisit"]',
                    'input[id="reasonForVisit"]'
                ]
            }
        ]
        
        for field in field_mappings:
            try:
                value = None
                for selector in field['selectors']:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            value = await element.input_value()
                            if value and value.strip():
                                break
                    except Exception:
                        continue
                
                form_data[field['key']] = value or ""
            except Exception as e:
                print(f"⚠️  Error capturing {field['key']}: {e}")
                form_data[field['key']] = ""
        
        # Capture dropdown/select field (sexAtBirth) - using actual field name "birthSex"
        try:
            sex_selectors = [
                '#birthSex',
                '[id="birthSex"]',
                '[name="birthSex"]',
                '[data-testid*="birthSex"]',
                'select[name="birthSex"]',
                'select[id="birthSex"]',
            ]
            
            sex_value = None
            for selector in sex_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        # Check if it's a select element
                        tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                        if tag_name == 'select':
                            sex_value = await element.evaluate('el => el.value')
                        else:
                            # For Ant Design custom dropdown, get the selected value
                            sex_value = await element.evaluate("""
                                (el) => {
                                    // Method 1: Check for selected-value element (most reliable for Ant Design)
                                    const selectedValueEl = el.querySelector('.ant-select-selection-selected-value');
                                    if (selectedValueEl) {
                                        const selectedText = (selectedValueEl.textContent || selectedValueEl.innerText || '').trim();
                                        if (selectedText && selectedText.length > 0) {
                                            return selectedText;
                                        }
                                        // Also try title attribute
                                        const title = selectedValueEl.getAttribute('title');
                                        if (title) return title;
                                    }
                                    
                                    // Method 2: Check the rendered container
                                    const rendered = el.querySelector('.ant-select-selection__rendered');
                                    const placeholder = el.querySelector('.ant-select-selection__placeholder');
                                    
                                    if (rendered) {
                                        // Check if placeholder is hidden (meaning something is selected)
                                        let isPlaceholderHidden = false;
                                        if (placeholder) {
                                            const placeholderStyle = window.getComputedStyle(placeholder);
                                            isPlaceholderHidden = placeholderStyle.display === 'none';
                                        }
                                        
                                        if (isPlaceholderHidden || !placeholder) {
                                            // Get all text from rendered
                                            const allText = rendered.textContent || rendered.innerText || '';
                                            // Remove placeholder text if it exists
                                            const placeholderText = placeholder ? (placeholder.textContent || placeholder.innerText || '') : '';
                                            const cleanText = allText.replace(placeholderText, '').trim();
                                            
                                            if (cleanText && !cleanText.includes('Choose an option') && cleanText.length > 0) {
                                                return cleanText;
                                            }
                                        }
                                    }
                                    
                                    // Method 3: Check if dropdown is open and get selected option
                                    const dropdown = el.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
                                    if (dropdown) {
                                        const selectedOption = dropdown.querySelector('.ant-select-item-selected, .ant-select-item-option-selected');
                                        if (selectedOption) {
                                            const optionText = (selectedOption.textContent || selectedOption.innerText || '').trim();
                                            if (optionText) return optionText;
                                        }
                                    }
                                    
                                    // Method 4: Look for hidden input or form field
                                    const hiddenInput = el.querySelector('input[type="hidden"]');
                                    if (hiddenInput && hiddenInput.value) {
                                        return hiddenInput.value;
                                    }
                                    
                                    // Method 5: Check Ant Design's internal state
                                    const antSelect = el.closest('.ant-select');
                                    if (antSelect) {
                                        const hiddenInput = antSelect.querySelector('input[type="hidden"]');
                                        if (hiddenInput && hiddenInput.value) {
                                            return hiddenInput.value;
                                        }
                                    }
                                    
                                    // Method 6: Check data attributes
                                    return el.getAttribute('data-value') || 
                                           el.getAttribute('value') || 
                                           el.getAttribute('aria-label') || '';
                                }
                            """)
                        if sex_value and sex_value.strip():
                            break
                except Exception:
                    continue
            
            form_data['sexAtBirth'] = sex_value or ""
        except Exception as e:
            print(f"⚠️  Error capturing sexAtBirth: {e}")
            form_data['sexAtBirth'] = ""
        
        return form_data
        
    except Exception as e:
        print(f"⚠️  Error capturing form data: {e}")
        return form_data


# Track recently sent EMR IDs to prevent duplicates (in-memory cache)
_recently_sent_emr_ids: Set[str] = set()
_recently_sent_lock = threading.Lock()

def check_if_patient_recently_sent(emr_id: str, minutes_threshold: int = 5) -> bool:
    """
    Check if a patient with this EMR ID was recently sent to the API.
    Checks both in-memory cache and database.
    
    Args:
        emr_id: EMR ID to check
        minutes_threshold: How many minutes back to check (default 5)
        
    Returns:
        True if recently sent, False otherwise
    """
    if not emr_id:
        return False
    
    # Check in-memory cache first (fast)
    with _recently_sent_lock:
        if emr_id in _recently_sent_emr_ids:
            return True
    
    # Check database for recently created records
    if not DB_AVAILABLE:
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        # Check if patient was created/updated in the last N minutes
        # Use PostgreSQL interval syntax
        cursor.execute(f"""
            SELECT id, created_at, updated_at
            FROM patients
            WHERE emr_id = %s
            AND (created_at > NOW() - INTERVAL '{minutes_threshold} minutes' 
                 OR updated_at > NOW() - INTERVAL '{minutes_threshold} minutes')
            ORDER BY created_at DESC
            LIMIT 1
        """, (emr_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            # Add to in-memory cache
            with _recently_sent_lock:
                _recently_sent_emr_ids.add(emr_id)
            return True
        
        return False
    except Exception as e:
        # If check fails, don't block sending (fail open)
        print(f"   ⚠️  Error checking for duplicate: {e}")
        return False
    finally:
        conn.close()


async def send_patient_to_api(patient_data: Dict[str, Any]) -> bool:
    """
    Send patient data to the API endpoint when EMR ID is available.
    Prevents duplicate sends by checking if patient was recently sent.
    
    Args:
        patient_data: Dictionary with patient data (must have emr_id)
        
    Returns:
        True if sent successfully, False otherwise
    """
    if not HTTPX_AVAILABLE:
        return False
    
    # Only send if EMR ID is present
    emr_id = patient_data.get('emr_id')
    if not emr_id:
        return False
    
    # Check for duplicates before sending
    if check_if_patient_recently_sent(emr_id):
        print(f"   ⏭️  Skipping duplicate: Patient with EMR ID {emr_id} was recently sent to API")
        return True  # Return True since it's already in the system
    
    # Get API URL from environment variables
    api_host = os.getenv('API_HOST', 'localhost')
    api_port = os.getenv('API_PORT', '8000')
    
    # Try to detect API port from run_all.py output or check common ports
    if api_port == '8000':
        # Check if API is running on alternative ports
        import socket
        for port in [8000, 8001, 8002, 8003, 8004]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                result = sock.connect_ex((api_host, port))
                sock.close()
                if result == 0:
                    # Port is open, try to verify it's our API by checking root endpoint
                    try:
                        import httpx
                        # Use root endpoint / which doesn't require parameters
                        response = httpx.get(f"http://{api_host}:{port}/", timeout=1.0)
                        if response.status_code in [200, 400, 401, 403, 404, 500]:  # Any HTTP response means API is there
                            api_port = str(port)
                            print(f"   🔍 Detected API server on port {port}")
                            break
                    except:
                        # If HTTP check fails, just use the port if it's open
                        # (might be our API but not responding to HTTP yet)
                        api_port = str(port)
                        print(f"   🔍 Port {port} is open, assuming API server")
                        break
            except:
                pass
    
    api_url = f"http://{api_host}:{api_port}/patients/create"
    
    # Get API token/key if authentication is enabled
    api_token = os.getenv('API_TOKEN')
    api_key = os.getenv('API_KEY')
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Add authentication if available
    if api_token:
        headers['Authorization'] = f'Bearer {api_token}'
    elif api_key:
        headers['X-API-Key'] = api_key
    
    # Prepare patient data for API (convert to API format)
    api_payload = {
        'emr_id': patient_data.get('emr_id') or '',
        'booking_id': patient_data.get('booking_id') or '',
        'booking_number': patient_data.get('booking_number') or '',
        'patient_number': patient_data.get('patient_number') or '',
        'location_id': patient_data.get('location_id') or '',
        'location_name': patient_data.get('location_name') or '',
        'legalFirstName': patient_data.get('legalFirstName') or patient_data.get('legal_first_name') or '',
        'legalLastName': patient_data.get('legalLastName') or patient_data.get('legal_last_name') or '',
        'dob': patient_data.get('dob') or '',
        'mobilePhone': patient_data.get('mobilePhone') or patient_data.get('mobile_phone') or '',
        'sexAtBirth': patient_data.get('sexAtBirth') or patient_data.get('sex_at_birth') or '',
        'reasonForVisit': patient_data.get('reasonForVisit') or patient_data.get('reason_for_visit') or '',
        'status': patient_data.get('status') or 'checked_in',
        'captured_at': patient_data.get('captured_at') or datetime.now().isoformat()
    }
    
    # Remove empty strings and convert to None for optional fields
    api_payload = {k: v if v else None for k, v in api_payload.items()}
    
    print(f"   📤 API Request Details:")
    print(f"      URL: {api_url}")
    print(f"      Method: POST")
    print(f"      Payload: {json.dumps(api_payload, indent=2, default=str)}")
    print(f"      Headers: {json.dumps(headers, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"   🔄 Sending HTTP request...")
            response = await client.post(api_url, json=api_payload, headers=headers)
            print(f"   📥 Response received: {response.status_code}")
            
            if response.status_code in [200, 201]:
                result = response.json()
                emr_id_sent = api_payload.get('emr_id')
                print(f"   ✅ Patient data sent to API successfully (EMR ID: {emr_id_sent})")
                # Mark as recently sent to prevent duplicates
                if emr_id_sent:
                    with _recently_sent_lock:
                        _recently_sent_emr_ids.add(emr_id_sent)
                return True
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get('detail', error_detail)
                except:
                    pass
                print(f"   ⚠️  API returned error {response.status_code}: {error_detail}")
                return False
                
    except httpx.TimeoutException:
        print(f"   ⚠️  API request timed out after 30 seconds")
        return False
    except httpx.RequestError as e:
        print(f"   ⚠️  API request error: {e}")
        return False
    except Exception as e:
        print(f"   ⚠️  Error sending to API: {e}")
        return False


async def save_patient_data(data) -> Optional[int]:
    """Persist patient data to the pending_patients staging table."""
    try:
        # Ensure captured_at is set so we can match the record later
        if not data.get('captured_at'):
            data['captured_at'] = datetime.now().isoformat()

        print("   💾 Saving patient submission to pending_patients staging table")

        pending_id = persist_pending_patient(data)
        if not pending_id:
            print("   ❌ Failed to persist patient submission to database")
            return None

        data['pending_id'] = pending_id
        print(f"✅ Pending patient saved (pending_id={pending_id})")

        if data.get('emr_id'):
            print("   📎 EMR ID already available, sending to API and saving to patients table")
            
            # Send to API first (when EMR ID is present)
            use_api = str_to_bool(os.getenv('USE_API', 'true'))
            if use_api and HTTPX_AVAILABLE:
                print("   📡 Sending patient data to API...")
                api_success = await send_patient_to_api(data)
                if api_success:
                    print("   ✅ Patient data successfully sent to API")
                else:
                    print("   ⚠️  Failed to send to API, will still save to database")
            elif use_api and not HTTPX_AVAILABLE:
                print("   ⚠️  API saving requested but httpx not available. Install with: pip install httpx")
            
            # Also save to database
            saved = save_patient_to_db(data, on_conflict='update')
            if saved:
                mark_pending_patient_status(pending_id, 'completed')
            else:
                mark_pending_patient_status(pending_id, 'error', 'Failed to upsert into patients table')
        else:
            mark_pending_patient_status(pending_id, 'pending')
            print("   ⏳ Waiting for EMR ID before inserting into patients table")

        return pending_id

    except Exception as e:
        print(f"❌ Error saving patient data: {e}")
        import traceback
        traceback.print_exc()
        return None


async def setup_form_monitor(page, location_id, location_name):
    """
    Set up JavaScript event listener to monitor form submissions.
    
    Args:
        page: Playwright page object
        location_id: Location ID from URL
        location_name: Location name from mapping
    """
    
    # Track pending patients waiting for EMR ID
    pending_patients = []
    
    # Expose a Python function to JavaScript
    async def handle_patient_submission(form_data):
        """
        Callback function called from JavaScript when form is submitted.
        """
        print(f"\n{'='*60}")
        print(f"🎯 PATIENT FORM SUBMITTED!")
        print(f"{'='*60}")
        print(f"   Raw form data received: {form_data}")
        
        # Re-extract location_id from current URL in case user changed location
        current_url = page.url
        current_location_id = extract_location_id_from_url(current_url) or location_id
        if current_location_id:
            current_location_name = get_location_name(current_location_id) or f"Location {current_location_id}"
        else:
            current_location_name = "Unknown Location"
        
        print(f"   Location ID: {current_location_id}")
        print(f"   Location: {current_location_name}")
        
        # Add location information to the data
        complete_data = {
            'location_id': current_location_id,
            'location_name': current_location_name,
            'emr_id': '',  # Will be filled later
            'booking_id': form_data.get('booking_id', '') if isinstance(form_data, dict) else '',
            'booking_number': form_data.get('booking_number', '') if isinstance(form_data, dict) else '',
            'patient_number': form_data.get('patient_number', '') if isinstance(form_data, dict) else '',
            **form_data
        }
        
        print(f"   Complete data to save: {complete_data}")
        
        # Save the data first and capture the pending_id for future updates
        pending_id = await save_patient_data(complete_data)
        if not pending_id:
            print("   ❌ Failed to persist patient submission; skipping EMR monitoring")
            return
        complete_data['pending_id'] = pending_id
        
        # Add to pending patients list for EMR ID monitoring
        pending_patients.append(complete_data)
        print(f"   📋 Added to pending patients list (total: {len(pending_patients)})")
        print(f"   ⏳ Now monitoring API responses for EMR ID assignment...")
        print(f"   💡 EMR ID typically appears 60-120 seconds after form submission")
        print(f"{'='*60}\n")
        
        # Start background task to wait for EMR ID (as fallback)
        asyncio.create_task(wait_for_emr_id(complete_data))
    
    # Expose the function to the page
    await page.expose_function("handlePatientSubmission", handle_patient_submission)
    
    async def wait_for_emr_id(patient_data):
        """
        Wait for the EMR ID to appear in API responses.
        Monitors network responses instead of opening the modal.
        
        Args:
            patient_data: Dictionary with patient data that was just saved
        """
        try:
            print(f"\n⏳ Waiting for EMR ID to be assigned via API...")
            print(f"   Patient: {patient_data.get('legalFirstName', '')} {patient_data.get('legalLastName', '')}")
            
            patient_first_name = patient_data.get('legalFirstName', '').strip()
            patient_last_name = patient_data.get('legalLastName', '').strip()
            captured_at = patient_data.get('captured_at', '')
            
            # Wait for API response that contains EMR ID
            max_wait_time = 180  # Maximum 3 minutes
            poll_interval = 3  # Check every 3 seconds
            elapsed_time = 0
            
            print(f"   🔄 Monitoring API responses for EMR ID (checking every {poll_interval} seconds, max {max_wait_time} seconds)...")
            
            while elapsed_time < max_wait_time:
                try:
                    # Check API responses for EMR ID by looking at the queue data
                    emr_id = await page.evaluate("""
                        (firstName, lastName) => {
                            // Look for patient data in the DOM that might contain EMR ID
                            // Check if there's any data attribute or text containing EMR ID
                            const allElements = document.querySelectorAll('[data-testid*="patient"], [data-testid*="booking"]');
                            
                            for (const element of allElements) {
                                const text = element.textContent || element.innerText || '';
                                // Check if this element contains the patient name
                                if (firstName && lastName && text.includes(firstName) && text.includes(lastName)) {
                                    // Look for EMR ID in nearby elements or data attributes
                                    const parent = element.closest('[class*="booking"], [class*="patient"]');
                                    if (parent) {
                                        const parentText = parent.textContent || parent.innerText || '';
                                        const emrMatch = parentText.match(/EMR ID[\\s:]+(\\d+)/i);
                                        if (emrMatch && emrMatch[1]) {
                                            return emrMatch[1];
                                        }
                                    }
                                }
                            }
                            
                            return null;
                        }
                    """, patient_first_name, patient_last_name)
                    
                    if emr_id:
                        print(f"   ✅ EMR ID found in DOM: {emr_id}")
                        patient_data['emr_id'] = emr_id
                        await update_patient_emr_id(patient_data)
                        print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                        return
                
                except Exception as e:
                    print(f"   ⚠️  Error checking for EMR ID: {e}")
                
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                if elapsed_time % 15 == 0:  # Print status every 15 seconds
                    print(f"   ⏳ Still waiting for EMR ID... ({elapsed_time}s elapsed)")
            
            print(f"   ⚠️  EMR ID not found after {max_wait_time} seconds")
            
        except Exception as e:
            print(f"   ❌ Error waiting for EMR ID: {e}")
            import traceback
            traceback.print_exc()
    
    async def update_status_for_booking(
        status_value: Any,
        *,
        booking_id: Optional[str] = None,
        booking_number: Optional[str] = None,
        patient_number: Optional[str] = None,
        emr_id: Optional[str] = None,
        patient_first_name: str = "",
        patient_last_name: str = "",
        api_phone: Optional[str] = None,
    ) -> bool:
        """
        Update pending/patient records when queue status changes are detected.

        Returns True if at least one record was updated.
        """
        normalized_status = normalize_status_value(status_value)
        if not normalized_status:
            return False

        def _clean(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                cleaned = value.strip()
            else:
                cleaned = str(value).strip()
            return cleaned or None

        def _equals(a: Optional[str], b: Optional[str]) -> bool:
            if a is None or b is None:
                return False
            return a.strip().lower() == b.strip().lower()

        def _normalize_phone(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            digits = "".join(ch for ch in value if ch.isdigit())
            return digits or None

        booking_id_clean = _clean(booking_id)
        booking_number_clean = _clean(booking_number)
        patient_number_clean = _clean(patient_number)
        emr_id_clean = _clean(emr_id)
        patient_first_clean = _clean(patient_first_name)
        patient_last_clean = _clean(patient_last_name)
        api_phone_clean = _normalize_phone(api_phone)

        updated_pending_ids: Set[int] = set()
        updated_patient_ids: Set[int] = set()

        for pending in list(pending_patients):
            match = False

            pending_booking_id = _clean(pending.get('booking_id') or pending.get('bookingId'))
            pending_booking_number = _clean(pending.get('booking_number') or pending.get('bookingNumber'))
            pending_patient_number = _clean(pending.get('patient_number') or pending.get('patientNumber'))
            pending_emr_id = _clean(pending.get('emr_id'))

            if booking_id_clean and pending_booking_id and _equals(booking_id_clean, pending_booking_id):
                match = True
            elif booking_number_clean and pending_booking_number and _equals(booking_number_clean, pending_booking_number):
                match = True
            elif patient_number_clean and pending_patient_number and _equals(patient_number_clean, pending_patient_number):
                match = True
            elif emr_id_clean and pending_emr_id and _equals(emr_id_clean, pending_emr_id):
                match = True
            else:
                pending_first = _clean(pending.get('legalFirstName') or pending.get('legal_first_name'))
                pending_last = _clean(pending.get('legalLastName') or pending.get('legal_last_name'))
                pending_phone = _normalize_phone(pending.get('mobilePhone') or pending.get('mobile_phone'))

                name_match = (
                    pending_first
                    and pending_last
                    and patient_first_clean
                    and patient_last_clean
                    and _equals(pending_first, patient_first_clean)
                    and _equals(pending_last, patient_last_clean)
                )
                phone_match = (
                    api_phone_clean
                    and pending_phone
                    and api_phone_clean == pending_phone
                )

                if name_match or (phone_match and (patient_first_clean or patient_last_clean)):
                    match = True

            if match:
                pending['status'] = normalized_status
                pending_id = pending.get('pending_id')
                if pending_id:
                    if mark_pending_patient_status(pending_id, normalized_status):
                        updated_pending_ids.add(int(pending_id))
                else:
                    updated = update_pending_status_by_identifiers(
                        normalized_status,
                        booking_id=booking_id_clean or pending_booking_id,
                        booking_number=booking_number_clean or pending_booking_number,
                        patient_number=patient_number_clean or pending_patient_number,
                        emr_id=emr_id_clean or pending_emr_id,
                    )
                    updated_pending_ids.update(updated)

                updated_patient_ids.update(
                    update_patient_status_by_identifiers(
                        normalized_status,
                        booking_id=booking_id_clean or pending_booking_id,
                        booking_number=booking_number_clean or pending_booking_number,
                        patient_number=patient_number_clean or pending_patient_number,
                        emr_id=emr_id_clean or pending_emr_id,
                    )
                )

        if not updated_pending_ids:
            fallback_pending = update_pending_status_by_identifiers(
                normalized_status,
                booking_id=booking_id_clean,
                booking_number=booking_number_clean,
                patient_number=patient_number_clean,
                emr_id=emr_id_clean,
            )
            updated_pending_ids.update(fallback_pending)

        if not updated_patient_ids:
            fallback_patient_ids = update_patient_status_by_identifiers(
                normalized_status,
                booking_id=booking_id_clean,
                booking_number=booking_number_clean,
                patient_number=patient_number_clean,
                emr_id=emr_id_clean,
            )
            updated_patient_ids.update(fallback_patient_ids)

        if updated_pending_ids or updated_patient_ids:
            pending_msg = (
                f"pending_id(s): {sorted(updated_pending_ids)}"
                if updated_pending_ids else "pending_id(s): none"
            )
            patients_msg = (
                f"patient_id(s): {sorted(updated_patient_ids)}"
                if updated_patient_ids else "patient_id(s): none"
            )
            print(f"   ✅ Queue status updated to '{normalized_status}' ({pending_msg}; {patients_msg})")
            return True

        print(
            f"   ⚠️  Queue status '{normalized_status}' detected but no matching pending/patient record was found "
            f"(booking_id={booking_id_clean}, booking_number={booking_number_clean}, patient_number={patient_number_clean}, emr_id={emr_id_clean})"
        )
        return False

    async def update_patient_emr_id(patient_data):
        """Update the pending record with the EMR ID and promote it to patients table."""
        try:
            if not patient_data.get('pending_id'):
                pending_id = find_pending_patient_id(patient_data)
                if pending_id:
                    patient_data['pending_id'] = pending_id
                else:
                    print("   ⚠️  Pending record not found for EMR assignment")
                    return

            pending_id = patient_data['pending_id']

            updated = update_pending_patient_record(patient_data, status='ready')
            if not updated:
                print(f"   ⚠️  Failed to update pending patient (pending_id={pending_id}) with EMR ID")
                return

            # Send to API when EMR ID is found (THIS IS THE CRITICAL PART)
            use_api = str_to_bool(os.getenv('USE_API', 'true'))
            print(f"\n{'='*60}")
            print(f"🚀 CRITICAL: EMR ID FOUND - PREPARING TO SEND TO API")
            print(f"{'='*60}")
            print(f"   EMR ID: {patient_data.get('emr_id')}")
            print(f"   Patient: {patient_data.get('legalFirstName')} {patient_data.get('legalLastName')}")
            print(f"   USE_API: {use_api}")
            print(f"   HTTPX_AVAILABLE: {HTTPX_AVAILABLE}")
            print(f"   Patient data keys: {list(patient_data.keys())}")
            
            if use_api and HTTPX_AVAILABLE:
                print(f"   📡 Sending patient data to API...")
                api_success = await send_patient_to_api(patient_data)
                if api_success:
                    print(f"   ✅ Patient data successfully sent to API (EMR ID: {patient_data.get('emr_id')})")
                else:
                    print(f"   ⚠️  Failed to send to API, will still save to database")
            elif use_api and not HTTPX_AVAILABLE:
                print(f"   ⚠️  API saving requested but httpx not available. Install with: pip install httpx")
            else:
                print(f"   ⚠️  API sending disabled (USE_API={use_api})")
            print(f"{'='*60}\n")
            
            # Also save to database
            saved = save_patient_to_db(patient_data, on_conflict='update')
            if saved:
                mark_pending_patient_status(pending_id, 'completed')
                print(f"   ✅ Pending patient promoted to patients table (pending_id={pending_id})")
            else:
                mark_pending_patient_status(pending_id, 'error', 'Failed to upsert into patients table after EMR assignment')
                print(f"   ❌ Failed to insert pending patient into patients table (pending_id={pending_id})")

        except Exception as e:
            pending_id = patient_data.get('pending_id')
            if pending_id:
                mark_pending_patient_status(pending_id, 'error', str(e))
            print(f"   ❌ Error updating EMR ID in database: {e}")
            import traceback
            traceback.print_exc()
    
    # Set up a background task to periodically check for form submissions
    async def monitor_form_submissions():
        """Background task that polls for form submissions"""
        last_captured = None
        while True:
            try:
                await asyncio.sleep(0.5)  # Check every 500ms
                
                # Check if modal is visible
                modal_visible = await page.evaluate("""
                    () => {
                        const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                        return modal && window.getComputedStyle(modal).display !== 'none';
                    }
                """)
                
                if modal_visible:
                    # Try to capture form data
                    form_data = await capture_form_data(page)
                    
                    # Check if we have new data (at least one field filled)
                    if any(v and v.strip() for v in form_data.values() if v):
                        # Create a hash of the data to detect changes
                        data_hash = str(sorted(form_data.items()))
                        
                        if data_hash != last_captured:
                            # Check if form is being submitted (button might be disabled/loading)
                            is_submitting = await page.evaluate("""
                                () => {
                                    const button = document.querySelector('[data-testid="addPatientSubmitButton"]') ||
                                                   document.querySelector('button[data-testid*="addPatient"]') ||
                                                   document.querySelector('button[type="submit"]');
                                    if (!button) return false;
                                    const modal = button.closest('[role="dialog"], .modal, [class*="Modal"]');
                                    return modal && (button.disabled || button.getAttribute('aria-busy') === 'true');
                                }
                            """)
                            
                            # If button is in submitting state, capture the data
                            if is_submitting:
                                print(f"\n🔄 Form submission detected via polling!")
                                last_captured = data_hash
                                await handle_patient_submission(form_data)
            except Exception as e:
                # Silently continue on errors
                pass
    
    # Start the background monitoring task
    asyncio.create_task(monitor_form_submissions())
    print("✅ Background form monitoring started")
    
    # Intercept network responses to catch EMR ID from API calls
    async def handle_response(response):
        """Intercept API responses to extract EMR ID"""
        try:
            url = response.url
            status = response.status
            
            # Look for API responses that might contain patient/booking data with EMR ID
            # Check a wider range of URLs, especially booking endpoints
            url_lower = url.lower()
            is_solvhealth_api = "api-manage.solvhealth.com" in url_lower
            is_relevant = (
                status == 200 and (
                    is_solvhealth_api or
                    "patient" in url_lower or 
                    "booking" in url_lower or 
                    "bookings" in url_lower or
                    "queue" in url_lower or 
                    "appointment" in url_lower or
                    "appointments" in url_lower or
                    "facesheet" in url_lower or
                    "visit" in url_lower or
                    "/api/" in url_lower or
                    "api-manage.solvhealth.com" in url_lower
                )
            )
            
            if is_relevant:
                try:
                    # Try to get JSON response
                    response_body = await response.json()
                    
                    # Log intercepted responses for debugging
                    if is_solvhealth_api and "/bookings" in url_lower:
                        print(f"\n🔍 Intercepted Solvhealth API response:")
                        print(f"   URL: {url}")
                        print(f"   Status: {status}")
                        print(f"   📋 Response body structure: {type(response_body)}")
                        if isinstance(response_body, dict):
                            print(f"   📋 Response keys: {list(response_body.keys())}")
                            if 'data' in response_body:
                                data = response_body.get('data', {})
                                if isinstance(data, dict):
                                    print(f"   📋 Data keys: {list(data.keys())}")
                                    if 'integration_status' in data:
                                        print(f"   📋 Found integration_status in data")
                                    if isinstance(data.get('integration_status'), list) and data.get('integration_status'):
                                        integration = data.get('integration_status')[0]
                                        if isinstance(integration, dict):
                                            emr_id = integration.get('emr_id')
                                            print(f"   📋 integration_status[0].emr_id = {emr_id} (type: {type(emr_id)})")
                    
                    async def process_single_booking_record(record: Dict[str, Any]) -> bool:
                        """Process a single booking/queue record and update EMR/status as needed."""
                        emr_id_local: Optional[str] = None
                        patient_match_local: Optional[Dict[str, Any]] = None
                        booking_id_local = ""
                        booking_number_local = ""
                        patient_number_local = ""
                        api_phone_value = ""
                        all_patients_local: List[Dict[str, Any]] = []
                        status_update_success = False

                        booking_status_value = (
                            record.get('status') or
                            record.get('queue_status') or
                            record.get('booking_status') or
                            record.get('patient_status')
                        )

                        status_first_name = (
                            record.get('first_name') or
                            record.get('firstName') or
                            record.get('legalFirstName') or
                            record.get('firstname') or
                            ''
                        )
                        status_last_name = (
                            record.get('last_name') or
                            record.get('lastName') or
                            record.get('legalLastName') or
                            record.get('lastname') or
                            ''
                        )

                        possible_booking_id = record.get('id') or record.get('booking_id')
                        if possible_booking_id:
                            booking_id_local = str(possible_booking_id).strip()
                        if record.get('booking_number'):
                            booking_number_local = str(record.get('booking_number')).strip()
                        if record.get('patient_number'):
                            patient_number_local = str(record.get('patient_number')).strip()

                        api_phone_value = str(
                            record.get('phone') or
                            record.get('mobile_phone') or
                            record.get('phone_number') or
                            ''
                        ).strip()

                        if booking_status_value:
                            status_update_success = await update_status_for_booking(
                                booking_status_value,
                                booking_id=booking_id_local or None,
                                booking_number=booking_number_local or None,
                                patient_number=patient_number_local or None,
                                emr_id=None,
                                patient_first_name=status_first_name,
                                patient_last_name=status_last_name,
                                api_phone=api_phone_value,
                            )

                        integration_status = record.get('integration_status', [])
                        if isinstance(integration_status, list) and integration_status:
                            for integration in integration_status:
                                if not isinstance(integration, dict):
                                    continue
                                integration_emr_id = integration.get('emr_id')
                                # Only use EMR ID if it's not null/empty (check for actual value)
                                # JSON null becomes Python None, so check for both None and empty strings
                                if (integration_emr_id is not None and 
                                    str(integration_emr_id).strip() and 
                                    str(integration_emr_id).strip().lower() not in ('null', 'none', '') and 
                                    not emr_id_local):
                                    emr_id_local = str(integration_emr_id).strip()
                                    patient_match_local = record
                                    print(f"   📍 Found EMR ID in integration_status: {emr_id_local}")
                                    print(f"   📋 Integration status: {integration.get('status')}")
                                    print(f"   📋 Booking ID: {record.get('id')}")
                                    print(f"   📋 Patient: {record.get('first_name')} {record.get('last_name')}")
                                requests = integration.get('requests', [])
                                if isinstance(requests, list):
                                    for request in requests:
                                        if not isinstance(request, dict):
                                            continue
                                        if not booking_number_local:
                                            booking_value = request.get('booking_number') or request.get('bookingNumber')
                                            if booking_value:
                                                booking_number_local = str(booking_value).strip()
                                        if not patient_number_local:
                                            patient_value = request.get('patient_number') or request.get('patientNumber')
                                            if patient_value:
                                                patient_number_local = str(patient_value).strip()
                                if emr_id_local and booking_number_local and patient_number_local:
                                    break

                        if not emr_id_local:
                            patient_match_details = record.get('patient_match_details') or record.get('patientMatchDetails')
                            if isinstance(patient_match_details, dict):
                                external_user_profile_id = patient_match_details.get('external_user_profile_id')
                                if external_user_profile_id:
                                    emr_id_local = str(external_user_profile_id).strip()
                                    patient_match_local = record
                                    print(f"   📍 Found EMR ID in patient_match_details: {emr_id_local}")
                                if not patient_number_local:
                                    pm_patient_number = patient_match_details.get('patient_number') or patient_match_details.get('patientNumber')
                                    if pm_patient_number:
                                        patient_number_local = str(pm_patient_number).strip()

                        if not emr_id_local:
                            def find_emr_in_record(data: Any):
                                nonlocal emr_id_local, patient_match_local, all_patients_local
                                if isinstance(data, dict):
                                    for key, value in data.items():
                                        key_lower = str(key).lower()
                                        if ("emr" in key_lower or "emr_id" in key_lower or "emrid" in key_lower) and isinstance(value, (str, int)):
                                            candidate = str(value).strip()
                                            if candidate:
                                                emr_id_local = candidate
                                                patient_match_local = data
                                                return
                                        if isinstance(value, dict):
                                            if any(k in str(value.keys()).lower() for k in ['first', 'last', 'name', 'patient']):
                                                all_patients_local.append(value)
                                            find_emr_in_record(value)
                                        elif isinstance(value, list):
                                            find_emr_in_record(value)
                                elif isinstance(data, list):
                                    for item in data:
                                        find_emr_in_record(item)

                            find_emr_in_record(record)

                        if emr_id_local:
                            print(f"\n🌐 API response contains EMR ID: {emr_id_local}")
                            print(f"   URL: {url}")

                            patient_first_name = (
                                patient_match_local.get('first_name') or
                                patient_match_local.get('firstName') or
                                patient_match_local.get('legalFirstName') or
                                patient_match_local.get('firstname') or
                                ''
                            ) if patient_match_local else ''
                            patient_last_name = (
                                patient_match_local.get('last_name') or
                                patient_match_local.get('lastName') or
                                patient_match_local.get('legalLastName') or
                                patient_match_local.get('lastname') or
                                ''
                            ) if patient_match_local else ''

                            if patient_match_local:
                                if not booking_id_local:
                                    local_booking_id = patient_match_local.get('id') or patient_match_local.get('booking_id')
                                    if local_booking_id:
                                        booking_id_local = str(local_booking_id).strip()
                                if not booking_number_local and patient_match_local.get('booking_number'):
                                    booking_number_local = str(patient_match_local.get('booking_number')).strip()
                                if not patient_number_local and patient_match_local.get('patient_number'):
                                    patient_number_local = str(patient_match_local.get('patient_number')).strip()

                            if not patient_first_name and all_patients_local:
                                for candidate in all_patients_local:
                                    if emr_id_local in str(candidate.values()):
                                        patient_first_name = (
                                            candidate.get('firstName') or
                                            candidate.get('legalFirstName') or
                                            candidate.get('first_name') or
                                            ''
                                        )
                                        patient_last_name = (
                                            candidate.get('lastName') or
                                            candidate.get('legalLastName') or
                                            candidate.get('last_name') or
                                            ''
                                        )
                                        if patient_first_name or patient_last_name:
                                            break

                            if patient_first_name or patient_last_name:
                                print(f"   Patient: {patient_first_name} {patient_last_name}")

                            matched = False
                            for pending in list(pending_patients):
                                if pending.get('emr_id'):
                                    continue

                                pending_first = pending.get('legalFirstName', '').strip()
                                pending_last = pending.get('legalLastName', '').strip()

                                name_match = False
                                if patient_first_name and patient_last_name:
                                    name_match = (
                                        pending_first.lower() == patient_first_name.lower().strip() and
                                        pending_last.lower() == patient_last_name.lower().strip()
                                    )
                                elif patient_first_name:
                                    name_match = pending_first.lower() == patient_first_name.lower().strip()
                                elif patient_last_name:
                                    name_match = pending_last.lower() == patient_last_name.lower().strip()

                                phone_match = False
                                if api_phone_value:
                                    pending_phone = pending.get('mobilePhone', '').strip()
                                    if pending_phone:
                                        api_phone_norm = api_phone_value.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                        pending_phone_norm = pending_phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                        if api_phone_norm and pending_phone_norm and api_phone_norm == pending_phone_norm:
                                            phone_match = True

                                final_match = name_match or (phone_match and (patient_first_name or patient_last_name))

                                if not final_match:
                                    unmatched_pending = [p for p in pending_patients if not p.get('emr_id')]
                                    if len(unmatched_pending) == 1 and pending is unmatched_pending[0]:
                                        final_match = True

                                if final_match:
                                    print(f"   ✅ Matched with pending patient!")
                                    if name_match:
                                        print(f"      Match by name: {pending_first} {pending_last}")
                                    if phone_match:
                                        print(f"      Match by phone: {pending.get('mobilePhone', '').strip()}")
                                    
                                    # Update pending record with EMR ID and all booking data
                                    pending['emr_id'] = emr_id_local
                                    if booking_id_local:
                                        pending['booking_id'] = booking_id_local
                                    if booking_number_local:
                                        pending['booking_number'] = booking_number_local
                                    if patient_number_local:
                                        pending['patient_number'] = patient_number_local
                                    
                                    # Extract and merge all patient data from booking record
                                    if patient_match_local:
                                        # Map booking fields to patient data format
                                        if not pending.get('legalFirstName') and patient_match_local.get('first_name'):
                                            pending['legalFirstName'] = patient_match_local.get('first_name')
                                        if not pending.get('legalLastName') and patient_match_local.get('last_name'):
                                            pending['legalLastName'] = patient_match_local.get('last_name')
                                        if not pending.get('dob') and patient_match_local.get('birth_date'):
                                            pending['dob'] = patient_match_local.get('birth_date')
                                        if not pending.get('mobilePhone') and patient_match_local.get('phone'):
                                            pending['mobilePhone'] = patient_match_local.get('phone')
                                        if not pending.get('sexAtBirth') and patient_match_local.get('birth_sex'):
                                            pending['sexAtBirth'] = patient_match_local.get('birth_sex')
                                        if not pending.get('reasonForVisit') and patient_match_local.get('reason'):
                                            pending['reasonForVisit'] = patient_match_local.get('reason')
                                        if not pending.get('location_id') and patient_match_local.get('location_id'):
                                            pending['location_id'] = patient_match_local.get('location_id')
                                        if not pending.get('location_name') and patient_match_local.get('location_name'):
                                            pending['location_name'] = patient_match_local.get('location_name')
                                        if not pending.get('status') and patient_match_local.get('status'):
                                            pending['status'] = patient_match_local.get('status')
                                    
                                    # Send to API and update database
                                    print(f"\n   🔄 Calling update_patient_emr_id() with patient data...")
                                    print(f"      EMR ID: {pending.get('emr_id')}")
                                    print(f"      Patient: {pending.get('legalFirstName')} {pending.get('legalLastName')}")
                                    await update_patient_emr_id(pending)
                                    print(f"   💾 Updated patient data with EMR ID: {emr_id_local}")
                                    pending_patients.remove(pending)
                                    matched = True
                                    break

                            # ALWAYS send to API when EMR ID is found, even if no pending patient match
                            # (This handles cases where EMR ID appears but form wasn't submitted through our monitor)
                            if not matched and emr_id_local and patient_match_local:
                                # Extract complete patient data from booking record
                                patient_data_for_api = {
                                    'emr_id': emr_id_local,
                                    'booking_id': booking_id_local or patient_match_local.get('id') or patient_match_local.get('booking_id') or None,
                                    'booking_number': booking_number_local or patient_match_local.get('booking_number') or None,
                                    'patient_number': patient_number_local or patient_match_local.get('patient_number') or None,
                                    'location_id': patient_match_local.get('location_id') or None,
                                    'location_name': patient_match_local.get('location_name') or None,
                                    'legalFirstName': patient_match_local.get('first_name') or patient_match_local.get('firstName') or patient_match_local.get('legalFirstName') or patient_first_name or None,
                                    'legalLastName': patient_match_local.get('last_name') or patient_match_local.get('lastName') or patient_match_local.get('legalLastName') or patient_last_name or None,
                                    'dob': patient_match_local.get('birth_date') or patient_match_local.get('dateOfBirth') or patient_match_local.get('dob') or None,
                                    'mobilePhone': patient_match_local.get('phone') or patient_match_local.get('mobile_phone') or patient_match_local.get('mobilePhone') or api_phone_value or None,
                                    'sexAtBirth': patient_match_local.get('birth_sex') or patient_match_local.get('sexAtBirth') or patient_match_local.get('sex_at_birth') or None,
                                    'reasonForVisit': patient_match_local.get('reason') or patient_match_local.get('reasonForVisit') or patient_match_local.get('reason_for_visit') or None,
                                    'status': patient_match_local.get('status') or booking_status_value or 'checked_in',
                                    'captured_at': datetime.now().isoformat()
                                }
                                
                                # Remove None values
                                patient_data_for_api = {k: v for k, v in patient_data_for_api.items() if v is not None}
                                
                                print(f"\n   🚀 EMR ID found! Sending patient data to API immediately...")
                                print(f"      EMR ID: {emr_id_local}")
                                print(f"      Patient: {patient_data_for_api.get('legalFirstName')} {patient_data_for_api.get('legalLastName')}")
                                
                                # Send to API directly
                                use_api = str_to_bool(os.getenv('USE_API', 'true'))
                                if use_api and HTTPX_AVAILABLE:
                                    api_success = await send_patient_to_api(patient_data_for_api)
                                    if api_success:
                                        print(f"   ✅ Patient data successfully sent to API (EMR ID: {emr_id_local})")
                                    else:
                                        print(f"   ⚠️  Failed to send to API")
                                elif use_api and not HTTPX_AVAILABLE:
                                    print(f"   ⚠️  API saving requested but httpx not available")
                                
                                # Also save to database
                                try:
                                    saved = save_patient_to_db(patient_data_for_api, on_conflict='update')
                                    if saved:
                                        print(f"   ✅ Patient data also saved to database")
                                    else:
                                        print(f"   ⚠️  Failed to save to database")
                                except Exception as e:
                                    print(f"   ⚠️  Error saving to database: {e}")
                            
                            if not matched:
                                print(f"   📋 No matching pending patient found (pending patients: {len(pending_patients)})")
                                if len(pending_patients) > 0:
                                    pending_names = [f"{p.get('legalFirstName', '')} {p.get('legalLastName', '')}" for p in pending_patients]
                                    print(f"   💡 Pending patients: {pending_names}")

                        if booking_status_value and not status_update_success:
                            await update_status_for_booking(
                                booking_status_value,
                                booking_id=booking_id_local or None,
                                booking_number=booking_number_local or None,
                                patient_number=patient_number_local or None,
                                emr_id=emr_id_local,
                                patient_first_name=status_first_name,
                                patient_last_name=status_last_name,
                                api_phone=api_phone_value,
                            )

                        return bool(emr_id_local or status_update_success)

                    handled_any = False
                    if isinstance(response_body, dict) and 'data' in response_body:
                        booking_payload = response_body.get('data', {})
                        records = None
                        if isinstance(booking_payload, dict) and isinstance(booking_payload.get('results'), list):
                            records = booking_payload.get('results')
                        elif isinstance(booking_payload, list):
                            records = booking_payload

                        if records and isinstance(records, list):
                            for record in records:
                                if isinstance(record, dict) and await process_single_booking_record(record):
                                    handled_any = True
                        elif isinstance(booking_payload, dict):
                            # Handle single booking record in data.data (like Solvhealth API response)
                            # Check if it's a booking record (has id, location_id, etc.)
                            if booking_payload.get('id') or booking_payload.get('location_id'):
                                if await process_single_booking_record(booking_payload):
                                    handled_any = True

                    if not handled_any and isinstance(response_body, dict):
                        # Also try processing the root dict directly if it looks like a booking record
                        if (response_body.get('id') or response_body.get('location_id')) and await process_single_booking_record(response_body):
                            handled_any = True

                    if handled_any:
                        return
                
                except Exception as e:
                    # Not JSON or can't parse, skip silently
                    pass
                    
        except Exception as e:
            # Ignore errors in response handler
            pass
    
    # Set up response interception
    page.on("response", handle_response)
    print("✅ API response interception enabled")
    print(f"   📡 Actively monitoring all API responses for EMR ID...")
    
    # Also set up periodic DOM checking as active backup
    async def actively_check_dom_for_emr():
        """Periodically check DOM for EMR IDs that might have appeared"""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                if not pending_patients:
                    continue
                
                # Check the queue list for EMR IDs
                for pending in list(pending_patients):
                    if pending.get('emr_id'):
                        continue
                    
                    pending_first = pending.get('legalFirstName', '').strip()
                    pending_last = pending.get('legalLastName', '').strip()
                    
                    if not pending_first and not pending_last:
                        continue
                    
                    # Look for patient in DOM and check for EMR ID
                    emr_id = await page.evaluate("""
                        (firstName, lastName) => {
                            // Find patient name elements
                            const nameElements = document.querySelectorAll('[data-testid^="booking-patient-name-"]');
                            
                            for (const nameEl of nameElements) {
                                const text = nameEl.textContent || nameEl.innerText || '';
                                if (text.includes(firstName) && text.includes(lastName)) {
                                    // Look for EMR ID in the parent container
                                    const container = nameEl.closest('[class*="booking"], [class*="patient"], [data-testid*="booking"]');
                                    if (container) {
                                        const containerText = container.textContent || container.innerText || '';
                                        const emrMatch = containerText.match(/EMR ID[\\s:]+(\\d+)/i);
                                        if (emrMatch && emrMatch[1]) {
                                            return emrMatch[1];
                                        }
                                    }
                                }
                            }
                            return null;
                        }
                    """, pending_first, pending_last)
                    
                    if emr_id:
                        print(f"\n🔍 Found EMR ID in DOM: {emr_id}")
                        print(f"   Patient: {pending_first} {pending_last}")
                        pending['emr_id'] = emr_id
                        await update_patient_emr_id(pending)
                        print(f"   💾 Updated patient data with EMR ID: {emr_id}")
                        pending_patients.remove(pending)
            
            except Exception as e:
                # Silently continue on errors
                pass
    
    # Start active DOM monitoring
    asyncio.create_task(actively_check_dom_for_emr())
    print("✅ Active DOM monitoring started (checking every 5 seconds)")
    
    # Inject JavaScript to monitor the submit button
    monitor_script = """
    (function() {
        console.log('🔍 Setting up patient form monitor...');
        
        let isMonitoring = false;
        const monitoredButtons = new WeakSet();
        
        // Function to capture form data
        function captureFormData() {
            const formData = {};
            
            // First, try to capture the selected location from dropdown (if visible in modal)
            // Look for location dropdown in the modal
            const locationSelectors = [
                'select[name*="location"]',
                'select[id*="location"]',
                '[name*="location"]',
                '[id*="location"]',
                '[data-testid*="location"]',
                'select',
                '[role="combobox"]'
            ];
            
            // Find modal/dialog first
            const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
            if (modal) {
                for (const selector of locationSelectors) {
                    try {
                        const element = modal.querySelector(selector);
                        if (element) {
                            const style = window.getComputedStyle(element);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                let locationValue = '';
                                if (element.tagName.toLowerCase() === 'select') {
                                    locationValue = element.value || '';
                                } else {
                                    locationValue = element.value || element.textContent || element.innerText || '';
                                    const selected = element.querySelector('[selected], [aria-selected="true"], [class*="selected"]');
                                    if (selected) {
                                        locationValue = selected.value || selected.textContent || selected.innerText || locationValue;
                                    }
                                }
                                if (locationValue && locationValue.trim()) {
                                    formData.selectedLocation = locationValue;
                                    break;
                                }
                            }
                        }
                    } catch (e) {
                        continue;
                    }
                }
            }
            
            // Capture text fields - using actual field names and test IDs from the HTML
            const fieldMappings = [
                { key: 'legalFirstName', selectors: ['[name="firstName"]', '[data-testid="addPatientFirstName"]', 'input[name="firstName"]'] },
                { key: 'legalLastName', selectors: ['[name="lastName"]', '[data-testid="addPatientLastName"]', 'input[name="lastName"]'] },
                { key: 'mobilePhone', selectors: ['[data-testid="addPatientMobilePhone"]', '[name="phone"]', 'input[type="tel"][data-testid*="Phone"]'] },
                { key: 'dob', selectors: ['[data-testid="addPatientDob"]', '[name="birthDate"]', 'input[placeholder*="MM/DD/YYYY"]'] },
                { key: 'reasonForVisit', selectors: ['[name="reasonForVisit"]', '[data-testid*="addPatientReasonForVisit"]', '[id="reasonForVisit"]', '[data-testid="addPatientReasonForVisit-0"]', 'input[name="reasonForVisit"]'] }
            ];
            
            fieldMappings.forEach(field => {
                let value = '';
                for (const selector of field.selectors) {
                    try {
                        const element = document.querySelector(selector);
                        if (element) {
                            const style = window.getComputedStyle(element);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                value = element.value || element.textContent || '';
                                if (value && value.trim()) break;
                            }
                        }
                    } catch (e) {
                        continue;
                    }
                }
                formData[field.key] = value || '';
            });
            
            // Capture sexAtBirth dropdown - using actual field name "birthSex"
            const sexSelectors = [
                '#birthSex',
                '[id="birthSex"]',
                '[name="birthSex"]',
                '[data-testid*="birthSex"]',
                '[data-testid*="sex"]',
                'select[name="birthSex"]',
                'select[id="birthSex"]'
            ];
            
            let sexValue = '';
            for (const selector of sexSelectors) {
                try {
                    const element = document.querySelector(selector);
                    if (element) {
                        const style = window.getComputedStyle(element);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            if (element.tagName.toLowerCase() === 'select') {
                                sexValue = element.value || '';
                            } else {
                                // For Ant Design custom dropdowns, check the selection
                                // Method 1: Check for selected-value element (most reliable)
                                const selectedValueEl = element.querySelector('.ant-select-selection-selected-value');
                                if (selectedValueEl) {
                                    sexValue = (selectedValueEl.textContent || selectedValueEl.innerText || '').trim();
                                    if (sexValue) {
                                        // Also try title attribute
                                        const title = selectedValueEl.getAttribute('title');
                                        if (title) sexValue = title;
                                        break;
                                    }
                                }
                                
                                // Method 2: Check the rendered container
                                const rendered = element.querySelector('.ant-select-selection__rendered');
                                const placeholder = element.querySelector('.ant-select-selection__placeholder');
                                
                                if (rendered) {
                                    // Check if placeholder is hidden (meaning something is selected)
                                    let isPlaceholderHidden = false;
                                    if (placeholder) {
                                        const placeholderStyle = window.getComputedStyle(placeholder);
                                        isPlaceholderHidden = placeholderStyle.display === 'none';
                                    }
                                    
                                    if (isPlaceholderHidden || !placeholder) {
                                        // Get all text from rendered
                                        const allText = rendered.textContent || rendered.innerText || '';
                                        // Remove placeholder text if it exists
                                        const placeholderText = placeholder ? (placeholder.textContent || placeholder.innerText || '') : '';
                                        const cleanText = allText.replace(placeholderText, '').trim();
                                        
                                        if (cleanText && !cleanText.includes('Choose an option') && cleanText.length > 0) {
                                            sexValue = cleanText;
                                            if (sexValue) break;
                                        }
                                    }
                                }
                                
                                // Method 3: Check if dropdown is open and get selected option
                                const dropdown = element.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
                                if (dropdown) {
                                    const selectedOption = dropdown.querySelector('.ant-select-item-selected, .ant-select-item-option-selected');
                                    if (selectedOption) {
                                        sexValue = (selectedOption.textContent || selectedOption.innerText || '').trim();
                                        if (sexValue) break;
                                    }
                                }
                                
                                // Method 4: Look for hidden input
                                const hiddenInput = element.querySelector('input[type="hidden"]');
                                if (hiddenInput && hiddenInput.value) {
                                    sexValue = hiddenInput.value;
                                    if (sexValue) break;
                                }
                                
                                // Method 5: Check Ant Design's internal state
                                const antSelect = element.closest('.ant-select');
                                if (antSelect) {
                                    const hiddenInput = antSelect.querySelector('input[type="hidden"]');
                                    if (hiddenInput && hiddenInput.value) {
                                        sexValue = hiddenInput.value;
                                        if (sexValue) break;
                                    }
                                }
                                
                                // Method 6: Check data attributes
                                sexValue = element.getAttribute('data-value') || 
                                          element.getAttribute('value') || 
                                          element.getAttribute('aria-label') || '';
                                if (sexValue) break;
                            }
                            if (sexValue && sexValue.trim()) break;
                        }
                    }
                } catch (e) {
                    continue;
                }
            }
            formData.sexAtBirth = sexValue || '';
            
            return formData;
        }
        
        // Function to check if form is visible (has input fields)
        function isFormVisible() {
            const formFields = [
                '[name="firstName"]',
                '[data-testid="addPatientFirstName"]',
                '[name="lastName"]',
                '[data-testid="addPatientLastName"]',
                '[data-testid="addPatientMobilePhone"]',
                '[data-testid="addPatientDob"]'
            ];
            for (const selector of formFields) {
                try {
                    const element = document.querySelector(selector);
                    if (element) {
                        const style = window.getComputedStyle(element);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return true;
                        }
                    }
                } catch (e) {
                    continue;
                }
            }
            return false;
        }
        
        // Function to setup button listener
        function setupButtonListener() {
            // Try to find the submit button - prioritize the specific testid
            // Look for buttons with text "Add" or submit buttons in modal
            const buttonSelectors = [
                '[data-testid="addPatientSubmitButton"]',
                'button[data-testid*="addPatient"][data-testid*="Submit"]',
                'button[data-testid*="addPatient"]',
                'button[data-testid*="submit"]',
                'button[data-testid*="Add"]'
            ];
            
            let submitButton = null;
            
            // First try specific selectors
            for (const selector of buttonSelectors) {
                try {
                    const buttons = document.querySelectorAll(selector);
                    if (buttons.length > 0) {
                        // Find the one that's visible and in a modal
                        for (const btn of buttons) {
                            const style = window.getComputedStyle(btn);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                // Check if it's in a modal/dialog
                                const modal = btn.closest('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                                if (modal) {
                                    submitButton = btn;
                                    break;
                                }
                            }
                        }
                        if (submitButton) break;
                    }
                } catch (e) {
                    continue;
                }
            }
            
            // If not found, look for buttons with text "Add" in modal
            if (!submitButton) {
                try {
                    const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                    if (modal) {
                        const buttons = modal.querySelectorAll('button');
                        for (const btn of buttons) {
                            const style = window.getComputedStyle(btn);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                const text = (btn.textContent || btn.innerText || '').trim();
                                // Look for buttons with "Add" text (but not "Add Patient" which is the opener)
                                if (text && text.toLowerCase().includes('add') && 
                                    !text.toLowerCase().includes('patient') &&
                                    text.length < 20) {
                                    submitButton = btn;
                                    break;
                                }
                                // Also check for submit type buttons
                                if (btn.type === 'submit' || btn.getAttribute('type') === 'submit') {
                                    submitButton = btn;
                                    break;
                                }
                            }
                        }
                    }
                } catch (e) {
                    // Ignore errors
                }
            }
            
            if (submitButton && !monitoredButtons.has(submitButton)) {
                console.log('✅ Found submit button, setting up listener');
                console.log('   Button text:', submitButton.textContent || submitButton.innerText);
                
                // Mark as monitored
                monitoredButtons.add(submitButton);
                
                // Add multiple listeners to ensure we catch it
                const captureAndSend = async function(e) {
                    console.log('🖱️  Submit button clicked!');
                    
                    // Capture immediately, don't wait
                    const formData = captureFormData();
                    console.log('📋 Captured form data:', formData);
                    
                    // Send to Python immediately
                    try {
                        await window.handlePatientSubmission(formData);
                    } catch (error) {
                        console.error('❌ Error calling handlePatientSubmission:', error);
                    }
                };
                
                // Add listener with capture phase (fires first)
                submitButton.addEventListener('click', captureAndSend, true);
                // Also add normal listener as backup
                submitButton.addEventListener('click', captureAndSend, false);
                // Also intercept mousedown (fires before click)
                submitButton.addEventListener('mousedown', captureAndSend, true);
                
                return true;
            }
            
            return false;
        }
        
        // Try to setup listener immediately
        setupButtonListener();
        
        // Use MutationObserver to watch for dynamically added buttons and modals
        const observer = new MutationObserver(function(mutations) {
            // Check for new buttons
            setupButtonListener();
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-testid', 'class', 'style']
        });
        
        // Also listen for form submit events as a fallback (non-blocking)
        document.addEventListener('submit', async function(e) {
            const form = e.target;
            if (form) {
                // Check if this form is in a modal and contains patient form fields
                const modal = form.closest('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
                if (modal) {
                    // Check if form has patient-related fields
                    const hasPatientFields = form.querySelector('[name="legalFirstName"], [id="legalFirstName"], [data-testid="legalFirstName"]') ||
                                           form.querySelector('[name="legalLastName"], [id="legalLastName"], [data-testid="legalLastName"]');
                    
                    if (hasPatientFields) {
                        console.log('📝 Form submit event detected in modal!');
                        
                        // Small delay to capture data (don't block submission)
                        setTimeout(async () => {
                            const formData = captureFormData();
                            console.log('📋 Captured form data:', formData);
                            
                            try {
                                await window.handlePatientSubmission(formData);
                            } catch (error) {
                                console.error('❌ Error calling handlePatientSubmission:', error);
                            }
                        }, 100);
                    }
                }
            }
        }, false); // Don't use capture phase, let form submit normally
        
        // Periodic check for buttons (in case MutationObserver misses something)
        setInterval(() => {
            setupButtonListener();
        }, 1000); // Check every second
        
        // Also log when modals appear
        const modalObserver = new MutationObserver(function(mutations) {
            const modal = document.querySelector('[role="dialog"], .modal, [class*="Modal"], [class*="modal"]');
            if (modal) {
                console.log('📦 Modal detected, checking for buttons...');
                setupButtonListener();
            }
        });
        
        modalObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        console.log('✅ Patient form monitor initialized');
        console.log('🔍 Monitoring for form submissions...');
    })();
    """
    
    # Inject the monitoring script
    await page.evaluate(monitor_script)
    print("✅ Form monitor script injected")
    
    # Also set up console message listener to see JavaScript logs
    def handle_console(msg):
        if "Patient form" in msg.text or "Submit button" in msg.text or "Form submit" in msg.text or "Captured form" in msg.text:
            print(f"   [JS Console] {msg.text}")
    
    page.on("console", handle_console)


async def main():
    """
    Main function to run the patient form monitor.
    """
    # Get URL from environment variable - use URL as-is without appending location_ids
    url = os.getenv('SOLVHEALTH_QUEUE_URL')
    
    if not url:
        print("❌ Error: SOLVHEALTH_QUEUE_URL environment variable is not set.")
        print("   Please set it with the queue URL, e.g.:")
        print("   export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue?location_ids=AXjwbE'")
        print("   or")
        print("   export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue'")
        sys.exit(1)
    
    # Extract location_id from URL (optional - will be extracted from current page URL if not in initial URL)
    location_id = extract_location_id_from_url(url)
    
    if location_id:
        location_name = get_location_name(location_id) or f"Location {location_id}"
    else:
        location_id = None
        location_name = "Will be detected from page"
    
    print("=" * 60)
    print("🏥 Patient Form Monitor")
    print("=" * 60)
    print(f"📍 URL: {url}")
    if location_id:
        print(f"📍 Location ID: {location_id}")
        print(f"📍 Location Name: {location_name}")
    else:
        print(f"📍 Location: {location_name}")
    print("=" * 60)
    print("\n🔍 Listening for patient submissions...")
    headless = str_to_bool(os.getenv("PLAYWRIGHT_HEADLESS"))
    if headless:
        print("   (Running in headless mode)")
    else:
        print("   (The browser will open in non-headless mode)")
    print("   (Click 'Add Patient' and submit the form to capture data)")
    print("   (Press Ctrl+C to stop)\n")
    
    async with async_playwright() as p:
        # Launch browser with mode controlled via environment variable
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to the page with a less strict wait condition
            print(f"🌐 Navigating to {url}...")
            try:
                # Try with domcontentloaded first (faster, less strict)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print("✅ Page loaded (DOM ready)")
            except PlaywrightTimeoutError:
                # If that times out, try with just load
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                    print("✅ Page loaded (load event)")
                except PlaywrightTimeoutError:
                    # Even if timeout, continue - the page might still be usable
                    print("⚠️  Page navigation timeout, but continuing anyway...")
                    print("   (The page may still be loading, but monitoring will start)")
            
            # Wait a bit for the page to fully initialize and any modals to be ready
            print("⏳ Waiting for page to initialize...")
            await asyncio.sleep(3)
            
            # Setup form monitor
            print("🔧 Setting up form monitor...")
            await setup_form_monitor(page, location_id, location_name)
            
            # Keep the script running indefinitely
            print("\n⏳ Monitoring... (Press Ctrl+C to stop)")
            print("   📝 Instructions:")
            print("      1. Click 'Add Patient' button (modal will open)")
            print("      2. Select location from dropdown in the modal")
            print("      3. Fill out the form fields that appear")
            print("      4. Click 'Add' button to submit")
            print("      5. Form data will be captured and saved automatically\n")
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping monitor...")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            await browser.close()
            print("👋 Browser closed. Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())


