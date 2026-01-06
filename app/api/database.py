#!/usr/bin/env python3
"""
Database helper functions for API operations.

This module contains functions that interact directly with the database:
- Database connection management
- CRUD operations (save_encounter, save_queue, save_summary, etc.)
- Query functions (fetch_pending_records, get_summary_by_emr_id, etc.)
- Queue operations (create_queue_from_encounter, update_queue_status, etc.)
"""

import os
import json
import uuid
import logging
import copy
from typing import Optional, Dict, Any, List
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def get_db_connection():
    """Get PostgreSQL database connection from environment variables.
    
    Supports two methods:
    1. DATABASE_URL (recommended for cloud deployments like Aptible)
       Format: postgresql://user:password@host:port/database
    2. Individual environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
    """
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
            raise HTTPException(
                status_code=500,
                detail=f"Error parsing DATABASE_URL: {str(e)}. Format should be: postgresql://user:password@host:port/database"
            )
    else:
        # Fall back to individual environment variables
        import getpass
        default_user = os.getenv('USER', os.getenv('USERNAME', getpass.getuser()))
        db_host = os.getenv('DB_HOST', 'localhost')
        db_config = {
            'host': db_host,
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'solvhealth_patients'),
            'user': os.getenv('DB_USER', default_user),
            'password': os.getenv('DB_PASSWORD', '')
        }
        # Enable SSL for remote databases (Aptible requires SSL)
        if db_host and db_host not in ('localhost', '127.0.0.1', '::1'):
            db_config['sslmode'] = 'require'
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection error: {str(e)}"
        )


def format_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format patient record for JSON response."""
    formatted = {}
    for key, value in record.items():
        # Convert datetime objects to ISO format strings
        if isinstance(value, datetime):
            formatted[key] = value.isoformat()
        # Convert date objects to ISO format strings
        elif hasattr(value, 'isoformat') and hasattr(value, 'year'):
            formatted[key] = value.isoformat()
        else:
            formatted[key] = value
    return formatted


def fetch_pending_records(
    cursor,
    location_id: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    query = """
        SELECT 
            pending_id AS id,
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
            created_at,
            updated_at,
            raw_payload,
            status,
            raw_payload->>'status' AS patient_status,
            raw_payload->>'appointment_date' AS appointment_date,
            raw_payload->>'appointment_date_at_clinic_tz' AS appointment_date_at_clinic_tz,
            raw_payload->>'calendar_date' AS calendar_date
        FROM pending_patients
    """

    conditions: List[str] = []
    params: List[Any] = []

    if location_id:
        conditions.append("location_id = %s")
        params.append(location_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY captured_at DESC NULLS LAST, updated_at DESC"

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def fetch_confirmed_records(
    cursor,
    location_id: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    query = """
        SELECT 
            id,
            emr_id,
            booking_id,
            booking_number,
            patient_number,
            location_id,
            location_name,
            status,
            legal_first_name,
            legal_last_name,
            dob,
            mobile_phone,
            sex_at_birth,
            captured_at,
            reason_for_visit,
            created_at,
            updated_at
        FROM patients
    """

    conditions: List[str] = []
    params: List[Any] = []

    if location_id:
        conditions.append("location_id = %s")
        params.append(location_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY captured_at DESC NULLS LAST, updated_at DESC"

    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def remove_excluded_fields(encounter_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove excluded fields from encounter payload for queue storage.
    
    This function creates a cleaned copy of the encounter payload by removing
    fields that should not be stored in the queue. The original encounter data
    remains intact in the encounters table.
    
    Args:
        encounter_payload: The full encounter payload dictionary
        
    Returns:
        A new dictionary with excluded fields removed
    """
    # Create a deep copy to avoid modifying the original
    cleaned_payload = copy.deepcopy(encounter_payload)
    
    # List of top-level fields to remove
    # Note: 'createdBy' and 'createdById' are kept to display in queue list
    excluded_top_level_fields = [
        'source',
        'meta',
        'esi',
        'deletedAt',
        'syncedAt',
        'originLaunchError',
        'origin',
        'originOrders',
        'originObservationLabs',
        'locationId',
        'originPatientId',
        'originBillingCode',
        'originStartedAt',
        'originBillingCodeSyncedAt',
        'originBillingCodeFailureCount',
        'originBillingCodeFailureMessage',
        'originDiagnosticReportsSyncedAt',
        'originDiagnosticReportsFailureCount',
        'originDiagnosticReportsFailureMessage',
        'originCsn',
        'originAppointmentType',
        'originDiagnosesSyncedAt',
        'originDiagnosesFailureCount',
        'originDiagnosesFailureMessage',
        'originDiagnosesJobId',
        'originDiagnosticReportsJobId',
        'originCsnSyncedAt',
        'originCsnFailureCount',
        'originCsnFailureMessage',
        'originCsnJobId',
        'createdByUser',
        'accessLogs',
        'creationLog',
    ]
    
    # Remove top-level excluded fields
    for field in excluded_top_level_fields:
        cleaned_payload.pop(field, None)
    
    # Remove fields from patient object if it exists
    if 'patient' in cleaned_payload and isinstance(cleaned_payload['patient'], dict):
        patient_excluded_fields = [
            'firstName',
            'lastName',
            'encounterOriginId',
            'mrn',
            'emailAddress',
            'phoneNumber',
        ]
        for field in patient_excluded_fields:
            cleaned_payload['patient'].pop(field, None)
    
    return cleaned_payload


def save_encounter(conn, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update an encounter record in the database.
    
    Args:
        conn: PostgreSQL database connection
        encounter_data: Dictionary containing encounter data with:
            - encounter_id: UUID (required)
            - emr_id: string (required)
            - encounter_payload: JSONB (required) - full encounter JSON payload
        
    Returns:
        Dictionary with the saved encounter data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Extract required fields
        encounter_id = encounter_data.get('encounter_id')
        emr_id = encounter_data.get('emr_id')
        encounter_payload = encounter_data.get('encounter_payload')
        
        # Validate required fields
        if not encounter_id:
            raise ValueError("encounter_id is required")
        if not emr_id:
            raise ValueError("emr_id is required")
        if not encounter_payload:
            raise ValueError("encounter_payload is required")
        
        # Convert encounter_payload to JSONB
        encounter_payload_json = Json(encounter_payload)
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        query = """
            INSERT INTO encounters (
                encounter_id, emr_id, encounter_payload
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (encounter_id) 
            DO UPDATE SET
                emr_id = EXCLUDED.emr_id,
                encounter_payload = EXCLUDED.encounter_payload
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                encounter_id,
                emr_id,
                encounter_payload_json,
            )
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result for response
        formatted_result = format_patient_record(result)
        
        # Convert encounter_payload JSONB back to dict if present
        if formatted_result.get('encounter_payload'):
            if isinstance(formatted_result['encounter_payload'], str):
                try:
                    formatted_result['encounter_payload'] = json.loads(formatted_result['encounter_payload'])
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def save_queue(conn, queue_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update a queue record in the database.
    
    Args:
        conn: PostgreSQL database connection
        queue_data: Dictionary containing queue data with:
            - queue_id: Optional UUID (will be generated if not provided)
            - encounter_id: UUID (required)
            - emr_id: Optional string
            - status: Optional string (default: 'PENDING')
            - raw_payload: Optional JSON payload (JSONB)
            - parsed_payload: Optional parsed JSON payload (JSONB)
            - attempts: Optional integer (default: 0)
        
    Returns:
        Dictionary with the saved queue data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Generate queue_id if not provided
        queue_id = queue_data.get('queue_id')
        if not queue_id:
            queue_id = str(uuid.uuid4())
        
        encounter_id = queue_data.get('encounter_id')
        if not encounter_id:
            raise ValueError("encounter_id is required for queue entries")
        
        # Get status, default to PENDING
        status = queue_data.get('status', 'PENDING')
        if status not in ['PENDING', 'PROCESSING', 'DONE', 'ERROR']:
            status = 'PENDING'
        
        # Get attempts, default to 0
        attempts = queue_data.get('attempts', 0)
        if not isinstance(attempts, int):
            attempts = 0
        
        # Extract raw_payload and parsed_payload if provided
        raw_payload_json = None
        if queue_data.get('raw_payload'):
            raw_payload_json = Json(queue_data['raw_payload'])
        
        parsed_payload_json = None
        if queue_data.get('parsed_payload'):
            parsed_payload_json = Json(queue_data['parsed_payload'])
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        query = """
            INSERT INTO queue (
                queue_id, encounter_id, emr_id, status,
                raw_payload, parsed_payload, attempts
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (encounter_id) 
            DO UPDATE SET
                emr_id = EXCLUDED.emr_id,
                status = EXCLUDED.status,
                raw_payload = EXCLUDED.raw_payload,
                parsed_payload = EXCLUDED.parsed_payload,
                attempts = EXCLUDED.attempts,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                queue_id,
                encounter_id,
                queue_data.get('emr_id'),
                status,
                raw_payload_json,
                parsed_payload_json,
                attempts,
            )
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result for response
        formatted_result = format_patient_record(result)
        
        # Convert raw_payload and parsed_payload JSONB back to dicts if present
        if formatted_result.get('raw_payload'):
            if isinstance(formatted_result['raw_payload'], str):
                try:
                    formatted_result['raw_payload'] = json.loads(formatted_result['raw_payload'])
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
        
        if formatted_result.get('parsed_payload'):
            if isinstance(formatted_result['parsed_payload'], str):
                try:
                    formatted_result['parsed_payload'] = json.loads(formatted_result['parsed_payload'])
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def save_vm_health(conn, vm_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update a VM health record in the database.
    
    Args:
        conn: PostgreSQL database connection
        vm_data: Dictionary containing VM health data with:
            - vm_id: string (required) - VM identifier
            - status: string (required) - VM status: healthy, unhealthy, or idle
            - processing_queue_id: Optional UUID - Queue ID that the VM is processing
        
    Returns:
        Dictionary with the saved/updated VM health data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Extract required fields
        vm_id = vm_data.get('vm_id')
        status = vm_data.get('status')
        processing_queue_id = vm_data.get('processing_queue_id')
        
        # Validate required fields
        if not vm_id:
            raise ValueError("vm_id is required")
        if not status:
            raise ValueError("status is required")
        
        # Validate status
        valid_statuses = ['healthy', 'unhealthy', 'idle']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}")
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        query = """
            INSERT INTO vm_health (
                vm_id, last_heartbeat, status, processing_queue_id, updated_at
            )
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (vm_id) 
            DO UPDATE SET
                last_heartbeat = CURRENT_TIMESTAMP,
                status = EXCLUDED.status,
                processing_queue_id = EXCLUDED.processing_queue_id,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                vm_id,
                status,
                processing_queue_id,
            )
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        if not result:
            raise ValueError("Failed to save VM health record")
        
        # Format the result
        formatted_result = dict(result)
        
        # Convert timestamps to ISO format strings
        if formatted_result.get('last_heartbeat'):
            if isinstance(formatted_result['last_heartbeat'], datetime):
                formatted_result['last_heartbeat'] = formatted_result['last_heartbeat'].isoformat() + 'Z'
        
        if formatted_result.get('created_at'):
            if isinstance(formatted_result['created_at'], datetime):
                formatted_result['created_at'] = formatted_result['created_at'].isoformat() + 'Z'
        
        if formatted_result.get('updated_at'):
            if isinstance(formatted_result['updated_at'], datetime):
                formatted_result['updated_at'] = formatted_result['updated_at'].isoformat() + 'Z'
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def get_latest_vm_health(conn) -> Optional[Dict[str, Any]]:
    """Get the latest VM health record from the database.
    
    Args:
        conn: PostgreSQL database connection
        
    Returns:
        Dictionary with the latest VM health data, or None if no records exist
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get the most recent VM health record
        query = """
            SELECT *
            FROM vm_health
            ORDER BY last_heartbeat DESC
            LIMIT 1
        """
        
        cursor.execute(query)
        result = cursor.fetchone()
        
        if not result:
            return None
        
        # Format the result
        formatted_result = dict(result)
        
        # Convert timestamps to ISO format strings
        if formatted_result.get('last_heartbeat'):
            if isinstance(formatted_result['last_heartbeat'], datetime):
                formatted_result['last_heartbeat'] = formatted_result['last_heartbeat'].isoformat() + 'Z'
        
        if formatted_result.get('created_at'):
            if isinstance(formatted_result['created_at'], datetime):
                formatted_result['created_at'] = formatted_result['created_at'].isoformat() + 'Z'
        
        if formatted_result.get('updated_at'):
            if isinstance(formatted_result['updated_at'], datetime):
                formatted_result['updated_at'] = formatted_result['updated_at'].isoformat() + 'Z'
        
        return formatted_result
        
    except psycopg2.Error as e:
        raise e
    finally:
        cursor.close()


def create_queue_from_encounter(conn, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a queue entry from an encounter record.
    
    This function creates a cleaned version of the encounter_payload by removing
    excluded fields (source, meta, esi, createdBy, accessLogs, etc.) before storing
    it in the queue's raw_payload. The original encounter_payload remains intact
    in the encounters table. The emr_id comes from the encounter table, not from
    the payload.
    
    The cleaned payload stored in raw_payload is what gets returned in API responses
    as encounterPayload. The parsed_payload is used internally only and is never
    exposed via API responses.
    
    Args:
        conn: PostgreSQL database connection
        encounter_data: Dictionary containing encounter data (from save_encounter result)
            Expected structure:
            - encounter_id: UUID (from encounters table)
            - emr_id: string (from encounters table)
            - encounter_payload: dict (the actual encounter JSON object)
        
    Returns:
        Dictionary with the created queue data
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Extract data from encounter table (not from payload)
    encounter_id = encounter_data.get('encounter_id')
    if not encounter_id:
        raise ValueError("encounter_id is required to create queue entry")
    
    # Get emr_id from encounter table (not from payload)
    emr_id = encounter_data.get('emr_id', '')
    if not emr_id:
        logger.warning(f"emr_id is empty for encounter {encounter_id}")
    
    # Get encounter_payload from encounter
    encounter_payload = encounter_data.get('encounter_payload')
    if not encounter_payload:
        raise ValueError("encounter_payload is required to create queue entry")
    
    # If encounter_payload is a string, parse it
    if isinstance(encounter_payload, str):
        try:
            encounter_payload = json.loads(encounter_payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"encounter_payload must be valid JSON: {str(e)}")
    
    # Validate that encounter_payload is a dictionary
    if not isinstance(encounter_payload, dict):
        raise ValueError(f"encounter_payload must be a dictionary, got {type(encounter_payload).__name__}")
    
    # Create a cleaned copy of encounter_payload for raw_payload
    # This removes excluded fields that should not be stored in the queue
    # The original encounter_payload remains intact in the encounters table
    raw_payload = remove_excluded_fields(encounter_payload)
    
    # Validate that raw_payload contains expected encounter fields
    # At minimum, it should have an id or encounterId
    encounter_id_in_payload = (
        raw_payload.get('id') or 
        raw_payload.get('encounterId') or 
        raw_payload.get('encounter_id')
    )
    
    if not encounter_id_in_payload:
        logger.warning(
            f"encounter_payload for encounter {encounter_id} does not contain "
            "id, encounterId, or encounter_id field"
        )
    
    # Ensure the encounter_id in payload matches the table encounter_id
    if encounter_id_in_payload and str(encounter_id_in_payload) != str(encounter_id):
        logger.warning(
            f"encounter_id mismatch: table has {encounter_id}, "
            f"payload has {encounter_id_in_payload}"
        )
    
    # Remove emr_id from raw_payload if it exists (it should come from table, not payload)
    # This ensures consistency - emr_id always comes from the encounter table
    if 'emrId' in raw_payload or 'emr_id' in raw_payload:
        payload_emr_id = raw_payload.pop('emrId', None) or raw_payload.pop('emr_id', None)
        if payload_emr_id and payload_emr_id != emr_id:
            logger.warning(
                f"emr_id mismatch: table has '{emr_id}', payload had '{payload_emr_id}'. "
                "Using table emr_id."
            )
    
    # Extract chief_complaints and trauma_type from encounter_payload for parsed_payload
    # Check both camelCase and snake_case versions
    chief_complaints = raw_payload.get('chiefComplaints') or raw_payload.get('chief_complaints', [])
    trauma_type = raw_payload.get('traumaType') or raw_payload.get('trauma_type')
    
    # Validate chief_complaints is a list
    if not isinstance(chief_complaints, list):
        logger.warning(f"chief_complaints is not a list for encounter {encounter_id}, converting to empty list")
        chief_complaints = []
    
    # CRITICAL: Ensure chiefComplaints is always present in raw_payload for queue entry
    # This ensures UiPath and other consumers can always access chiefComplaints
    # Use camelCase (chiefComplaints) as the standard format
    if 'chiefComplaints' not in raw_payload and 'chief_complaints' not in raw_payload:
        logger.warning(
            f"chiefComplaints missing from encounter {encounter_id} payload. "
            f"Adding empty array to ensure field is always present."
        )
        raw_payload['chiefComplaints'] = chief_complaints
    elif 'chiefComplaints' not in raw_payload and 'chief_complaints' in raw_payload:
        # Convert snake_case to camelCase for consistency
        raw_payload['chiefComplaints'] = raw_payload.pop('chief_complaints')
        logger.info(f"Converted chief_complaints to chiefComplaints for encounter {encounter_id}")
    elif 'chiefComplaints' in raw_payload:
        # Ensure it's the correct type
        if not isinstance(raw_payload['chiefComplaints'], list):
            logger.warning(
                f"chiefComplaints in raw_payload is not a list for encounter {encounter_id}, "
                f"replacing with validated list"
            )
            raw_payload['chiefComplaints'] = chief_complaints
    
    # Log if chiefComplaints is empty (for debugging)
    if len(chief_complaints) == 0:
        logger.warning(
            f"encounter {encounter_id} has empty chiefComplaints array. "
            f"This may indicate an issue with encounter creation."
        )
    
    # Create parsed_payload structure with experityAction set to empty array
    parsed_payload = {
        'trauma_type': trauma_type,
        'chief_complaints': chief_complaints,
        'experityAction': []
    }
    
    # Build queue data
    # Note: emr_id comes from encounter_data (table), not from raw_payload
    queue_data = {
        'encounter_id': str(encounter_id),
        'emr_id': str(emr_id),  # From encounter table, not from payload
        'status': 'PENDING',
        'raw_payload': raw_payload,  # Cleaned encounter payload (excluded fields removed)
        'parsed_payload': parsed_payload,  # Simplified parsed structure (internal use only)
        'attempts': 0,
    }
    
    logger.info(
        f"Creating queue entry for encounter {encounter_id} "
        f"(emr_id: {emr_id}, trauma_type: {trauma_type}, "
        f"chief_complaints count: {len(chief_complaints)})"
    )
    
    # Save queue entry
    return save_queue(conn, queue_data)


def save_summary(conn, summary_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save a summary record in the database.
    
    Args:
        conn: PostgreSQL database connection
        summary_data: Dictionary containing summary data with:
            - emr_id: EMR identifier (required)
            - note: Summary note text (required)
        
    Returns:
        Dictionary with the saved summary data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        emr_id = summary_data.get('emr_id')
        note = summary_data.get('note')
        
        if not emr_id:
            raise ValueError("emr_id is required for summary entries")
        if not note:
            raise ValueError("note is required for summary entries")
        
        # Insert new summary record
        query = """
            INSERT INTO summaries (emr_id, note)
            VALUES (%s, %s)
            RETURNING *
        """
        
        cursor.execute(query, (emr_id, note))
        
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result for response
        formatted_result = format_patient_record(result)
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def get_summary_by_emr_id(conn, emr_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a summary record by EMR ID.
    
    Args:
        conn: PostgreSQL database connection
        emr_id: EMR identifier to search for
        
    Returns:
        Dictionary with the summary data, or None if not found
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT * FROM summaries
            WHERE emr_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
        """
        
        cursor.execute(query, (emr_id,))
        result = cursor.fetchone()
        
        if not result:
            return None
        
        # Format the result for response
        formatted_result = format_patient_record(result)
        
        return formatted_result
        
    except psycopg2.Error as e:
        raise e
    finally:
        cursor.close()


def update_queue_status_and_experity_action(
    conn,
    queue_id: str,
    status: str,
    experity_actions: Optional[List[Dict[str, Any]]] = None,
    error_message: Optional[str] = None,
    increment_attempts: bool = False
) -> None:
    """
    Update queue entry status and optionally experity actions.
    
    Args:
        conn: PostgreSQL database connection
        queue_id: Queue identifier (UUID)
        status: New status ('PROCESSING', 'DONE', 'ERROR')
        experity_actions: Optional list of Experity action objects to store in parsed_payload
        error_message: Optional error message to store (for ERROR status)
        increment_attempts: Whether to increment the attempts counter
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get current queue entry
        cursor.execute(
            "SELECT parsed_payload FROM queue WHERE queue_id = %s",
            (queue_id,)
        )
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            raise ValueError(f"Queue entry not found: {queue_id}")
        
        # Parse current parsed_payload
        parsed_payload = queue_entry.get('parsed_payload')
        if isinstance(parsed_payload, str):
            try:
                parsed_payload = json.loads(parsed_payload)
            except json.JSONDecodeError:
                parsed_payload = {}
        elif parsed_payload is None:
            parsed_payload = {}
        
        # Update experityAction if provided
        if experity_actions is not None:
            parsed_payload['experityAction'] = experity_actions
        
        # Build update query
        update_fields = ["status = %s", "parsed_payload = %s", "updated_at = CURRENT_TIMESTAMP"]
        update_values = [status, Json(parsed_payload)]
        
        if increment_attempts:
            update_fields.append("attempts = attempts + 1")
        
        if error_message and status == 'ERROR':
            # Store error in parsed_payload for tracking
            parsed_payload['error_message'] = error_message
        
        query = f"""
            UPDATE queue
            SET {', '.join(update_fields)}
            WHERE queue_id = %s
        """
        update_values.append(queue_id)
        
        cursor.execute(query, tuple(update_values))
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
