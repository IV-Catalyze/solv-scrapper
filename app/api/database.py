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
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
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
    # Note: 'createdBy', 'createdById', and 'createdByUser' are kept to display in queue list
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
        'accessLogs',
        'creationLog',
        'predictedDiagnoses',
    ]
    
    # Extract createdBy from createdByUser if createdBy doesn't exist
    # This ensures we preserve the creator information even if it's nested in createdByUser
    if 'createdBy' not in cleaned_payload and 'created_by' not in cleaned_payload:
        created_by_user = encounter_payload.get('createdByUser') or encounter_payload.get('created_by_user')
        if created_by_user:
            if isinstance(created_by_user, dict):
                # Extract email, emailAddress, name, or id from createdByUser object
                created_by = (
                    created_by_user.get('email') or 
                    created_by_user.get('emailAddress') or 
                    created_by_user.get('name') or 
                    created_by_user.get('id') or
                    created_by_user.get('username')
                )
                if created_by:
                    cleaned_payload['createdBy'] = str(created_by)
            elif isinstance(created_by_user, str):
                cleaned_payload['createdBy'] = created_by_user
    
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
            - server_id: Optional string - Server identifier
            - status: string (required) - VM status: healthy, unhealthy, or idle
            - processing_queue_id: Optional UUID - Queue ID that the VM is processing
            - workflow_status: Optional string - AI Agent Workflow status
            - metadata: Optional dict - Metadata object with system metrics
        
    Returns:
        Dictionary with the saved/updated VM health data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    import json
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Extract required fields
        vm_id = vm_data.get('vm_id')
        status = vm_data.get('status')
        processing_queue_id = vm_data.get('processing_queue_id')
        server_id = vm_data.get('server_id')
        workflow_status = vm_data.get('workflow_status')
        metadata = vm_data.get('metadata')
        
        # Validate required fields
        if not vm_id:
            raise ValueError("vm_id is required")
        if not status:
            raise ValueError("status is required")
        
        # Validate status
        valid_statuses = ['healthy', 'unhealthy', 'idle']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}")
        
        # Convert metadata dict to JSON string if provided
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata)
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        query = """
            INSERT INTO vm_health (
                vm_id, server_id, last_heartbeat, status, processing_queue_id, 
                workflow_status, metadata, updated_at
            )
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (vm_id) 
            DO UPDATE SET
                server_id = EXCLUDED.server_id,
                last_heartbeat = CURRENT_TIMESTAMP,
                status = EXCLUDED.status,
                processing_queue_id = EXCLUDED.processing_queue_id,
                workflow_status = EXCLUDED.workflow_status,
                metadata = EXCLUDED.metadata,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                vm_id,
                server_id,
                status,
                processing_queue_id,
                workflow_status,
                metadata_json,
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
        
        # Parse metadata JSONB if present
        if formatted_result.get('metadata'):
            if isinstance(formatted_result['metadata'], str):
                formatted_result['metadata'] = json.loads(formatted_result['metadata'])
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def save_server_health(conn, server_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update a server health record in the database.
    
    Args:
        conn: PostgreSQL database connection
        server_data: Dictionary containing server health data with:
            - server_id: string (required) - Server identifier
            - status: string (required) - Server status: healthy, unhealthy, or down
            - metadata: Optional dict - Metadata object with system metrics
        
    Returns:
        Dictionary with the saved/updated server health data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Extract required fields
        server_id = server_data.get('server_id')
        status = server_data.get('status')
        metadata = server_data.get('metadata')
        
        # Validate required fields
        if not server_id:
            raise ValueError("server_id is required")
        if not status:
            raise ValueError("status is required")
        
        # Validate status
        valid_statuses = ['healthy', 'unhealthy', 'down']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}")
        
        # Convert metadata dict to JSON string if provided
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata)
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        query = """
            INSERT INTO server_health (
                server_id, last_heartbeat, status, metadata, updated_at
            )
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (server_id) 
            DO UPDATE SET
                last_heartbeat = CURRENT_TIMESTAMP,
                status = EXCLUDED.status,
                metadata = EXCLUDED.metadata,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                server_id,
                status,
                metadata_json,
            )
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        if not result:
            raise ValueError("Failed to save server health record")
        
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
        
        # Parse metadata JSONB if present
        if formatted_result.get('metadata'):
            if isinstance(formatted_result['metadata'], str):
                formatted_result['metadata'] = json.loads(formatted_result['metadata'])
        
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


def get_vm_health_by_vm_id(conn, vm_id: str) -> Optional[Dict[str, Any]]:
    """Get VM health record for a specific VM ID.
    
    Args:
        conn: PostgreSQL database connection
        vm_id: VM identifier
        
    Returns:
        Dictionary with the VM health data for the given vm_id, or None if not found.
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT *
            FROM vm_health
            WHERE vm_id = %s
        """
        cursor.execute(query, (vm_id,))
        result = cursor.fetchone()
        
        if not result:
            return None
        
        formatted = dict(result)
        
        # Normalize timestamps to ISO strings
        if formatted.get("last_heartbeat") and isinstance(formatted["last_heartbeat"], datetime):
            formatted["last_heartbeat"] = formatted["last_heartbeat"].isoformat() + "Z"
        if formatted.get("created_at") and isinstance(formatted["created_at"], datetime):
            formatted["created_at"] = formatted["created_at"].isoformat() + "Z"
        if formatted.get("updated_at") and isinstance(formatted["updated_at"], datetime):
            formatted["updated_at"] = formatted["updated_at"].isoformat() + "Z"
        
        # Parse metadata JSONB if needed
        if formatted.get("metadata") and isinstance(formatted["metadata"], str):
            formatted["metadata"] = json.loads(formatted["metadata"])
        
        return formatted
    finally:
        cursor.close()


def get_server_health_by_server_id(conn, server_id: str) -> Optional[Dict[str, Any]]:
    """Get server health record for a specific server ID.
    
    Args:
        conn: PostgreSQL database connection
        server_id: Server identifier
        
    Returns:
        Dictionary with the server health data for the given server_id, or None if not found.
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT *
            FROM server_health
            WHERE server_id = %s
        """
        cursor.execute(query, (server_id,))
        result = cursor.fetchone()
        
        if not result:
            return None
        
        formatted = dict(result)
        
        # Normalize timestamps to ISO strings
        if formatted.get("last_heartbeat") and isinstance(formatted["last_heartbeat"], datetime):
            formatted["last_heartbeat"] = formatted["last_heartbeat"].isoformat() + "Z"
        if formatted.get("created_at") and isinstance(formatted["created_at"], datetime):
            formatted["created_at"] = formatted["created_at"].isoformat() + "Z"
        if formatted.get("updated_at") and isinstance(formatted["updated_at"], datetime):
            formatted["updated_at"] = formatted["updated_at"].isoformat() + "Z"
        
        # Parse metadata JSONB if needed
        if formatted.get("metadata") and isinstance(formatted["metadata"], str):
            formatted["metadata"] = json.loads(formatted["metadata"])
        
        return formatted
    finally:
        cursor.close()


def get_vms_by_server_id(conn, server_id: str) -> List[Dict[str, Any]]:
    """Get all VM health records for a specific server ID.
    
    Args:
        conn: PostgreSQL database connection
        server_id: Server identifier
        
    Returns:
        List of dictionaries with VM health data for the given server_id
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT 
                vm_id,
                server_id,
                last_heartbeat,
                status,
                workflow_status,
                processing_queue_id,
                metadata,
                created_at,
                updated_at
            FROM vm_health
            WHERE server_id = %s
            ORDER BY vm_id
        """
        cursor.execute(query, (server_id,))
        results = cursor.fetchall()
        
        formatted_results = []
        for result in results:
            formatted = dict(result)
            
            # Normalize timestamps to ISO strings
            if formatted.get("last_heartbeat") and isinstance(formatted["last_heartbeat"], datetime):
                formatted["last_heartbeat"] = formatted["last_heartbeat"].isoformat() + "Z"
            if formatted.get("created_at") and isinstance(formatted["created_at"], datetime):
                formatted["created_at"] = formatted["created_at"].isoformat() + "Z"
            if formatted.get("updated_at") and isinstance(formatted["updated_at"], datetime):
                formatted["updated_at"] = formatted["updated_at"].isoformat() + "Z"
            
            # Parse metadata JSONB if needed
            if formatted.get("metadata") and isinstance(formatted["metadata"], str):
                formatted["metadata"] = json.loads(formatted["metadata"])
            
            formatted_results.append(formatted)
        
        return formatted_results
    finally:
        cursor.close()


def get_all_servers_health(
    conn, 
    server_id: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all server health records with optional filtering.
    
    Args:
        conn: PostgreSQL database connection
        server_id: Optional server identifier to filter by
        status: Optional status to filter by (healthy, unhealthy, down)
        
    Returns:
        List of dictionaries with server health data
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = "SELECT * FROM server_health WHERE 1=1"
        params = []
        
        if server_id:
            query += " AND server_id = %s"
            params.append(server_id)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY server_id"
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        formatted_results = []
        for result in results:
            formatted = dict(result)
            
            # Normalize timestamps
            if formatted.get("last_heartbeat") and isinstance(formatted["last_heartbeat"], datetime):
                formatted["last_heartbeat"] = formatted["last_heartbeat"].isoformat() + "Z"
            if formatted.get("created_at") and isinstance(formatted["created_at"], datetime):
                formatted["created_at"] = formatted["created_at"].isoformat() + "Z"
            if formatted.get("updated_at") and isinstance(formatted["updated_at"], datetime):
                formatted["updated_at"] = formatted["updated_at"].isoformat() + "Z"
            
            # Parse metadata JSONB
            if formatted.get("metadata") and isinstance(formatted["metadata"], str):
                formatted["metadata"] = json.loads(formatted["metadata"])
            
            formatted_results.append(formatted)
        
        return formatted_results
    finally:
        cursor.close()


def get_all_vms_health(
    conn,
    server_id: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all VM health records with optional filtering.
    
    Args:
        conn: PostgreSQL database connection
        server_id: Optional server identifier to filter by
        status: Optional status to filter by (healthy, unhealthy, idle)
        
    Returns:
        List of dictionaries with VM health data
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT 
                vm_id,
                server_id,
                last_heartbeat,
                status,
                workflow_status,
                processing_queue_id,
                metadata,
                created_at,
                updated_at
            FROM vm_health
            WHERE 1=1
        """
        params = []
        
        if server_id:
            query += " AND server_id = %s"
            params.append(server_id)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY server_id, vm_id"
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        formatted_results = []
        for result in results:
            formatted = dict(result)
            
            # Normalize timestamps
            if formatted.get("last_heartbeat") and isinstance(formatted["last_heartbeat"], datetime):
                formatted["last_heartbeat"] = formatted["last_heartbeat"].isoformat() + "Z"
            if formatted.get("created_at") and isinstance(formatted["created_at"], datetime):
                formatted["created_at"] = formatted["created_at"].isoformat() + "Z"
            if formatted.get("updated_at") and isinstance(formatted["updated_at"], datetime):
                formatted["updated_at"] = formatted["updated_at"].isoformat() + "Z"
            
            # Parse metadata JSONB
            if formatted.get("metadata") and isinstance(formatted["metadata"], str):
                formatted["metadata"] = json.loads(formatted["metadata"])
            
            formatted_results.append(formatted)
        
        return formatted_results
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
    # This ensures AI Agent Workflow and other consumers can always access chiefComplaints
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
            - emr_id: EMR identifier (optional)
            - encounter_id: Encounter identifier UUID (optional)
            - note: Summary note text (required)
        
    Returns:
        Dictionary with the saved summary data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        emr_id = summary_data.get('emr_id')
        encounter_id = summary_data.get('encounter_id')
        note = summary_data.get('note')
        
        # Require at least one identifier, but not necessarily both
        if not emr_id and not encounter_id:
            raise ValueError("Either emr_id or encounter_id is required for summary entries")
        if not note:
            raise ValueError("note is required for summary entries")
        
        # Insert new summary record
        query = """
            INSERT INTO summaries (emr_id, encounter_id, note)
            VALUES (%s, %s, %s)
            RETURNING *
        """
        
        cursor.execute(query, (emr_id, encounter_id, note))
        
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


def get_summary_by_encounter_id(conn, encounter_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a summary record by Encounter ID.
    
    Args:
        conn: PostgreSQL database connection
        encounter_id: Encounter identifier UUID to search for
        
    Returns:
        Dictionary with the summary data, or None if not found
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT * FROM summaries
            WHERE encounter_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
        """
        
        cursor.execute(query, (encounter_id,))
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


def save_alert(conn, alert_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save or create an alert record in the alerts table.
    
    Args:
        conn: PostgreSQL database connection
        alert_dict: Dictionary containing alert data with keys:
            - source: str (required) - 'vm', 'server', 'workflow', or 'monitor'
            - source_id: str (required) - Source identifier
            - severity: str (required) - 'critical', 'warning', or 'info'
            - message: str (required) - Alert message
            - details: dict (optional) - Additional details as JSONB
            - timestamp: str (optional) - ISO 8601 timestamp (defaults to now)
    
    Returns:
        Dictionary with the saved alert data including alert_id and created_at
    
    Raises:
        psycopg2.Error: If database operation fails
        ValueError: If required fields are missing or invalid
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Validate required fields
        required_fields = ['source', 'source_id', 'severity', 'message']
        for field in required_fields:
            if field not in alert_dict or not alert_dict[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate source
        valid_sources = ['vm', 'server', 'workflow', 'monitor']
        if alert_dict['source'] not in valid_sources:
            raise ValueError(f"Invalid source: {alert_dict['source']}. Must be one of: {', '.join(valid_sources)}")
        
        # Validate severity
        valid_severities = ['critical', 'warning', 'info']
        if alert_dict['severity'] not in valid_severities:
            raise ValueError(f"Invalid severity: {alert_dict['severity']}. Must be one of: {', '.join(valid_severities)}")
        
        # Prepare data for insertion
        source = alert_dict['source']
        source_id = alert_dict['source_id']
        severity = alert_dict['severity']
        message = alert_dict['message']
        details = alert_dict.get('details')
        timestamp = alert_dict.get('timestamp')
        
        # Convert details to JSONB if provided
        details_jsonb = Json(details) if details else None
        
        # Use provided timestamp or default to now
        if timestamp:
            # Parse timestamp string to datetime if needed
            if isinstance(timestamp, str):
                # Remove 'Z' suffix and parse
                timestamp_clean = timestamp.replace('Z', '').replace('+00:00', '')
                try:
                    # Try parsing ISO format
                    created_at_dt = datetime.fromisoformat(timestamp_clean)
                    if created_at_dt.tzinfo is None:
                        created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
                    created_at = created_at_dt
                except ValueError:
                    # If parsing fails, use the string as-is and let PostgreSQL handle it
                    created_at = timestamp
            else:
                created_at = timestamp
        else:
            created_at = datetime.now(timezone.utc)
        
        # Insert alert
        query = """
            INSERT INTO alerts (source, source_id, severity, message, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING alert_id, source, source_id, severity, message, details, 
                      resolved, resolved_at, resolved_by, created_at, updated_at
        """
        
        cursor.execute(query, (source, source_id, severity, message, details_jsonb, created_at))
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result
        alert_record = dict(result)
        return alert_record
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    except ValueError as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def get_alerts(conn, filters: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    Retrieve alerts with optional filtering and pagination.
    
    Args:
        conn: PostgreSQL database connection
        filters: Optional dictionary with filter keys:
            - source: str - Filter by source
            - source_id: str - Filter by source ID
            - severity: str - Filter by severity
            - resolved: bool - Filter by resolved status
        limit: Maximum number of alerts to return (default: 50)
        offset: Pagination offset (default: 0)
    
    Returns:
        Tuple of (list of alert dictionaries, total count)
    
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Build WHERE clause
        where_conditions = []
        query_params = []
        
        if filters:
            if 'source' in filters and filters['source']:
                where_conditions.append("source = %s")
                query_params.append(filters['source'])
            
            if 'source_id' in filters and filters['source_id']:
                where_conditions.append("source_id = %s")
                query_params.append(filters['source_id'])
            
            if 'severity' in filters and filters['severity']:
                where_conditions.append("severity = %s")
                query_params.append(filters['severity'])
            
            if 'resolved' in filters:
                resolved = filters['resolved']
                if isinstance(resolved, bool):
                    where_conditions.append("resolved = %s")
                    query_params.append(resolved)
                elif isinstance(resolved, str):
                    # Handle string "true"/"false"
                    resolved_bool = resolved.lower() in ('true', '1', 'yes')
                    where_conditions.append("resolved = %s")
                    query_params.append(resolved_bool)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM alerts {where_clause}"
        cursor.execute(count_query, tuple(query_params))
        total_result = cursor.fetchone()
        total = total_result['total'] if total_result else 0
        
        # Get paginated results
        query = f"""
            SELECT alert_id, source, source_id, severity, message, details,
                   resolved, resolved_at, resolved_by, created_at, updated_at
            FROM alerts
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        
        query_params.extend([limit, offset])
        cursor.execute(query, tuple(query_params))
        results = cursor.fetchall()
        
        # Format results
        alerts = [dict(row) for row in results]
        
        return alerts, total
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def resolve_alert(conn, alert_id: str, resolved_by: Optional[str] = None) -> Dict[str, Any]:
    """
    Mark an alert as resolved.
    
    Args:
        conn: PostgreSQL database connection
        alert_id: Alert UUID to resolve
        resolved_by: Optional identifier of who/what resolved the alert
    
    Returns:
        Dictionary with the updated alert data
    
    Raises:
        psycopg2.Error: If database operation fails
        ValueError: If alert not found
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First check if alert exists
        check_query = "SELECT alert_id FROM alerts WHERE alert_id = %s"
        cursor.execute(check_query, (alert_id,))
        existing = cursor.fetchone()
        
        if not existing:
            raise ValueError(f"Alert not found: {alert_id}")
        
        # Update alert
        update_query = """
            UPDATE alerts
            SET resolved = TRUE,
                resolved_at = CURRENT_TIMESTAMP,
                resolved_by = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE alert_id = %s
            RETURNING alert_id, source, source_id, severity, message, details,
                      resolved, resolved_at, resolved_by, created_at, updated_at
        """
        
        cursor.execute(update_query, (resolved_by, alert_id))
        result = cursor.fetchone()
        conn.commit()
        
        if not result:
            raise ValueError(f"Failed to resolve alert: {alert_id}")
        
        # Format the result
        alert_record = dict(result)
        return alert_record
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    except ValueError as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def save_experity_process_time(conn, process_time_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save or create an Experity process time record.
    
    Args:
        conn: PostgreSQL database connection
        process_time_dict: Dictionary containing process time data with keys:
            - process_name: str (required) - 'Encounter process time' or 'Experity process time'
            - started_at: str (required) - ISO 8601 timestamp
            - ended_at: str (required) - ISO 8601 timestamp
            - encounter_id: str (optional) - Encounter ID UUID
    
    Returns:
        Dictionary with the saved process time data including process_time_id and created_at
    
    Raises:
        psycopg2.Error: If database operation fails
        ValueError: If required fields are missing or invalid
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Validate required fields
        required_fields = ['process_name', 'started_at', 'ended_at']
        for field in required_fields:
            if field not in process_time_dict or not process_time_dict[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate process_name
        valid_names = ['Encounter process time', 'Experity process time']
        if process_time_dict['process_name'] not in valid_names:
            raise ValueError(f"Invalid process_name: {process_time_dict['process_name']}. Must be one of: {', '.join(valid_names)}")
        
        # Parse timestamps
        started_at = process_time_dict['started_at']
        if isinstance(started_at, str):
            started_at_clean = started_at.replace('Z', '').replace('+00:00', '')
            try:
                started_at_dt = datetime.fromisoformat(started_at_clean)
                if started_at_dt.tzinfo is None:
                    started_at_dt = started_at_dt.replace(tzinfo=timezone.utc)
                started_at = started_at_dt
            except ValueError:
                raise ValueError(f"Invalid started_at timestamp format: {started_at}")
        
        ended_at = process_time_dict['ended_at']
        if isinstance(ended_at, str):
            ended_at_clean = ended_at.replace('Z', '').replace('+00:00', '')
            try:
                ended_at_dt = datetime.fromisoformat(ended_at_clean)
                if ended_at_dt.tzinfo is None:
                    ended_at_dt = ended_at_dt.replace(tzinfo=timezone.utc)
                ended_at = ended_at_dt
            except ValueError:
                raise ValueError(f"Invalid ended_at timestamp format: {ended_at}")
        
        # Get encounter_id if provided
        encounter_id = process_time_dict.get('encounter_id')
        
        # Insert process time record
        query = """
            INSERT INTO experity_process_time (process_name, started_at, ended_at, encounter_id)
            VALUES (%s, %s, %s, %s)
            RETURNING process_time_id, process_name, started_at, ended_at, 
                      duration_seconds, created_at, updated_at, encounter_id
        """
        
        cursor.execute(query, (process_time_dict['process_name'], started_at, ended_at, encounter_id))
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result
        process_time_record = dict(result)
        return process_time_record
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    except ValueError as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def get_experity_process_times(conn, filters: Optional[Dict[str, Any]] = None, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    Retrieve Experity process time records with optional filtering and pagination.
    
    Args:
        conn: PostgreSQL database connection
        filters: Optional dictionary with filter keys:
            - process_name: str - Filter by process name
            - started_after: str - ISO 8601 timestamp (only records started after this)
            - started_before: str - ISO 8601 timestamp (only records started before this)
            - completed_only: bool - Only return records with ended_at set
            - encounter_id: str - Filter by encounter ID
        limit: Maximum number of records to return (default: 50, max: 100)
        offset: Number of records to skip (default: 0)
    
    Returns:
        Tuple of (list of process time records, total count)
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if filters:
            if 'process_name' in filters:
                where_conditions.append("process_name = %s")
                params.append(filters['process_name'])
            
            if 'encounter_id' in filters:
                where_conditions.append("encounter_id = %s")
                params.append(filters['encounter_id'])
            
            if 'started_after' in filters:
                where_conditions.append("started_at >= %s")
                started_after = filters['started_after']
                if isinstance(started_after, str):
                    started_at_clean = started_after.replace('Z', '').replace('+00:00', '')
                    started_at_dt = datetime.fromisoformat(started_at_clean)
                    if started_at_dt.tzinfo is None:
                        started_at_dt = started_at_dt.replace(tzinfo=timezone.utc)
                    params.append(started_at_dt)
                else:
                    params.append(started_after)
            
            if 'started_before' in filters:
                where_conditions.append("started_at <= %s")
                started_before = filters['started_before']
                if isinstance(started_before, str):
                    started_before_clean = started_before.replace('Z', '').replace('+00:00', '')
                    started_before_dt = datetime.fromisoformat(started_before_clean)
                    if started_before_dt.tzinfo is None:
                        started_before_dt = started_before_dt.replace(tzinfo=timezone.utc)
                    params.append(started_before_dt)
                else:
                    params.append(started_before)
            
            if filters.get('completed_only', False):
                where_conditions.append("ended_at IS NOT NULL")
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM experity_process_time WHERE {where_clause}"
        cursor.execute(count_query, tuple(params))
        total = cursor.fetchone()['total']
        
        # Get paginated results
        query = f"""
            SELECT process_time_id, process_name, started_at, ended_at, 
                   duration_seconds, created_at, updated_at, encounter_id
            FROM experity_process_time
            WHERE {where_clause}
            ORDER BY started_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Convert to list of dicts
        process_times = [dict(row) for row in results]
        
        return process_times, total
        
    except psycopg2.Error as e:
        raise e
    finally:
        cursor.close()


def update_server_health_partial(conn, server_data: Dict[str, Any]) -> Dict[str, Any]:
    """Partially update a server health record (only updates provided fields).
    
    Args:
        conn: PostgreSQL database connection
        server_data: Dictionary containing server health data with:
            - server_id: string (required) - Server identifier
            - status: Optional string - Server status
            - metadata: Optional dict - Metadata object with system metrics
        
    Returns:
        Dictionary with the updated server health data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        server_id = server_data.get('server_id')
        if not server_id:
            raise ValueError("server_id is required")
        
        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        update_values = []
        
        if 'status' in server_data and server_data['status']:
            update_fields.append("status = %s")
            update_values.append(server_data['status'])
        
        if 'metadata' in server_data:
            metadata_json = None
            if server_data['metadata']:
                metadata_json = json.dumps(server_data['metadata'])
            update_fields.append("metadata = %s::jsonb")
            update_values.append(metadata_json)
        
        # Always update last_heartbeat and updated_at
        update_fields.append("last_heartbeat = CURRENT_TIMESTAMP")
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        
        if not update_fields:
            # No fields to update, just return existing record
            return get_server_health_by_server_id(conn, server_id)
        
        query = f"""
            UPDATE server_health
            SET {', '.join(update_fields)}
            WHERE server_id = %s
            RETURNING *
        """
        
        update_values.append(server_id)
        cursor.execute(query, tuple(update_values))
        
        result = cursor.fetchone()
        conn.commit()
        
        if not result:
            raise ValueError(f"Server with ID '{server_id}' not found")
        
        # Format the result
        formatted_result = dict(result)
        
        # Convert timestamps
        if formatted_result.get('last_heartbeat') and isinstance(formatted_result['last_heartbeat'], datetime):
            formatted_result['last_heartbeat'] = formatted_result['last_heartbeat'].isoformat() + 'Z'
        
        if formatted_result.get('created_at') and isinstance(formatted_result['created_at'], datetime):
            formatted_result['created_at'] = formatted_result['created_at'].isoformat() + 'Z'
        
        if formatted_result.get('updated_at') and isinstance(formatted_result['updated_at'], datetime):
            formatted_result['updated_at'] = formatted_result['updated_at'].isoformat() + 'Z'
        
        # Parse metadata JSONB
        if formatted_result.get('metadata') and isinstance(formatted_result['metadata'], str):
            formatted_result['metadata'] = json.loads(formatted_result['metadata'])
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def sync_server_health_from_vms(conn, server_id: str) -> Optional[Dict[str, Any]]:
    """
    Recalculate a server's status from all of its VMs.
    
    Rules:
      - If any VM is 'unhealthy'          -> server = 'unhealthy'
      - Else if any VM is healthy or idle -> server = 'healthy'
      - Else (no VMs or only unknown)     -> 'down'
    """
    if not server_id:
        return None

    # Get all VMs for this server
    vms = get_vms_by_server_id(conn, server_id)

    if not vms:
        # No VMs for this server; just return current server record (if any)
        return get_server_health_by_server_id(conn, server_id)

    # Determine aggregate server status from VM statuses
    vm_statuses = [str(vm.get("status", "")).lower() for vm in vms]

    if any(status == "unhealthy" for status in vm_statuses):
        new_status = "unhealthy"
    elif any(status in ("healthy", "idle") for status in vm_statuses):
        new_status = "healthy"
    else:
        new_status = "down"

    # Use existing partial update helper so timestamps/metadata are handled consistently
    return update_server_health_partial(
        conn,
        {
            "server_id": server_id,
            "status": new_status,
        },
    )


def sync_vms_from_server_status(conn, server_id: str, server_status: str) -> None:
    """
    Propagate a server status change down to its VMs.
    
    Behaviour:
      - If server is 'down' or 'unhealthy' -> mark all its VMs as 'unhealthy'
      - If server is 'healthy'             -> do nothing (VMs stay independent)
    """
    if not server_id or not server_status:
        return

    normalized_status = str(server_status).lower()
    if normalized_status not in ("down", "unhealthy"):
        # Only push "bad" states down; otherwise VMs manage their own status
        return

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE vm_health
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = %s
            """,
            ("unhealthy", server_id),
        )
        conn.commit()
    finally:
        cursor.close()
        
        
def update_vm_health_partial(conn, vm_data: Dict[str, Any]) -> Dict[str, Any]:
    """Partially update a VM health record (only updates provided fields).
    
    Args:
        conn: PostgreSQL database connection
        vm_data: Dictionary containing VM health data with:
            - vm_id: string (required) - VM identifier
            - server_id: Optional string - Server identifier
            - status: Optional string - VM status
            - processing_queue_id: Optional UUID - Queue ID
            - workflow_status: Optional string - Workflow status
            - metadata: Optional dict - Metadata object
        
    Returns:
        Dictionary with the updated VM health data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        vm_id = vm_data.get('vm_id')
        if not vm_id:
            raise ValueError("vm_id is required")
        
        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        update_values = []
        
        if 'server_id' in vm_data:
            update_fields.append("server_id = %s")
            update_values.append(vm_data['server_id'])
        
        if 'status' in vm_data and vm_data['status']:
            update_fields.append("status = %s")
            update_values.append(vm_data['status'])
        
        if 'processing_queue_id' in vm_data:
            update_fields.append("processing_queue_id = %s")
            update_values.append(vm_data['processing_queue_id'])
        
        if 'workflow_status' in vm_data:
            update_fields.append("workflow_status = %s")
            update_values.append(vm_data['workflow_status'])
        
        if 'metadata' in vm_data:
            metadata_json = None
            if vm_data['metadata']:
                metadata_json = json.dumps(vm_data['metadata'])
            update_fields.append("metadata = %s::jsonb")
            update_values.append(metadata_json)
        
        # Always update last_heartbeat and updated_at
        update_fields.append("last_heartbeat = CURRENT_TIMESTAMP")
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        
        if not update_fields:
            # No fields to update, just return existing record
            return get_vm_health_by_vm_id(conn, vm_id)
        
        query = f"""
            UPDATE vm_health
            SET {', '.join(update_fields)}
            WHERE vm_id = %s
            RETURNING *
        """
        
        update_values.append(vm_id)
        cursor.execute(query, tuple(update_values))
        
        result = cursor.fetchone()
        conn.commit()
        
        if not result:
            raise ValueError(f"VM with ID '{vm_id}' not found")
        
        # Format the result
        formatted_result = dict(result)
        
        # Convert timestamps
        if formatted_result.get('last_heartbeat') and isinstance(formatted_result['last_heartbeat'], datetime):
            formatted_result['last_heartbeat'] = formatted_result['last_heartbeat'].isoformat() + 'Z'
        
        if formatted_result.get('created_at') and isinstance(formatted_result['created_at'], datetime):
            formatted_result['created_at'] = formatted_result['created_at'].isoformat() + 'Z'
        
        if formatted_result.get('updated_at') and isinstance(formatted_result['updated_at'], datetime):
            formatted_result['updated_at'] = formatted_result['updated_at'].isoformat() + 'Z'
        
        # Parse metadata JSONB
        if formatted_result.get('metadata') and isinstance(formatted_result['metadata'], str):
            formatted_result['metadata'] = json.loads(formatted_result['metadata'])
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
