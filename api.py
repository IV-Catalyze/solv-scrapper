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
    from pydantic import BaseModel, Field
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: Required packages not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

# Import authentication module
try:
    from auth import get_current_client, create_token_for_client, TokenData
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
    ],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

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
        payloads.append(decorate_patient_payload(payload))
        if limit is not None and len(payloads) >= limit:
            break

    return payloads


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
        500: {"description": "Database or server error while preparing the dashboard."},
    },
)
async def root(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description="Location identifier to filter patients by."
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

    Parameters mirror the `/patients` JSON endpoint and rely on `prepare_dashboard_patients()` to construct
    the records displayed in the template.
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
            normalized_statuses = DEFAULT_STATUSES.copy()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        locations = fetch_locations(cursor)
        patients = prepare_dashboard_patients(cursor, locationId, normalized_statuses, limit)

        status_summary: Dict[str, int] = {}
        for patient in patients:
            status = patient.get("status_class") or "unknown"
            status_summary[status] = status_summary.get(status, 0) + 1

        return templates.TemplateResponse(
            "patients_table.html",
            {
                "request": request,
                "patients": patients,
                "location_id": locationId,
                "selected_statuses": normalized_statuses,
                "limit": limit,
                "locations": locations,
                "default_statuses": DEFAULT_STATUSES,
                "status_summary": status_summary,
            },
        )
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
        200: {"description": "Ordered list of patient payloads from `prepare_dashboard_patients()`."},
        400: {"description": "Missing or invalid query parameters."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Database or server error while assembling the queue."},
    },
)
async def list_patients(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description="Location identifier to filter patients by. Required."
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
    
    Requires authentication via Bearer token or API key.
    """
    if not locationId:
        raise HTTPException(status_code=400, detail="locationId query parameter is required")

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

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        patients = prepare_dashboard_patients(cursor, locationId, normalized_statuses, limit)
        return [PatientPayload(**patient) for patient in patients]

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

