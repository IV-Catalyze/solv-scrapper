#!/usr/bin/env python3
"""
FastAPI application to expose patient data via REST API.
"""

import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from fastapi import FastAPI, HTTPException, Query, Request, Depends
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel, Field, field_validator
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: Required packages not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Import authentication module
try:
    from app.utils.auth import get_current_client, create_token_for_client, TokenData
    AUTH_ENABLED = True
except ImportError:
    print("Warning: auth.py not found. Authentication will be disabled.")
    get_current_client = None
    create_token_for_client = None
    TokenData = None
    AUTH_ENABLED = False

# Create a dependency that works whether auth is enabled or not
def get_auth_dependency():
    """Return the authentication dependency if auth is enabled, otherwise return a no-op."""
    if AUTH_ENABLED and get_current_client:
        return Depends(get_current_client)
    else:
        # Return a dependency that always passes (no auth required)
        async def no_auth():
            return None
        return Depends(no_auth)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from pathlib import Path

from app.utils.api_client import get_api_token

# Import patient saving functions
try:
    from app.database.utils import normalize_patient_record
    from tests.save_to_db import insert_patients
except ImportError:
    try:
        # Fallback: try importing from old location
        from save_to_db import normalize_patient_record, insert_patients
    except ImportError:
        print("Warning: save_to_db module not found. Patient save endpoint will not work.")
        normalize_patient_record = None
        insert_patients = None

app = FastAPI(
    title="Patient Data API",
    description=(
        "Endpoints for retrieving patient queue data rendered in the dashboard UI or consumed as JSON. "
        "Filters and response fields mirror the helpers defined in `api.py`, such as "
        "`prepare_dashboard_patients`, `build_patient_payload`, and `decorate_patient_payload`. "
        "All API endpoints require authentication via JWT Bearer token or API key."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "Authentication", "description": "Token generation and authentication endpoints."},
        {"name": "Dashboard", "description": "Server-rendered views for the patient queue."},
        {"name": "Patients", "description": "JSON APIs for querying patient records and queue data."},
        {"name": "Encounters", "description": "JSON APIs for creating and managing encounter records."},
    ],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

def normalize_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or None
    return None


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.min
        # Handle trailing Z (Zulu time) which datetime.fromisoformat can't parse directly
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.min

DEFAULT_STATUSES = ["checked_in", "confirmed"]


def resolve_location_id(location_id: Optional[str], *, required: bool = True) -> Optional[str]:
    """
    Normalize `locationId` from the query string with support for a default
    value defined via the DEFAULT_LOCATION_ID environment variable.
    """
    normalized = location_id.strip() if location_id else None
    if normalized:
        return normalized

    env_location_id = os.getenv("DEFAULT_LOCATION_ID", "").strip()
    if env_location_id:
        return env_location_id

    if required:
        raise HTTPException(
            status_code=400,
            detail=(
                "locationId query parameter is required. "
                "Provide ?locationId=<ID> or configure DEFAULT_LOCATION_ID."
            ),
        )

    return None


def use_remote_api_for_reads() -> bool:
    """
    Determine whether to read queue data from the remote production API
    instead of the local database.

    Controlled by USE_REMOTE_API_FOR_READS env var (default: false).
    """
    return os.getenv("USE_REMOTE_API_FOR_READS", "false").strip().lower() in {"1", "true", "yes", "on"}


class PatientPayload(BaseModel):
    """Schema describing the normalized patient payload returned by the API."""

    emr_id: Optional[str] = Field(None, description="EMR identifier for the patient.")
    booking_id: Optional[str] = Field(None, description="Internal booking identifier.")
    booking_number: Optional[str] = Field(None, description="Human-readable booking number.")
    patient_number: Optional[str] = Field(None, description="Clinic-specific patient number.")
    location_id: Optional[str] = Field(None, description="Unique identifier for the clinic location.")
    location_name: Optional[str] = Field(None, description="Display name of the clinic location.")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.")
    dob: Optional[str] = Field(None, description="Date of birth in ISO 8601 format.")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.")
    captured_at: Optional[str] = Field(None, description="Timestamp indicating when the record was captured.")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.")
    created_at: Optional[str] = Field(None, description="Record creation timestamp.")
    updated_at: Optional[str] = Field(None, description="Record last update timestamp.")
    status: Optional[str] = Field(None, description="Current queue status for the patient.")
    appointment_date: Optional[str] = Field(None, description="Scheduled appointment date (if provided).")
    appointment_date_at_clinic_tz: Optional[str] = Field(
        None, description="Appointment date/time localized to the clinic timezone."
    )
    calendar_date: Optional[str] = Field(None, description="Calendar date associated with the visit.")
    status_class: Optional[str] = Field(None, description="Normalized status (lowercase/underscored) for styling.")
    status_label: Optional[str] = Field(None, description="Human-friendly status label.")
    captured_display: Optional[str] = Field(None, description="Formatted capture timestamp for UI display.")
    source: Optional[str] = Field(None, description="Origin of the record (e.g., 'confirmed', 'pending').")

    class Config:
        extra = "allow"


def fetch_locations(cursor) -> List[Dict[str, Optional[str]]]:
    cursor.execute(
        """
        SELECT DISTINCT
            location_id,
            location_name
        FROM (
            SELECT location_id, location_name FROM pending_patients WHERE location_id IS NOT NULL
            UNION
            SELECT location_id, location_name FROM patients WHERE location_id IS NOT NULL
        ) AS combined
        ORDER BY location_name NULLS LAST, location_id
        """
    )
    rows = cursor.fetchall()
    locations: List[Dict[str, Optional[str]]] = []
    for row in rows:
        loc_id = row.get("location_id")
        if not loc_id:
            continue
        locations.append(
            {
                "location_id": loc_id,
                "location_name": row.get("location_name"),
            }
        )
    return locations


async def fetch_remote_patients(
    location_id: str,
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Fetch patient queue data from the remote production API instead of the local DB.

    Uses API_URL /patients endpoint with the same query parameters that this API exposes.
    """
    if not HTTPX_AVAILABLE:
        raise HTTPException(status_code=500, detail="httpx is required for remote API reads")

    api_url_env = os.getenv("API_URL")
    if not api_url_env or not api_url_env.strip():
        raise HTTPException(status_code=500, detail="API_URL must be set for remote API reads")

    api_base_url = api_url_env.strip().rstrip("/")
    url = f"{api_base_url}/patients"

    params: Dict[str, Any] = {"locationId": location_id}
    if statuses:
        # Repeat statuses param for each value to match existing API contract
        params["statuses"] = statuses
    if limit is not None:
        params["limit"] = limit

    api_key = os.getenv("API_KEY")
    api_token = os.getenv("API_TOKEN")

    headers: Dict[str, str] = {"Content-Type": "application/json"}

    # Prefer API key if present; otherwise use token / auto-token
    if api_key:
        headers["X-API-Key"] = api_key
    else:
        if not api_token:
            # Auto-fetch token using same helper as monitor/api_client
            token = await get_api_token(api_base_url)
            api_token = token or ""
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:  # type: ignore[attr-defined]
            response = await client.get(url, params=params, headers=headers)

        if response.status_code != 200:
            detail = None
            try:
                data = response.json()
                detail = data.get("detail")
            except Exception:
                pass
            msg = detail or f"Remote API returned {response.status_code}"
            raise HTTPException(status_code=502, detail=msg)

        data = response.json()
        if not isinstance(data, list):
            raise HTTPException(status_code=502, detail="Remote API /patients response is not a list")

        # Data should already be in PatientPayload shape; normalize minimally
        return data

    except httpx.TimeoutException:  # type: ignore[attr-defined]
        raise HTTPException(status_code=504, detail="Remote API request timed out")
    except httpx.RequestError as e:  # type: ignore[attr-defined]
        raise HTTPException(status_code=502, detail=f"Error calling remote API: {e}")


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


def prepare_dashboard_patients(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    selected = [normalize_status(status) for status in statuses if normalize_status(status)]
    selected_set = set(selected)
    results: List[Dict[str, Any]] = []

    confirmed_records = fetch_confirmed_records(
        cursor,
        location_id,
        limit,
    )
    for record in confirmed_records:
        payload = build_patient_payload(record)
        status = normalize_status(payload.get("status")) or "confirmed"
        payload["status"] = status
        if selected_set and status not in selected_set:
            continue
        payload["source"] = "confirmed"
        results.append(decorate_patient_payload(payload))

    # Sort by captured_at descending then updated_at
    def sort_key(item: Dict[str, Any]):
        captured = parse_datetime(item.get("captured_at"))
        updated = parse_datetime(item.get("updated_at"))
        return (captured, updated)

    results.sort(key=sort_key, reverse=True)

    if limit is not None:
        results = results[:limit]

    return results


def fetch_pending_payloads(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    selected = [normalize_status(status) for status in statuses if normalize_status(status)]
    selected_set = set(selected)
    records = fetch_pending_records(cursor, location_id, None)
    payloads: List[Dict[str, Any]] = []

    for record in records:
        payload = build_patient_payload(record)
        status = normalize_status(payload.get("status")) or normalize_status(record.get("status")) or "checked_in"
        if selected_set and status not in selected_set:
            continue
        payload["status"] = status
        payload["source"] = "pending"
        payloads.append(decorate_patient_payload(payload))
        if limit is not None and len(payloads) >= limit:
            break

    return payloads


def get_local_patients(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Gather patient payloads from the local database (confirmed + pending) to
    mirror the remote API shape.
    """
    confirmed = prepare_dashboard_patients(cursor, location_id, statuses, None)
    pending = fetch_pending_payloads(cursor, location_id, statuses, None)

    combined = confirmed + pending

    def sort_key(item: Dict[str, Any]):
        captured = parse_datetime(item.get("captured_at"))
        updated = parse_datetime(item.get("updated_at"))
        return (captured, updated)

    combined.sort(key=sort_key, reverse=True)

    if limit is not None:
        combined = combined[:limit]

    return combined


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


def save_encounter(conn, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save or update an encounter record in the database.
    
    Args:
        conn: PostgreSQL database connection
        encounter_data: Dictionary containing encounter data
        
    Returns:
        Dictionary with the saved encounter data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    import json
    from psycopg2.extras import Json
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Parse started_at timestamp if provided
        started_at = None
        if encounter_data.get('started_at'):
            started_at = parse_datetime(encounter_data['started_at'])
            if started_at == datetime.min:
                started_at = None
        
        # Validate chief_complaints is not empty
        chief_complaints = encounter_data.get('chief_complaints', [])
        if not chief_complaints or len(chief_complaints) == 0:
            raise ValueError("chief_complaints cannot be empty. At least one complaint is required.")
        
        # Convert chief_complaints to JSONB
        chief_complaints_json = Json(chief_complaints)
        
        # Use INSERT ... ON CONFLICT to handle duplicates (update on conflict)
        # Note: chief_complaints is always updated since it's required
        query = """
            INSERT INTO encounters (
                id, encounter_id, client_id, patient_id, trauma_type,
                chief_complaints, status, created_by, started_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (encounter_id) 
            DO UPDATE SET
                client_id = EXCLUDED.client_id,
                patient_id = EXCLUDED.patient_id,
                trauma_type = EXCLUDED.trauma_type,
                chief_complaints = EXCLUDED.chief_complaints,
                status = EXCLUDED.status,
                created_by = EXCLUDED.created_by,
                started_at = EXCLUDED.started_at,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        
        cursor.execute(
            query,
            (
                encounter_data['id'],
                encounter_data['encounter_id'],
                encounter_data['client_id'],
                encounter_data['patient_id'],
                encounter_data.get('trauma_type'),
                chief_complaints_json,  # Always provided (validated above)
                encounter_data.get('status'),
                encounter_data.get('created_by'),
                started_at,
            )
        )
        
        result = cursor.fetchone()
        conn.commit()
        
        # Format the result for response
        formatted_result = format_patient_record(result)
        
        # Convert chief_complaints JSONB back to list
        if formatted_result.get('chief_complaints'):
            if isinstance(formatted_result['chief_complaints'], str):
                formatted_result['chief_complaints'] = json.loads(formatted_result['chief_complaints'])
        
        return formatted_result
        
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


def format_encounter_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format encounter record for JSON response."""
    import json
    
    formatted = {
        'id': str(record.get('id', '')),
        'encounter_id': str(record.get('encounter_id', '')),
        'client_id': str(record.get('client_id', '')),
        'patient_id': str(record.get('patient_id', '')),
        'trauma_type': record.get('trauma_type'),
        'chief_complaints': record.get('chief_complaints', []),
        'status': record.get('status'),
        'created_by': record.get('created_by'),
        'started_at': None,
        'created_at': None,
        'updated_at': None,
    }
    
    # Convert datetime objects to ISO format strings
    if record.get('started_at'):
        started_at = record['started_at']
        if isinstance(started_at, datetime):
            formatted['started_at'] = started_at.isoformat()
        elif isinstance(started_at, str):
            formatted['started_at'] = started_at
    
    if record.get('created_at'):
        created_at = record['created_at']
        if isinstance(created_at, datetime):
            formatted['created_at'] = created_at.isoformat()
        elif isinstance(created_at, str):
            formatted['created_at'] = created_at
    
    if record.get('updated_at'):
        updated_at = record['updated_at']
        if isinstance(updated_at, datetime):
            formatted['updated_at'] = updated_at.isoformat()
        elif isinstance(updated_at, str):
            formatted['updated_at'] = updated_at
    
    # Handle chief_complaints JSONB
    if formatted.get('chief_complaints'):
        if isinstance(formatted['chief_complaints'], str):
            try:
                formatted['chief_complaints'] = json.loads(formatted['chief_complaints'])
            except json.JSONDecodeError:
                formatted['chief_complaints'] = []
    
    return formatted


def build_patient_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build patient response payload in normalized structure."""
    captured = record.get("captured_at")
    if isinstance(captured, datetime):
        captured = captured.isoformat()
    created = record.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    updated = record.get("updated_at")
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    raw_payload = record.get("raw_payload")

    payload = {
        "emr_id": record.get("emr_id"),
        "booking_id": record.get("booking_id"),
        "booking_number": record.get("booking_number"),
        "patient_number": record.get("patient_number"),
        "location_id": record.get("location_id"),
        "location_name": record.get("location_name"),
        "legalFirstName": record.get("legal_first_name"),
        "legalLastName": record.get("legal_last_name"),
        "dob": record.get("dob"),
        "mobilePhone": record.get("mobile_phone"),
        "sexAtBirth": record.get("sex_at_birth"),
        "captured_at": captured,
        "reasonForVisit": record.get("reason_for_visit"),
        "created_at": created,
        "updated_at": updated,
    }

    status = record.get("patient_status") or record.get("status")
    if not status and isinstance(raw_payload, dict):
        status = raw_payload.get("status")
    if status:
        payload["status"] = status

    appointment_date = record.get("appointment_date")
    if appointment_date is None and isinstance(raw_payload, dict):
        appointment_date = raw_payload.get("appointment_date")
    if appointment_date:
        payload["appointment_date"] = appointment_date

    appointment_date_clinic_tz = record.get("appointment_date_at_clinic_tz")
    if appointment_date_clinic_tz is None and isinstance(raw_payload, dict):
        appointment_date_clinic_tz = raw_payload.get("appointment_date_at_clinic_tz")
    if appointment_date_clinic_tz:
        payload["appointment_date_at_clinic_tz"] = appointment_date_clinic_tz

    calendar_date = record.get("calendar_date")
    if calendar_date is None and isinstance(raw_payload, dict):
        calendar_date = raw_payload.get("calendar_date")
    if calendar_date:
        payload["calendar_date"] = calendar_date

    return payload


def decorate_patient_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add presentation-friendly fields to the patient payload."""
    status_class = normalize_status(payload.get("status")) or "unknown"
    payload["status_class"] = status_class
    payload["status_label"] = status_class.replace("_", " ").title()

    captured_display = None
    captured_raw = payload.get("captured_at")
    captured_dt = parse_datetime(captured_raw)
    if captured_dt > datetime.min:
        captured_display = captured_dt.strftime("%b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")
    payload["captured_display"] = captured_display

    return payload


# Token generation request model
class TokenRequest(BaseModel):
    """Request model for token generation."""
    client_id: str = Field(..., description="Identifier for the client/service requesting access")
    expires_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,  # Max 1 year
        description="Optional expiration time in hours (default: 24 hours)"
    )


# Patient data submission models
class PatientCreateRequest(BaseModel):
    """Request model for creating a single patient record."""
    emr_id: Optional[str] = Field(None, description="EMR identifier for the patient.")
    booking_id: Optional[str] = Field(None, description="Internal booking identifier.")
    booking_number: Optional[str] = Field(None, description="Human-readable booking number.")
    patient_number: Optional[str] = Field(None, description="Clinic-specific patient number.")
    location_id: Optional[str] = Field(None, description="Unique identifier for the clinic location.")
    location_name: Optional[str] = Field(None, description="Display name of the clinic location.")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.")
    dob: Optional[str] = Field(None, description="Date of birth.")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.")
    status: Optional[str] = Field(None, description="Current queue status for the patient.")
    captured_at: Optional[str] = Field(None, description="Timestamp indicating when the record was captured.")
    
    class Config:
        extra = "allow"


class PatientBatchRequest(BaseModel):
    """Request model for creating multiple patient records."""
    patients: List[PatientCreateRequest] = Field(..., description="List of patient records to create.")


class StatusUpdateRequest(BaseModel):
    """Request model for updating patient status."""
    status: str = Field(..., description="New queue status for the patient.")


# Encounter data submission models
class ChiefComplaint(BaseModel):
    """Model for a single chief complaint."""
    id: str = Field(..., description="Unique identifier for the chief complaint.")
    description: str = Field(..., description="Description of the complaint.")
    type: str = Field(..., description="Type of complaint (e.g., 'trauma').")
    part: str = Field(..., description="Body part affected.")
    bodyParts: List[str] = Field(default_factory=list, description="List of affected body parts.")


class EncounterCreateRequest(BaseModel):
    """Request model for creating an encounter record."""
    id: str = Field(..., description="Unique identifier for the encounter (UUID).")
    clientId: str = Field(..., description="Client identifier (UUID).")
    patientId: str = Field(..., description="Patient identifier (UUID). Required.")
    encounterId: str = Field(..., description="Encounter identifier (UUID).")
    traumaType: Optional[str] = Field(None, description="Type of trauma (e.g., 'BURN').")
    chiefComplaints: List[ChiefComplaint] = Field(..., min_length=1, description="List of chief complaints. At least one complaint is required.")
    status: Optional[str] = Field(None, description="Status of the encounter (e.g., 'COMPLETE').")
    createdBy: Optional[str] = Field(None, description="Email or identifier of the user who created the encounter.")
    startedAt: Optional[str] = Field(None, description="ISO 8601 timestamp when the encounter started.")
    
    @field_validator('chiefComplaints')
    @classmethod
    def validate_chief_complaints_not_empty(cls, v: List[ChiefComplaint]) -> List[ChiefComplaint]:
        """Ensure chief_complaints is not empty."""
        if not v or len(v) == 0:
            raise ValueError('chiefComplaints cannot be empty. At least one complaint is required.')
        return v
    
    class Config:
        extra = "allow"


class EncounterResponse(BaseModel):
    """Response model for encounter records."""
    id: str = Field(..., description="Unique identifier for the encounter (UUID).")
    encounter_id: str = Field(..., description="Encounter identifier (UUID).")
    client_id: str = Field(..., description="Client identifier (UUID).")
    patient_id: str = Field(..., description="Patient identifier (UUID).")
    trauma_type: Optional[str] = Field(None, description="Type of trauma.")
    chief_complaints: List[Dict[str, Any]] = Field(default_factory=list, description="List of chief complaints.")
    status: Optional[str] = Field(None, description="Status of the encounter.")
    created_by: Optional[str] = Field(None, description="User who created the encounter.")
    started_at: Optional[str] = Field(None, description="ISO 8601 timestamp when the encounter started.")
    created_at: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was created.")
    updated_at: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was last updated.")
    
    class Config:
        extra = "allow"



@app.post(
    "/auth/token",
    tags=["Authentication"],
    summary="Generate access token",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Access token generated successfully."},
        400: {"description": "Invalid request parameters."},
    },
)
async def generate_token(request: TokenRequest):
    """
    Generate a JWT access token for API authentication.
    
    This endpoint allows clients to obtain an access token that can be used
    to authenticate subsequent API requests. The token includes:
    - Client identifier
    - Expiration time
    - Issued timestamp
    
    **Usage:**
    1. Call this endpoint with your client_id to get a token
    2. Include the token in subsequent requests using the Authorization header:
       `Authorization: Bearer <token>`
    3. Tokens expire after the specified time (default: 24 hours)
    
    **Alternative:** You can also use API key authentication by setting the
    `X-API-Key` header instead of a Bearer token.
    """
    if not create_token_for_client:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable"
        )
    
    try:
        token_data = create_token_for_client(
            client_id=request.client_id,
            expires_hours=request.expires_hours
        )
        return token_data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate token: {str(e)}"
        )


@app.get(
    "/",
    tags=["Dashboard"],
    summary="Render the patient dashboard",
    response_class=HTMLResponse,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- HTML dashboard rendered via Jinja template -->"}},
            "description": "HTML table view of the patient queue filtered by the supplied query parameters.",
        },
        500: {"description": "Server error while fetching patient data from remote API."},
    },
)
async def root(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description=(
            "Location identifier to filter patients by. Required unless DEFAULT_LOCATION_ID env var is set."
        ),
    ),
    statuses: Optional[List[str]] = Query(
        default=None,
        alias="statuses",
        description="Filter patients by status. Provide multiple values by repeating the query parameter."
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return."
    ),
):
    """
    Render the patient queue dashboard as HTML.

    Uses the remote production API when location filtering is available;
    otherwise falls back to the local database.
    """
    # Normalize locationId: convert empty strings to None
    # FastAPI may receive empty string from form submission, normalize it to None
    normalized_location_id = resolve_location_id(locationId, required=False)
    
    if statuses is None:
        normalized_statuses = DEFAULT_STATUSES.copy()
    else:
        normalized_statuses = [
            normalize_status(status)
            for status in statuses
            if isinstance(status, str)
        ]
        normalized_statuses = [status for status in normalized_statuses if status]
        if not normalized_statuses:
            normalized_statuses = DEFAULT_STATUSES.copy()

    try:
        use_remote_reads = use_remote_api_for_reads()
        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            patients = await fetch_remote_patients(normalized_location_id, normalized_statuses, limit)

            # Location dropdown is limited to the current location in remote mode
            locations = [
                {
                    "location_id": normalized_location_id,
                    "location_name": None,
                }
            ]
        else:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                patients = get_local_patients(cursor, normalized_location_id, normalized_statuses, limit)
                locations = fetch_locations(cursor)
            finally:
                cursor.close()
                conn.close()

        status_summary: Dict[str, int] = {}
        for patient in patients:
            status = patient.get("status_class") or "unknown"
            status_summary[status] = status_summary.get(status, 0) + 1

        return templates.TemplateResponse(
            "patients_table.html",
            {
                "request": request,
                "patients": patients,
                "location_id": normalized_location_id,
                "selected_statuses": normalized_statuses,
                "limit": limit,
                "locations": locations,
                "default_statuses": DEFAULT_STATUSES,
                "status_summary": status_summary,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get(
    "/patient/{emr_id}",
    tags=["Patients"],
    summary="Get latest patient record by EMR ID",
    response_model=PatientPayload,
    responses={
        200: {"description": "Most recent patient record normalized by `build_patient_payload()`."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        404: {"description": "No patient found for the supplied EMR ID."},
        500: {"description": "Database or server error while fetching the record."},
    },
)
async def get_patient_by_emr_id(
    emr_id: str,
    current_client: TokenData = get_auth_dependency()
) -> PatientPayload:
    """
    Return the most recent patient record matching the supplied EMR ID.

    The query orders rows by `captured_at DESC` and uses `build_patient_payload()` to normalize the result.
    
    Requires authentication via Bearer token or API key.
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query for the most recent patient record with the given emr_id
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
            WHERE emr_id = %s
            ORDER BY captured_at DESC
            LIMIT 1;
        """
        
        cursor.execute(query, (emr_id,))
        record = cursor.fetchone()
        
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emr_id}' not found"
            )
        
        response_payload = build_patient_payload(record)

        return PatientPayload(**response_payload)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@app.post(
    "/patients/create",
    tags=["Patients"],
    summary="Create patient record(s)",
    response_model=Dict[str, Any],
    responses={
        201: {"description": "Patient record(s) created successfully."},
        400: {"description": "Invalid request data."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Database or server error while saving the record(s)."},
    },
)
async def create_patient(
    patient_data: PatientCreateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    Create a single patient record from the provided data.
    
    This endpoint accepts patient data in JSON format and saves it to the database.
    The data will be normalized and validated before insertion.
    
    Requires authentication via Bearer token or API key.
    """
    if not normalize_patient_record or not insert_patients:
        raise HTTPException(
            status_code=503,
            detail="Patient save functionality unavailable"
        )
    
    conn = None
    try:
        # Convert Pydantic model to dict
        patient_dict = patient_data.model_dump(exclude_none=True)
        
        # Normalize the patient record
        normalized = normalize_patient_record(patient_dict)
        
        # Check if emr_id is required
        emr_id = normalized.get("emr_id")
        if not emr_id:
            raise HTTPException(
                status_code=400,
                detail="emr_id is required. Please provide an EMR identifier for the patient."
            )
        
        conn = get_db_connection()

        # If location_id is missing, try to reuse existing record's location_id (and other fields) for updates.
        if not normalized.get("location_id"):
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM patients WHERE emr_id = %s ORDER BY updated_at DESC NULLS LAST, captured_at DESC NULLS LAST LIMIT 1",
                (emr_id,),
            )
            existing = cursor.fetchone()
            cursor.close()

            if existing:
                # Merge: keep any newly provided fields, fill gaps from existing record.
                merge_fields = [
                    "location_id",
                    "location_name",
                    "booking_id",
                    "booking_number",
                    "patient_number",
                    "legal_first_name",
                    "legal_last_name",
                    "dob",
                    "mobile_phone",
                    "sex_at_birth",
                    "reason_for_visit",
                ]
                for field in merge_fields:
                    if normalized.get(field) is None and existing.get(field) is not None:
                        normalized[field] = existing[field]

            # After merge, still no location_id -> cannot create a brand new record without it.
            if not normalized.get("location_id"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "location_id is required for new patients. "
                        "For existing patients, ensure an initial record with location_id was created before "
                        "sending status-only updates."
                    ),
                )

        inserted_count = insert_patients(conn, [normalized], on_conflict='update')
        
        if inserted_count == 0:
            # Record might already exist, try to fetch it
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM patients WHERE emr_id = %s LIMIT 1",
                (normalized['emr_id'],)
            )
            existing = cursor.fetchone()
            cursor.close()
            
            if existing:
                return {
                    "message": "Patient record already exists and was updated",
                    "emr_id": normalized['emr_id'],
                    "status": "updated"
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create patient record"
                )
        
        return {
            "message": "Patient record created successfully",
            "emr_id": normalized['emr_id'],
            "status": "created",
            "inserted_count": inserted_count
        }
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@app.patch(
    "/patients/{emr_id}",
    tags=["Patients"],
    summary="Update patient status",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Patient status updated successfully."},
        400: {"description": "Invalid request data."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        404: {"description": "Patient with the specified EMR ID not found."},
        500: {"description": "Database or server error while updating the status."},
    },
)
async def update_patient_status(
    emr_id: str,
    status_data: StatusUpdateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    Update the queue status for a patient by EMR ID.
    
    This endpoint accepts a status update and applies it to the patient record
    in the database. Only the status field is updated.
    
    Requires authentication via Bearer token or API key.
    """
    if not emr_id or not emr_id.strip():
        raise HTTPException(
            status_code=400,
            detail="emr_id is required in the URL path"
        )
    
    emr_id_clean = emr_id.strip()
    normalized_status = normalize_status(status_data.status)
    
    if not normalized_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status value: {status_data.status}"
        )
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if patient exists
        cursor.execute(
            "SELECT id, emr_id, status FROM patients WHERE emr_id = %s LIMIT 1",
            (emr_id_clean,)
        )
        existing = cursor.fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emr_id_clean}' not found"
            )
        
        # Update status
        cursor.execute(
            """
            UPDATE patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE emr_id = %s
            RETURNING id, emr_id, status, updated_at
            """,
            (normalized_status, emr_id_clean)
        )
        
        updated = cursor.fetchone()
        conn.commit()
        
        return {
            "message": "Patient status updated successfully",
            "emr_id": emr_id_clean,
            "old_status": existing.get("status"),
            "new_status": normalized_status,
            "updated_at": updated.get("updated_at").isoformat() if updated.get("updated_at") else None
        }
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.post(
    "/encounter",
    tags=["Encounters"],
    summary="Create or update encounter record",
    response_model=EncounterResponse,
    status_code=201,
    responses={
        201: {"description": "Encounter record created or updated successfully."},
        400: {"description": "Invalid request data or missing required fields."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Database or server error while saving the encounter."},
    },
)
async def create_encounter(
    encounter_data: EncounterCreateRequest,
    current_client: TokenData = get_auth_dependency()
) -> EncounterResponse:
    """
    Create or update an encounter record from the provided data.
    
    This endpoint accepts encounter data in JSON format and saves it to the database.
    If an encounter with the same `encounterId` already exists, it will be updated.
    
    **Required fields:**
    - `id`: Unique identifier for the encounter (UUID)
    - `patientId`: Patient identifier (UUID) - **REQUIRED**
    - `encounterId`: Encounter identifier (UUID)
    - `clientId`: Client identifier (UUID)
    - `chiefComplaints`: List of chief complaint objects - **REQUIRED (at least one complaint)**
    
    **Optional fields:**
    - `traumaType`: Type of trauma (e.g., "BURN")
    - `status`: Status of the encounter (e.g., "COMPLETE")
    - `createdBy`: Email or identifier of the user who created the encounter
    - `startedAt`: ISO 8601 timestamp when the encounter started
    
    Requires authentication via Bearer token or API key.
    """
    conn = None
    
    try:
        # Validate required fields
        if not encounter_data.patientId:
            raise HTTPException(
                status_code=400,
                detail="patientId is required. Please provide a patient identifier."
            )
        
        if not encounter_data.encounterId:
            raise HTTPException(
                status_code=400,
                detail="encounterId is required. Please provide an encounter identifier."
            )
        
        if not encounter_data.clientId:
            raise HTTPException(
                status_code=400,
                detail="clientId is required. Please provide a client identifier."
            )
        
        # Validate chief_complaints is not empty
        if not encounter_data.chiefComplaints or len(encounter_data.chiefComplaints) == 0:
            raise HTTPException(
                status_code=400,
                detail="chiefComplaints cannot be empty. At least one complaint is required."
            )
        
        # Convert Pydantic model to dict and transform field names
        # Convert chief complaints to list of dicts (already validated to be non-empty)
        chief_complaints_list = [complaint.model_dump() for complaint in encounter_data.chiefComplaints]
        
        encounter_dict = {
            'id': encounter_data.id,
            'encounter_id': encounter_data.encounterId,
            'client_id': encounter_data.clientId,
            'patient_id': encounter_data.patientId,
            'trauma_type': encounter_data.traumaType,
            'chief_complaints': chief_complaints_list,  # Always non-empty (validated above)
            'status': encounter_data.status,
            'created_by': encounter_data.createdBy,
            'started_at': encounter_data.startedAt,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the encounter
        saved_encounter = save_encounter(conn, encounter_dict)
        
        # Format the response
        formatted_response = format_encounter_response(saved_encounter)
        
        return EncounterResponse(**formatted_response)
        
    except HTTPException:
        raise
    except ValueError as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('PORT', os.getenv('API_PORT', '8000')))
    host = os.getenv('API_HOST', '0.0.0.0')
    
    uvicorn.run(app, host=host, port=port)


@app.get(
    "/patients",
    tags=["Patients"],
    summary="List patient queue data for a location",
    response_model=List[PatientPayload],
    responses={
        200: {"description": "Ordered list of patient payloads fetched from remote API."},
        400: {"description": "Missing or invalid query parameters."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Server error while fetching patient data from remote API."},
    },
)
async def list_patients(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description=(
            "Location identifier to filter patients by. Required unless DEFAULT_LOCATION_ID env var is set."
        ),
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return."
    ),
    statuses: Optional[List[str]] = Query(
        default=None,
        alias="statuses",
        description="Filter patients by status. Provide multiple values by repeating the query parameter."
    ),
    current_client: TokenData = get_auth_dependency()
):
    """
    Return the patient queue as JSON, mirroring the data rendered in the dashboard view.
    
    Reads from the remote production API when a location filter is provided;
    otherwise falls back to the local database.
    Requires authentication via Bearer token or API key.
    """
    if statuses is None:
        normalized_statuses = DEFAULT_STATUSES.copy()
    else:
        normalized_statuses = [
            normalize_status(status)
            for status in statuses
            if isinstance(status, str)
        ]
        normalized_statuses = [status for status in normalized_statuses if status]
        if not normalized_statuses:
            raise HTTPException(status_code=400, detail="At least one valid status must be provided")

    try:
        normalized_location_id = resolve_location_id(locationId, required=False)
        use_remote_reads = use_remote_api_for_reads()

        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            patients_raw = await fetch_remote_patients(normalized_location_id, normalized_statuses, limit)
            return [PatientPayload(**patient) for patient in patients_raw]

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            patients_raw = get_local_patients(cursor, normalized_location_id, normalized_statuses, limit)
            return [PatientPayload(**patient) for patient in patients_raw]
        finally:
            cursor.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

