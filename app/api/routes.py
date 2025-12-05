#!/usr/bin/env python3
"""
FastAPI application to expose patient data via REST API.
"""

import os
import sys
import asyncio
import random
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from fastapi import FastAPI, HTTPException, Query, Request, Depends, Path
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel, Field, field_validator, model_validator
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
    from app.utils.auth import get_current_client, TokenData
    AUTH_ENABLED = True
except ImportError:
    print("Warning: auth.py not found. Authentication will be disabled.")
    get_current_client = None
    TokenData = None
    AUTH_ENABLED = False

# Import session-based authentication for web UI
try:
    from app.api.auth_routes import router as auth_router, require_auth
    SESSION_AUTH_ENABLED = True
except ImportError:
    print("Warning: auth_routes.py not found. Session authentication will be disabled.")
    auth_router = None
    # Create a no-op dependency for when auth is disabled
    async def require_auth_noop(request: Request):
        return None
    require_auth = require_auth_noop
    SESSION_AUTH_ENABLED = False

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

# Import Azure AI client
try:
    from app.utils.azure_ai_client import (
        call_azure_ai_agent,
        AzureAIClientError,
        AzureAIAuthenticationError,
        AzureAIRateLimitError,
        AzureAITimeoutError,
        AzureAIResponseError
    )
    AZURE_AI_AVAILABLE = True
except ImportError:
    print("Warning: azure_ai_client.py not found. Experity mapping endpoint will not work.")
    call_azure_ai_agent = None
    AZURE_AI_AVAILABLE = False
    AzureAIClientError = Exception
    AzureAIAuthenticationError = Exception
    AzureAIRateLimitError = Exception
    AzureAITimeoutError = Exception
    AzureAIResponseError = Exception

# Note: parse_encounter_payload and validate_encounter_payload are no longer used
# The endpoint now accepts only emrId and encounterPayload directly

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
    title="Patient Queue API",
    description="""
RESTful API for managing patient data, encounters, queue entries, and summaries.

## Authentication

All API endpoints require **HMAC-SHA256 authentication** via `X-Timestamp` and `X-Signature` headers. See the security schemes below for detailed authentication instructions.

**Base URL:** `https://app-97926.on-aptible.com`
    """,
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Patients",
            "description": "Manage patient records and queue data. Create, update, and query patient information by location and status."
        },
        {
            "name": "Encounters",
            "description": "Create and manage encounter records. Encounters link to patients via EMR ID and contain chief complaints and trauma information."
        },
        {
            "name": "Queue",
            "description": "Manage queue entries for processing encounters. Queue entries track processing status and Experity action mappings."
        },
        {
            "name": "Summaries",
            "description": "Create and retrieve patient summaries. Summaries contain clinical notes linked to patients via EMR ID."
        },
    ],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Customize OpenAPI schema to document HMAC authentication headers
def custom_openapi():
    """
    Customize OpenAPI schema to document HMAC authentication headers.
    This makes the required headers visible in Swagger UI for manual testing.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Ensure components exist
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    # Add HMAC security scheme to components for documentation
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    openapi_schema["components"]["securitySchemes"].update({
        "HMACSignature": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Signature",
            "description": (
                "**Base64-encoded HMAC-SHA256 signature**\n\n"
                "**Step-by-step generation:**\n"
                "1. Get current UTC timestamp in ISO 8601 format\n"
                "2. Hash request body using SHA256 (empty string for GET requests)\n"
                "3. Create canonical string: `METHOD\\nPATH\\nTIMESTAMP\\nBODY_HASH`\n"
                "4. Compute HMAC-SHA256 using your secret key\n"
                "5. Base64 encode the result\n\n"
                "**Example canonical string:**\n"
                "```\n"
                "POST\n"
                "/patients/create\n"
                "2025-11-21T13:49:04Z\n"
                "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456\n"
                "```\n\n"
                "📖 See `docs/HMAC_AUTHENTICATION_GUIDE.md` for detailed instructions and code examples."
            ),
        },
        "HMACTimestamp": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Timestamp",
            "description": (
                "**ISO 8601 UTC timestamp** (e.g., `2025-11-21T13:49:04Z`)\n\n"
                "**Requirements:**\n"
                "- Must be within ±5 minutes of server time\n"
                "- Generate timestamp just before making the request\n"
                "- Always use UTC timezone\n"
                "- Format: `YYYY-MM-DDTHH:MM:SSZ`\n\n"
                "**Example:** `2025-11-21T13:49:04Z`"
            ),
        },
    })
    
    # Add security requirement to all protected endpoints via global security
    # Individual endpoints can override if needed
    if "security" not in openapi_schema:
        openapi_schema["security"] = []
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Include authentication routes
if SESSION_AUTH_ENABLED and auth_router:
    app.include_router(auth_router)

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


def ensure_client_location_access(
    location_id: Optional[str],
    current_client: Optional[TokenData],
) -> Optional[str]:
    """
    Ensure the authenticated client is permitted to access the requested location.

    Returns the effective location ID (may inject the client's sole allowed ID)
    or raises HTTPException when the access rules would be violated.
    """
    if not current_client or current_client.allowed_location_ids is None:
        return location_id

    allowed = current_client.allowed_location_ids
    if not allowed:
        raise HTTPException(status_code=403, detail="No locations are enabled for this client.")

    if location_id:
        if location_id not in allowed:
            raise HTTPException(status_code=403, detail="This client is not permitted to access the requested location.")
        return location_id

    if len(allowed) == 1:
        # Auto-select the only available location for convenience.
        return allowed[0]

    raise HTTPException(
        status_code=403,
        detail="locationId is required for this client. Provide a permitted location ID explicitly.",
    )


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

    emrId: Optional[str] = Field(None, description="EMR identifier for the patient.", alias="emr_id")
    locationId: Optional[str] = Field(None, description="Unique identifier for the clinic location.", alias="location_id")
    locationName: Optional[str] = Field(None, description="Display name of the clinic location.", alias="location_name")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.")
    dob: Optional[str] = Field(None, description="Date of birth in ISO 8601 format.")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.")
    capturedAt: Optional[str] = Field(None, description="Timestamp indicating when the record was captured.", alias="captured_at")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.")
    createdAt: Optional[str] = Field(None, description="Record creation timestamp.", alias="created_at")
    updatedAt: Optional[str] = Field(None, description="Record last update timestamp.", alias="updated_at")
    status: Optional[str] = Field(None, description="Current queue status for the patient.")

    class Config:
        extra = "allow"
        populate_by_name = True


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

    # Sort by capturedAt descending then updatedAt
    def sort_key(item: Dict[str, Any]):
        captured = parse_datetime(item.get("capturedAt") or item.get("captured_at"))
        updated = parse_datetime(item.get("updatedAt") or item.get("updated_at"))
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


def filter_patients_by_search(
    patients: List[Dict[str, Any]],
    search_query: str,
) -> List[Dict[str, Any]]:
    """
    Filter patients by search query (searches name, EMR ID, and phone number).
    
    Args:
        patients: List of patient dictionaries
        search_query: Search term to match against patient data
        
    Returns:
        Filtered list of patients matching the search query
    """
    if not search_query:
        return patients
    
    search_lower = search_query.lower().strip()
    filtered = []
    
    for patient in patients:
        # Search in name fields
        first_name = (patient.get("legalFirstName") or "").lower()
        last_name = (patient.get("legalLastName") or "").lower()
        full_name = f"{first_name} {last_name}".strip()
        
        # Search in EMR ID (support both camelCase and snake_case for backward compatibility)
        emr_id = (patient.get("emrId") or patient.get("emr_id") or "").lower()
        
        # Search in phone number
        phone = (patient.get("mobilePhone") or "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        
        # Check if search query matches any field
        if (search_lower in first_name or 
            search_lower in last_name or 
            search_lower in full_name or
            search_lower in emr_id or
            search_lower in phone):
            filtered.append(patient)
    
    return filtered


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
        captured = parse_datetime(item.get("capturedAt") or item.get("captured_at"))
        updated = parse_datetime(item.get("updatedAt") or item.get("updated_at"))
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
        encounter_data: Dictionary containing encounter data with:
            - encounter_id: UUID (required)
            - emr_id: string (required)
            - encounter_payload: JSONB (required) - full encounter JSON payload
        
    Returns:
        Dictionary with the saved encounter data
        
    Raises:
        psycopg2.Error: If database operation fails
    """
    import json
    from psycopg2.extras import Json
    
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


def format_encounter_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format encounter record for JSON response."""
    import json
    
    formatted = {
        'emr_id': record.get('emr_id', ''),
        'encounter_payload': record.get('encounter_payload', {}),
    }
    
    # Handle encounter_payload JSONB - convert from string if needed
    if formatted.get('encounter_payload'):
        if isinstance(formatted['encounter_payload'], str):
            try:
                formatted['encounter_payload'] = json.loads(formatted['encounter_payload'])
            except json.JSONDecodeError:
                formatted['encounter_payload'] = {}
    
    return formatted


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
    import json
    import uuid
    from psycopg2.extras import Json
    
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


def create_queue_from_encounter(conn, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a queue entry from an encounter record.
    
    Args:
        conn: PostgreSQL database connection
        encounter_data: Dictionary containing encounter data (from save_encounter result)
        
    Returns:
        Dictionary with the created queue data
    """
    import json
    
    # Extract data from encounter
    encounter_id = encounter_data.get('encounter_id')
    if not encounter_id:
        raise ValueError("encounter_id is required to create queue entry")
    
    # Get encounter_payload from encounter
    encounter_payload = encounter_data.get('encounter_payload')
    if not encounter_payload:
        raise ValueError("encounter_payload is required to create queue entry")
    
    # If encounter_payload is a string, parse it
    if isinstance(encounter_payload, str):
        try:
            encounter_payload = json.loads(encounter_payload)
        except json.JSONDecodeError:
            raise ValueError("encounter_payload must be valid JSON")
    
    # Extract chief_complaints and trauma_type from encounter_payload for parsed_payload
    chief_complaints = encounter_payload.get('chiefComplaints') or encounter_payload.get('chief_complaints', [])
    trauma_type = encounter_payload.get('traumaType') or encounter_payload.get('trauma_type')
    
    # Create parsed_payload structure with experityAction set to empty array
    parsed_payload = {
        'trauma_type': trauma_type,
        'chief_complaints': chief_complaints if isinstance(chief_complaints, list) else [],
        'experityAction': []
    }
    
    # Build queue data
    queue_data = {
        'encounter_id': str(encounter_id),
        'emr_id': encounter_data.get('emr_id', ''),
        'status': 'PENDING',
        'raw_payload': encounter_payload,  # Store full encounter payload as raw_payload
        'parsed_payload': parsed_payload,  # Store simplified parsed structure
        'attempts': 0,
    }
    
    # Save queue entry
    return save_queue(conn, queue_data)


def format_queue_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format queue record for JSON response."""
    import json
    
    formatted = {
        'queue_id': str(record.get('queue_id', '')),
        'encounter_id': str(record.get('encounter_id', '')),
        'emr_id': record.get('emr_id', ''),
        'status': record.get('status', 'PENDING'),
        'raw_payload': record.get('raw_payload'),
        'parsed_payload': record.get('parsed_payload'),
        'attempts': record.get('attempts', 0),
        'created_at': None,
        'updated_at': None,
    }
    
    # Convert datetime objects to ISO format strings
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
    
    # Handle JSONB fields
    if formatted.get('raw_payload'):
        if isinstance(formatted['raw_payload'], str):
            try:
                formatted['raw_payload'] = json.loads(formatted['raw_payload'])
            except json.JSONDecodeError:
                pass
    
    if formatted.get('parsed_payload'):
        if isinstance(formatted['parsed_payload'], str):
            try:
                formatted['parsed_payload'] = json.loads(formatted['parsed_payload'])
            except json.JSONDecodeError:
                pass
        
        # Ensure experityAction is an array (handle legacy data)
        if isinstance(formatted['parsed_payload'], dict):
            experity_action = formatted['parsed_payload'].get('experityAction')
            if experity_action is None:
                formatted['parsed_payload']['experityAction'] = []
            elif isinstance(experity_action, dict):
                # Convert legacy single object to array
                formatted['parsed_payload']['experityAction'] = [experity_action]
            elif not isinstance(experity_action, list):
                # If it's not a list, initialize as empty array
                formatted['parsed_payload']['experityAction'] = []
    
    return formatted


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


def format_summary_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format summary record for JSON response with camelCase field names."""
    formatted = {
        'id': record.get('id'),
        'emrId': record.get('emr_id', ''),
        'note': record.get('note', ''),
        'createdAt': None,
        'updatedAt': None,
    }
    
    # Convert datetime objects to ISO format strings
    if record.get('created_at'):
        created_at = record['created_at']
        if isinstance(created_at, datetime):
            formatted['createdAt'] = created_at.isoformat()
        elif isinstance(created_at, str):
            formatted['createdAt'] = created_at
    
    if record.get('updated_at'):
        updated_at = record['updated_at']
        if isinstance(updated_at, datetime):
            formatted['updatedAt'] = updated_at.isoformat()
        elif isinstance(updated_at, str):
            formatted['updatedAt'] = updated_at
    
    return formatted


def build_patient_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build patient response payload in normalized structure with camelCase field names."""
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
        "emrId": record.get("emr_id"),
        "locationId": record.get("location_id"),
        "locationName": record.get("location_name"),
        "legalFirstName": record.get("legal_first_name"),
        "legalLastName": record.get("legal_last_name"),
        "dob": record.get("dob"),
        "mobilePhone": record.get("mobile_phone"),
        "sexAtBirth": record.get("sex_at_birth"),
        "capturedAt": captured,
        "reasonForVisit": record.get("reason_for_visit"),
        "createdAt": created,
        "updatedAt": updated,
    }

    # Note: booking_id, booking_number, patient_number, appointment_date,
    # appointment_date_at_clinic_tz, and calendar_date are intentionally excluded
    # from the response as they are not needed

    status = record.get("patient_status") or record.get("status")
    if not status and isinstance(raw_payload, dict):
        status = raw_payload.get("status")
    if status:
        payload["status"] = status

    return payload


def decorate_patient_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add presentation-friendly fields to the patient payload."""
    # Note: status_class, status_label, and captured_display are only added
    # for dashboard/list endpoints, not for single patient retrieval
    # This function is kept for backward compatibility with list endpoints
    status_class = normalize_status(payload.get("status")) or "unknown"
    payload["status_class"] = status_class
    payload["status_label"] = status_class.replace("_", " ").title()

    captured_display = None
    captured_raw = payload.get("capturedAt") or payload.get("captured_at")
    captured_dt = parse_datetime(captured_raw)
    if captured_dt > datetime.min:
        captured_display = captured_dt.strftime("%b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")
    payload["captured_display"] = captured_display

    return payload


# Token generation endpoint removed - HMAC authentication only


# Patient data submission models
class PatientCreateRequest(BaseModel):
    """Request model for creating a single patient record."""
    emrId: str = Field(..., description="EMR identifier for the patient (required).", example="EMR12345", alias="emr_id")
    locationId: Optional[str] = Field(None, description="Unique identifier for the clinic location (required for new patients).", example="AXjwbE", alias="location_id")
    locationName: Optional[str] = Field(None, description="Display name of the clinic location.", example="Demo Clinic", alias="location_name")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.", example="John")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.", example="Doe")
    dob: Optional[str] = Field(None, description="Date of birth in ISO 8601 format.", example="1990-01-15")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.", example="+1234567890")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.", example="M")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.", example="Annual checkup")
    status: Optional[str] = Field(None, description="Current queue status for the patient.", example="confirmed")
    capturedAt: Optional[str] = Field(None, description="Timestamp indicating when the record was captured in ISO 8601 format.", example="2025-11-21T10:30:00Z", alias="captured_at")
    bookingId: Optional[str] = Field(None, description="Internal booking identifier.", example="booking-123", alias="booking_id")
    bookingNumber: Optional[str] = Field(None, description="Human-readable booking number.", example="BK-001", alias="booking_number")
    patientNumber: Optional[str] = Field(None, description="Clinic-specific patient number.", example="PN-456", alias="patient_number")
    
    class Config:
        populate_by_name = True
        extra = "allow"
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "locationId": "AXjwbE",
                "locationName": "Demo Clinic",
                "legalFirstName": "John",
                "legalLastName": "Doe",
                "dob": "1990-01-15",
                "mobilePhone": "+1234567890",
                "sexAtBirth": "M",
                "status": "confirmed",
                "reasonForVisit": "Annual checkup",
                "capturedAt": "2025-11-21T10:30:00Z"
            }
        }


class PatientBatchRequest(BaseModel):
    """Request model for creating multiple patient records."""
    patients: List[PatientCreateRequest] = Field(..., description="List of patient records to create.")


class StatusUpdateRequest(BaseModel):
    """Request model for updating patient status."""
    status: str = Field(..., description="New queue status for the patient. Common values: confirmed, checked_in, pending, completed, cancelled.", example="checked_in")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "checked_in"
            }
        }


# Encounter data submission models
class EncounterCreateRequest(BaseModel):
    """Request model for creating an encounter record."""
    emrId: str = Field(
        ..., 
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    encounterPayload: Dict[str, Any] = Field(
        ..., 
        description="Full encounter JSON payload. Must contain 'id' or 'encounterId' field to identify the encounter.",
        example={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
            "attributes": {"gender": "male", "ageYears": 69},
            "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
            "status": "COMPLETE"
        },
        alias="encounter_payload"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "encounterPayload": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                    "attributes": {"gender": "male", "ageYears": 69},
                    "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
                    "status": "COMPLETE"
                }
            }
        }


class EncounterResponse(BaseModel):
    """Response model for encounter records."""
    emrId: str = Field(
        ..., 
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    encounterPayload: Dict[str, Any] = Field(
        ..., 
        description="Full encounter JSON payload as stored",
        alias="encounter_payload"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "encounterPayload": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                    "attributes": {"gender": "male", "ageYears": 69},
                    "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
                    "status": "COMPLETE"
                }
            }
        }


# Queue data submission models
class QueueUpdateRequest(BaseModel):
    """Request model for updating queue experityAction."""
    queue_id: Optional[str] = Field(None, description="Queue identifier (UUID). Either queue_id or encounter_id is required.", example="660e8400-e29b-41d4-a716-446655440000")
    encounter_id: Optional[str] = Field(None, description="Encounter identifier (UUID). Either queue_id or encounter_id is required.", example="550e8400-e29b-41d4-a716-446655440000")
    experityAction: Optional[List[Dict[str, Any]]] = Field(None, description="Experity action objects array to update in parsed_payload.")
    
    @model_validator(mode='after')
    def validate_at_least_one_identifier(self):
        """Ensure at least one identifier is provided."""
        if not self.queue_id and not self.encounter_id:
            raise ValueError('Either queue_id or encounter_id must be provided.')
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
                "experityAction": [
                    {
                        "action": "UPDATE_VITALS",
                        "data": {
                            "temperature": 98.6,
                            "bloodPressure": "120/80"
                        }
                    }
                ]
            }
        }


class QueueResponse(BaseModel):
    """Response model for queue records."""
    queue_id: str = Field(..., description="Unique identifier for the queue entry (UUID).")
    encounter_id: str = Field(..., description="Encounter identifier (UUID).")
    emr_id: Optional[str] = Field(None, description="EMR identifier for the patient.")
    status: str = Field(..., description="Queue status: PENDING, PROCESSING, DONE, or ERROR.")
    raw_payload: Optional[Dict[str, Any]] = Field(None, description="Raw JSON payload from encounter.")
    parsed_payload: Optional[Dict[str, Any]] = Field(None, description="Parsed payload with trauma_type, chief_complaints, and experityAction (array of action objects).")
    created_at: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was created.")
    updated_at: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was last updated.")
    attempts: int = Field(default=0, description="Number of processing attempts.")
    
    class Config:
        extra = "allow"


# Experity mapping endpoint models
class ExperityMapRequest(BaseModel):
    """Request model for mapping queue entry to Experity actions via Azure AI."""
    queue_entry: Dict[str, Any] = Field(
        ...,
        description="Queue entry containing queue_id, encounter_id, raw_payload, and parsed_payload."
    )
    
    @field_validator("queue_entry")
    @classmethod
    def validate_queue_entry(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate queue entry has required fields."""
        if not isinstance(v, dict):
            raise ValueError("queue_entry must be a dictionary")
        
        if not v.get("encounter_id"):
            raise ValueError("queue_entry must contain 'encounter_id' field")
        
        if not v.get("raw_payload"):
            raise ValueError("queue_entry must contain 'raw_payload' field")
        
        return v


class ExperityAction(BaseModel):
    """Model for a single Experity action."""
    template: str = Field(..., description="Template name.")
    bodyAreaKey: str = Field(..., description="Body area key.")
    coordKey: Optional[str] = Field(None, description="Coordinate key.")
    bodyMapSide: Optional[str] = Field(None, description="Body map side (front/back).")
    ui: Optional[Dict[str, Any]] = Field(None, description="UI data including bodyMapClick coordinates.")
    mainProblem: str = Field(..., description="Main problem description.")
    notesTemplateKey: Optional[str] = Field(None, description="Notes template key.")
    notesPayload: Optional[Dict[str, Any]] = Field(None, description="Notes payload data.")
    reasoning: Optional[str] = Field(None, description="Reasoning for the mapping.")
    
    class Config:
        extra = "allow"


class ExperityMapResponse(BaseModel):
    """Response model for Experity mapping endpoint."""
    success: bool = Field(..., description="Whether the mapping was successful.")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data containing experity_actions.")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if success is false.")
    
    class Config:
        extra = "allow"


# Summary data submission models
class SummaryRequest(BaseModel):
    """Request model for creating or updating a summary record."""
    emrId: str = Field(
        ..., 
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    note: str = Field(
        ..., 
        description="Summary note text containing clinical information",
        example="Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days."
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days."
            }
        }


class SummaryResponse(BaseModel):
    """Response model for summary records."""
    id: int = Field(..., description="Unique identifier for the summary record", example=123)
    emrId: str = Field(..., description="EMR identifier for the patient", example="EMR12345", alias="emr_id")
    note: str = Field(..., description="Summary note text", example="Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.")
    createdAt: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was created", example="2025-11-21T10:30:00Z", alias="created_at")
    updatedAt: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was last updated", example="2025-11-21T10:30:00Z", alias="updated_at")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "emrId": "EMR12345",
                "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                "createdAt": "2025-11-21T10:30:00Z",
                "updatedAt": "2025-11-21T10:30:00Z"
            }
        }
        extra = "allow"


# Token generation endpoint removed - HMAC authentication only
# Clients authenticate each request using HMAC signatures


@app.get(
    "/",
    summary="Render the patient dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- HTML dashboard rendered via Jinja template -->"}},
            "description": "HTML table view of the patient queue filtered by the supplied query parameters.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
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
    search: Optional[str] = Query(
        default=None,
        alias="search",
        description="Search patients by name, EMR ID, or phone number."
    ),
    page: Optional[int] = Query(
        default=1,
        ge=1,
        alias="page",
        description="Page number for pagination (starts at 1)."
    ),
    page_size: Optional[int] = Query(
        default=25,
        ge=1,
        le=100,
        alias="page_size",
        description="Number of records per page (1-100)."
    ),
    current_user: dict = Depends(require_auth),
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

    # Normalize search query
    search_query = search.strip() if search and isinstance(search, str) and search.strip() else None

    try:
        use_remote_reads = use_remote_api_for_reads()
        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            all_patients = await fetch_remote_patients(normalized_location_id, normalized_statuses, None)
            
            # Apply search filter if provided
            if search_query:
                all_patients = filter_patients_by_search(all_patients, search_query)

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
                all_patients = get_local_patients(cursor, normalized_location_id, normalized_statuses, None)
                
                # Apply search filter if provided
                if search_query:
                    all_patients = filter_patients_by_search(all_patients, search_query)
                
                locations = fetch_locations(cursor)
            finally:
                cursor.close()
                conn.close()

        # Calculate pagination
        total_count = len(all_patients)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        current_page = min(page, total_pages) if total_pages > 0 else 1
        
        # Apply pagination
        start_idx = (current_page - 1) * page_size
        end_idx = start_idx + page_size
        patients = all_patients[start_idx:end_idx]

        status_summary: Dict[str, int] = {}
        for patient in patients:
            status = patient.get("status_class") or "unknown"
            status_summary[status] = status_summary.get(status, 0) + 1

        # Create response with no-cache headers to prevent back button showing cached page
        response = templates.TemplateResponse(
            "patients_table.html",
            {
                "request": request,
                "patients": patients,
                "location_id": normalized_location_id,
                "selected_statuses": normalized_statuses,
                "search": search_query or "",
                "page": current_page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "locations": locations,
                "default_statuses": DEFAULT_STATUSES,
                "status_summary": status_summary,
                "current_user": current_user,
            },
        )
        
        # Add cache-control headers to prevent browser caching after logout
        # Use no-cache instead of no-store to allow history navigation while preventing stale cache
        response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get(
    "/experity/chat",
    summary="Experity Mapper Chat UI",
    response_class=HTMLResponse,
    include_in_schema=False,
    responses={
        200: {
            "content": {"text/html": {"example": "<!-- Experity Mapper Chat UI -->"}},
            "description": "Interactive chat UI for mapping queue entries to Experity actions.",
        },
        303: {"description": "Redirect to login page if not authenticated."},
    },
)
async def experity_chat_ui(
    request: Request,
    current_user: dict = Depends(require_auth),
):
    """
    Render the Experity Mapper Chat UI.
    
    This page provides an interactive interface to:
    - Upload JSON queue entries
    - Send requests to the /experity/map endpoint
    - View responses with Experity actions
    
    Requires authentication - users must be logged in to access this page.
    """
    response = templates.TemplateResponse(
        "experity_chat.html",
        {
            "request": request,
            "current_user": current_user,
        },
    )
    # Use no-cache instead of no-store to allow history navigation while preventing stale cache
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get(
    "/patient/{emrId}",
    tags=["Patients"],
    response_model=PatientPayload,
    responses={
        200: {
            "description": "Patient record",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "locationId": "AXjwbE",
                        "locationName": "Demo Clinic",
                        "legalFirstName": "John",
                        "legalLastName": "Doe",
                        "dob": "1990-01-15",
                        "mobilePhone": "+1234567890",
                        "sexAtBirth": "M",
                        "capturedAt": "2025-11-21T10:30:00Z",
                        "reasonForVisit": "Annual checkup",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z",
                        "status": "confirmed"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Patient not found"},
        500: {"description": "Server error"},
    },
)
async def get_patient_by_emr_id(
    emrId: str = Path(..., description="EMR identifier for the patient"),
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    **Example:**
    ```
    GET /patient/EMR12345
    ```
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
        
        cursor.execute(query, (emrId,))
        record = cursor.fetchone()
        
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emrId}' not found"
            )
        
        ensure_client_location_access(record.get("location_id"), current_client)
        
        response_payload = build_patient_payload(record)

        # Remove these fields completely from the response (always exclude)
        fields_to_always_exclude = [
            "booking_id", "booking_number", "patient_number",
            "appointment_date", "appointment_date_at_clinic_tz", "calendar_date",
            "status_class", "status_label", "captured_display", "source"
        ]
        # Remove excluded fields regardless of their values
        filtered_payload = {
            k: v for k, v in response_payload.items()
            if k not in fields_to_always_exclude
        }

        # Create model and exclude both None and unset values from serialization
        # Use by_alias=True to output camelCase field names
        patient = PatientPayload(**filtered_payload)
        return patient.model_dump(exclude_none=True, exclude_unset=True, by_alias=True)
        
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
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Patient record",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Patient record created successfully",
                        "emrId": "EMR12345",
                        "status": "created",
                        "insertedCount": 1
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_patient(
    patient_data: PatientCreateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    """
    if not normalize_patient_record or not insert_patients:
        raise HTTPException(
            status_code=503,
            detail="Patient save functionality unavailable"
        )
    
    conn = None
    try:
        # Convert Pydantic model to dict (use by_alias=False to get internal field names for normalization)
        patient_dict = patient_data.model_dump(exclude_none=True, by_alias=False)
        
        # Normalize the patient record (normalize_patient_record accepts both camelCase and snake_case)
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

        normalized_location_id = ensure_client_location_access(normalized.get("location_id"), current_client)
        normalized["location_id"] = normalized_location_id

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
                    "emrId": normalized['emr_id'],
                    "status": "updated"
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create patient record"
                )
        
        return {
            "message": "Patient record created successfully",
            "emrId": normalized['emr_id'],
            "status": "created",
            "insertedCount": inserted_count
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
    "/patients/{emrId}",
    tags=["Patients"],
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Status update result",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Patient status updated successfully",
                        "emrId": "EMR12345",
                        "oldStatus": "confirmed",
                        "newStatus": "checked_in",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        404: {"description": "Patient not found"},
        500: {"description": "Server error"},
    },
)
async def update_patient_status(
    emrId: str = Path(..., description="EMR identifier for the patient"),
    status_data: StatusUpdateRequest = ...,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    """
    if not emrId or not emrId.strip():
        raise HTTPException(
            status_code=400,
            detail="emrId is required in the URL path"
        )
    
    emr_id_clean = emrId.strip()
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
            "SELECT id, emr_id, status, location_id FROM patients WHERE emr_id = %s LIMIT 1",
            (emr_id_clean,)
        )
        existing = cursor.fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emr_id_clean}' not found"
            )
        
        ensure_client_location_access(existing.get("location_id"), current_client)
        
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
            "emrId": emr_id_clean,
            "oldStatus": existing.get("status"),
            "newStatus": normalized_status,
            "updatedAt": updated.get("updated_at").isoformat() if updated.get("updated_at") else None
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
        201: {
            "description": "Encounter record created or updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "encounterPayload": {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                            "attributes": {
                                "gender": "male",
                                "ageYears": 69
                            },
                            "chiefComplaints": [
                                {
                                    "id": "00f9612e-f37d-451b-9172-25cbddee58a9",
                                    "description": "cough",
                                    "type": "search"
                                }
                            ],
                            "status": "COMPLETE"
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request data or missing required fields"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_encounter(
    request: Request,
    current_client: TokenData = get_auth_dependency()
) -> EncounterResponse:
    """
    **Request Body:**
    - `emrId` (required): EMR identifier for the patient
    - `encounterPayload` (required): Full encounter JSON object. Must contain `id` or `encounterId` field.
    
    **Example:**
    ```json
    POST /encounter
    {
      "emrId": "EMR12345",
      "encounterPayload": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "attributes": {
          "gender": "male",
          "ageYears": 69
        },
        "chiefComplaints": [
          {
            "id": "00f9612e-f37d-451b-9172-25cbddee58a9",
            "description": "cough",
            "type": "search"
          }
        ],
        "status": "COMPLETE"
      }
    }
    ```
    
    **Response:**
    Returns the stored encounter with `emrId` and `encounterPayload`.
    If an encounter with the same `encounterId` (from `encounterPayload.id` or `encounterPayload.encounterId`) exists, it will be updated.
    """
    conn = None
    
    try:
        # Capture raw JSON body
        request_body = await request.json()
        
        # Extract emrId (support both camelCase and snake_case)
        emr_id = request_body.get('emrId') or request_body.get('emr_id')
        if not emr_id:
            raise HTTPException(
                status_code=400,
                detail="emrId is required. Please provide an EMR identifier for the patient."
            )
        
        # Extract encounterPayload (support both camelCase and snake_case)
        encounter_payload = request_body.get('encounterPayload') or request_body.get('encounter_payload')
        if not encounter_payload:
            raise HTTPException(
                status_code=400,
                detail="encounterPayload is required. Please provide the full encounter JSON payload."
            )
        
        # Validate encounterPayload is a dictionary
        if not isinstance(encounter_payload, dict):
            raise HTTPException(
                status_code=400,
                detail="encounterPayload must be a JSON object."
            )
        
        # Extract encounter_id from within encounterPayload
        # Try both 'id' and 'encounterId' fields (support both camelCase and snake_case)
        encounter_id = (
            encounter_payload.get('id') or 
            encounter_payload.get('encounterId') or 
            encounter_payload.get('encounter_id')
        )
        
        if not encounter_id:
            raise HTTPException(
                status_code=400,
                detail="encounterPayload must contain either an 'id' or 'encounterId' field to identify the encounter."
            )
        
        # Build encounter_dict with only the 3 required fields
        encounter_dict = {
            'encounter_id': str(encounter_id),
            'emr_id': str(emr_id),
            'encounter_payload': encounter_payload,  # Store full encounter JSON
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the encounter
        saved_encounter = save_encounter(conn, encounter_dict)
        
        # Automatically create queue entry from encounter
        try:
            create_queue_from_encounter(conn, saved_encounter)
        except Exception as e:
            # Log error but don't fail the encounter creation
            print(f"Warning: Failed to create queue entry for encounter {encounter_id}: {str(e)}")
        
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


@app.post(
    "/queue",
    tags=["Queue"],
    summary="Update queue experityAction",
    response_model=QueueResponse,
    responses={
        200: {
            "description": "Queue entry updated successfully. The `experityAction` field in `parsed_payload` has been updated.",
            "content": {
                "application/json": {
                    "example": {
                        "queue_id": "660e8400-e29b-41d4-a716-446655440000",
                        "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
                        "emr_id": "EMR12345",
                        "status": "PENDING",
                        "parsed_payload": {
                            "experityAction": [
                                {
                                    "action": "UPDATE_VITALS",
                                    "data": {
                                        "temperature": 98.6,
                                        "bloodPressure": "120/80"
                                    }
                                }
                            ]
                        },
                        "updated_at": "2025-11-21T10:35:00Z"
                    }
                }
            }
        },
        400: {
            "description": "Invalid request data or missing required fields. Either `queue_id` or `encounter_id` must be provided."
        },
        401: {"description": "Authentication required. Provide HMAC signature via X-Timestamp and X-Signature headers."},
        404: {"description": "Queue entry not found. Provide a valid `queue_id` or `encounter_id`."},
        500: {"description": "Database or server error while updating the queue."},
    },
)
async def update_queue_experity_action(
    request_data: QueueUpdateRequest,
    current_client: TokenData = get_auth_dependency()
) -> QueueResponse:
    """
    Update the `experityAction` field in a queue entry's `parsed_payload`.
    
    This endpoint allows updating the `experityAction` array within the `parsed_payload` 
    of a queue entry. The queue entry can be identified by either `queue_id` or `encounter_id`.
    
    **Request Body:**
    - **queue_id** (optional): Queue identifier (UUID). Either `queue_id` or `encounter_id` must be provided.
    - **encounter_id** (optional): Encounter identifier (UUID). Either `queue_id` or `encounter_id` must be provided.
    - **experityAction** (optional): Array of Experity action objects to set in `parsed_payload`. 
      If a single object is provided, it will be automatically converted to an array.
    
    **Behavior:**
    - Updates the `experityAction` field in the queue entry's `parsed_payload`
    - If `experityAction` is not provided, the field remains unchanged
    - If `experityAction` is `null` or an empty array, it will be set to an empty array
    - Single objects are automatically converted to arrays for backward compatibility
    
    **Example Request:**
    ```json
    {
      "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
      "experityAction": [
        {
          "action": "UPDATE_VITALS",
          "data": {
            "temperature": 98.6,
            "bloodPressure": "120/80"
          }
        }
      ]
    }
    ```
    
    Requires HMAC signature authentication via X-Timestamp and X-Signature headers.
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Find queue entry by queue_id or encounter_id
        queue_entry = None
        if request_data.queue_id:
            cursor.execute(
                "SELECT * FROM queue WHERE queue_id = %s",
                (request_data.queue_id,)
            )
            queue_entry = cursor.fetchone()
        elif request_data.encounter_id:
            cursor.execute(
                "SELECT * FROM queue WHERE encounter_id = %s",
                (request_data.encounter_id,)
            )
            queue_entry = cursor.fetchone()
        
        if not queue_entry:
            raise HTTPException(
                status_code=404,
                detail="Queue entry not found. Provide a valid queue_id or encounter_id."
            )
        
        # Get current parsed_payload
        import json
        from psycopg2.extras import Json
        
        parsed_payload = queue_entry.get('parsed_payload')
        if isinstance(parsed_payload, str):
            try:
                parsed_payload = json.loads(parsed_payload)
            except json.JSONDecodeError:
                parsed_payload = {}
        elif parsed_payload is None:
            parsed_payload = {}
        
        # Ensure experityAction exists and is an array (handle legacy data)
        if 'experityAction' not in parsed_payload:
            parsed_payload['experityAction'] = []
        elif parsed_payload.get('experityAction') is None:
            parsed_payload['experityAction'] = []
        elif isinstance(parsed_payload.get('experityAction'), dict):
            # Convert legacy single object to array
            parsed_payload['experityAction'] = [parsed_payload['experityAction']]
        elif not isinstance(parsed_payload.get('experityAction'), list):
            # If it's not a list, initialize as empty array
            parsed_payload['experityAction'] = []
        
        # Update experityAction if provided
        if request_data.experityAction is not None:
            # Ensure experityAction is an array
            if isinstance(request_data.experityAction, list):
                parsed_payload['experityAction'] = request_data.experityAction
            elif isinstance(request_data.experityAction, dict):
                # Handle legacy single object - convert to array
                parsed_payload['experityAction'] = [request_data.experityAction]
            else:
                # If it's not a list or dict, initialize as empty array
                parsed_payload['experityAction'] = []
        
        # Update the queue entry
        cursor.execute(
            """
            UPDATE queue
            SET parsed_payload = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE queue_id = %s
            RETURNING *
            """,
            (Json(parsed_payload), queue_entry['queue_id'])
        )
        
        updated_entry = cursor.fetchone()
        conn.commit()
        
        # Format the response
        formatted_response = format_queue_response(updated_entry)
        
        return QueueResponse(**formatted_response)
        
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


@app.get(
    "/queue",
    tags=["Queue"],
    summary="List queue entries with optional filters",
    response_model=List[QueueResponse],
    responses={
        200: {
            "description": "List of queue entries matching the filters. Results are ordered by `created_at` descending (newest first).",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "queue_id": "660e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
                            "emr_id": "EMR12345",
                            "status": "PENDING",
                            "parsed_payload": {
                                "experityAction": []
                            },
                            "attempts": 0,
                            "created_at": "2025-11-21T10:30:00Z",
                            "updated_at": "2025-11-21T10:30:00Z"
                        }
                    ]
                }
            }
        },
        400: {"description": "Invalid query parameters."},
        401: {"description": "Authentication required. Provide HMAC signature via X-Timestamp and X-Signature headers."},
        500: {"description": "Database or server error while fetching queue entries."},
    },
)
async def list_queue(
    queue_id: Optional[str] = Query(
        default=None,
        alias="queue_id",
        description="Filter by queue identifier (UUID). Example: `660e8400-e29b-41d4-a716-446655440000`"
    ),
    encounter_id: Optional[str] = Query(
        default=None,
        alias="encounter_id",
        description="Filter by encounter identifier (UUID). Example: `550e8400-e29b-41d4-a716-446655440000`"
    ),
    status: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status. Valid values: `PENDING`, `PROCESSING`, `DONE`, `ERROR`. Example: `PENDING`"
    ),
    emr_id: Optional[str] = Query(
        default=None,
        alias="emr_id",
        description="Filter by EMR identifier. Example: `EMR12345`"
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return. Must be >= 1. Example: `50`"
    ),
    current_client: TokenData = get_auth_dependency()
) -> List[QueueResponse]:
    """
    Retrieve queue entries with optional filters.
    
    This endpoint allows querying queue entries by various filters. Queue entries track 
    the processing status of encounters and contain both raw and parsed payloads.
    
    **Query Parameters (all optional):**
    - **queue_id**: Get specific queue entry by UUID
    - **encounter_id**: Get queue entry by encounter UUID
    - **status**: Filter by status. Valid values: `PENDING`, `PROCESSING`, `DONE`, `ERROR`
    - **emr_id**: Filter by EMR identifier
    - **limit**: Limit the number of results (must be >= 1)
    
    **Response:**
    Returns an array of queue entry objects. Each entry includes:
    - `queue_id`: Unique queue identifier
    - `encounter_id`: Associated encounter identifier
    - `emr_id`: Patient EMR identifier
    - `status`: Processing status
    - `raw_payload`: Original encounter JSON
    - `parsed_payload`: Parsed structure with `experityAction` array
    - `attempts`: Number of processing attempts
    - Timestamps: `created_at`, `updated_at`
    
    **Example Request:**
    ```
    GET /queue?status=PENDING&limit=10
    GET /queue?encounter_id=550e8400-e29b-41d4-a716-446655440000
    ```
    
    Results are ordered by `created_at` descending (newest first).
    
    Requires HMAC signature authentication via X-Timestamp and X-Signature headers.
    """
    conn = None
    cursor = None
    
    try:
        # Validate status if provided
        if status and status not in ['PENDING', 'PROCESSING', 'DONE', 'ERROR']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: PENDING, PROCESSING, DONE, ERROR"
            )
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query with filters
        query = "SELECT * FROM queue WHERE 1=1"
        params: List[Any] = []
        
        if queue_id:
            query += " AND queue_id = %s"
            params.append(queue_id)
        
        if encounter_id:
            query += " AND encounter_id = %s"
            params.append(encounter_id)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        if emr_id:
            query += " AND emr_id = %s"
            params.append(emr_id)
        
        # Order by created_at descending
        query += " ORDER BY created_at DESC"
        
        # Apply limit if provided
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Format the results
        formatted_results = [format_queue_response(record) for record in results]
        
        return [QueueResponse(**result) for result in formatted_results]
        
    except HTTPException:
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
    response_model=List[PatientPayload],
    responses={
        200: {
            "description": "List of patient records",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "emrId": "EMR12345",
                            "locationId": "AXjwbE",
                            "locationName": "Demo Clinic",
                            "legalFirstName": "John",
                            "legalLastName": "Doe",
                            "dob": "1990-01-15",
                            "mobilePhone": "+1234567890",
                            "sexAtBirth": "M",
                            "capturedAt": "2025-11-21T10:30:00Z",
                            "reasonForVisit": "Annual checkup",
                            "createdAt": "2025-11-21T10:30:00Z",
                            "updatedAt": "2025-11-21T10:30:00Z",
                            "status": "confirmed"
                        }
                    ]
                }
            }
        },
        400: {"description": "Invalid query parameters"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def list_patients(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description="Location identifier. Required unless DEFAULT_LOCATION_ID is set.",
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return"
    ),
    statuses: Optional[List[str]] = Query(
        default=None,
        alias="statuses",
        description="Filter by status. Defaults to checked_in, confirmed if not provided."
    ),
    current_client: TokenData = get_auth_dependency()
):
    """
    **Query Parameters:**
    - `locationId` (optional) - Required unless DEFAULT_LOCATION_ID is set
    - `statuses` (optional) - Defaults to checked_in, confirmed
    - `limit` (optional)
    
    **Example:**
    ```
    GET /patients?locationId=AXjwbE&statuses=confirmed&limit=50
    ```
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
        normalized_location_id = ensure_client_location_access(normalized_location_id, current_client)
        use_remote_reads = use_remote_api_for_reads()

        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            patients_raw = await fetch_remote_patients(normalized_location_id, normalized_statuses, limit)
            # Remove excluded fields
            fields_to_exclude = ["status_class", "status_label", "captured_display", "source"]
            filtered_patients = [
                {k: v for k, v in patient.items() if k not in fields_to_exclude}
                for patient in patients_raw
            ]
            # Use by_alias=True to output camelCase field names
            return [PatientPayload(**patient).model_dump(exclude_none=True, exclude_unset=True, by_alias=True) for patient in filtered_patients]

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            patients_raw = get_local_patients(cursor, normalized_location_id, normalized_statuses, limit)
            # Remove excluded fields
            fields_to_exclude = ["status_class", "status_label", "captured_display", "source"]
            filtered_patients = [
                {k: v for k, v in patient.items() if k not in fields_to_exclude}
                for patient in patients_raw
            ]
            # Use by_alias=True to output camelCase field names
            return [PatientPayload(**patient).model_dump(exclude_none=True, exclude_unset=True, by_alias=True) for patient in filtered_patients]
        finally:
            cursor.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post(
    "/summary",
    tags=["Summaries"],
    summary="Create summary record",
    response_model=SummaryResponse,
    status_code=201,
    responses={
        201: {
            "description": "Summary record created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
                        "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data or missing required fields"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_summary(
    summary_data: SummaryRequest,
    current_client: TokenData = get_auth_dependency()
) -> SummaryResponse:
    """
    **Request Body:**
    - `emrId` (required): EMR identifier for the patient
    - `note` (required): Summary note text containing clinical information
    
    **Example:**
    ```json
    POST /summary
    {
      "emrId": "EMR12345",
      "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days."
    }
    ```
    
    **Response:**
    Returns the created summary record with auto-generated `id` and timestamps.
    """
    conn = None
    
    try:
        # Validate required fields
        if not summary_data.emrId:
            raise HTTPException(
                status_code=400,
                detail="emrId is required. Please provide an EMR identifier."
            )
        
        if not summary_data.note:
            raise HTTPException(
                status_code=400,
                detail="note is required. Please provide summary note text."
            )
        
        # Prepare summary data
        summary_dict = {
            'emr_id': summary_data.emrId,
            'note': summary_data.note,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the summary
        saved_summary = save_summary(conn, summary_dict)
        
        # Format the response
        formatted_response = format_summary_response(saved_summary)
        
        # Use by_alias=True to output camelCase field names
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=True)
        
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


@app.get(
    "/summary",
    tags=["Summaries"],
    summary="Get summary by EMR ID",
    response_model=SummaryResponse,
    responses={
        200: {
            "description": "Summary record",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
                        "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Summary not found"},
        500: {"description": "Server error"},
    },
)
async def get_summary(
    emrId: str = Query(..., alias="emrId", description="EMR identifier for the patient"),
    current_client: TokenData = get_auth_dependency()
) -> SummaryResponse:
    """
    Get the most recent summary record for a patient.
    
    **Example:**
    ```
    GET /summary?emrId=EMR12345
    ```
    
    Returns the summary with the latest `updatedAt` timestamp. If multiple summaries exist, only the most recent one is returned.
    """
    conn = None
    
    try:
        if not emrId:
            raise HTTPException(
                status_code=400,
                detail="emrId query parameter is required."
            )
        
        # Get database connection
        conn = get_db_connection()
        
        # Retrieve the summary
        summary = get_summary_by_emr_id(conn, emrId)
        
        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"Summary not found for EMR ID: {emrId}"
            )
        
        # Format the response
        formatted_response = format_summary_response(summary)
        
        # Use by_alias=True to output camelCase field names
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=True)
        
    except HTTPException:
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
        if conn:
            conn.close()


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
    import json
    from psycopg2.extras import Json
    
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


@app.post(
    "/experity/map",
    tags=["Queue"],
    summary="Map queue entry to Experity actions via Azure AI",
    response_model=ExperityMapResponse,
    responses={
        200: {
            "description": "Successfully mapped queue entry to Experity actions. The queue entry status is updated to PROCESSING during the request and DONE or ERROR based on the result.",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "experity_actions": {
                                "emrId": "EMR12345",
                                "vitals": {
                                    "temperature": 98.6,
                                    "bloodPressure": "120/80"
                                },
                                "guardianAssistedInterview": None,
                                "labOrders": [],
                                "icdUpdates": [],
                                "complaints": [
                                    {
                                        "mainProblem": "Fever and cough",
                                        "bodyParts": ["chest", "throat"]
                                    }
                                ]
                            },
                            "queue_id": "660e8400-e29b-41d4-a716-446655440000",
                            "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
                            "processed_at": "2025-11-21T10:30:00Z"
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid request data or missing required fields. `queue_entry` must contain `encounter_id` and `raw_payload`."
        },
        401: {"description": "Authentication required. Provide HMAC signature via X-Timestamp and X-Signature headers."},
        404: {"description": "Queue entry not found in database."},
        502: {"description": "Azure AI agent returned an error. The queue entry status is updated to ERROR."},
        504: {"description": "Request to Azure AI agent timed out. The queue entry status is updated to ERROR."},
        500: {"description": "Database or server error. Azure AI client may not be available."},
    },
)
async def map_queue_to_experity(
    request: Request,
    current_client: TokenData = get_auth_dependency()
) -> ExperityMapResponse:
    """
    Map a queue entry to Experity actions using Azure AI Experity Mapper Agent.
    
    This endpoint processes a queue entry through Azure AI to generate Experity mapping actions.
    The queue entry status is automatically updated during processing:
    - Set to `PROCESSING` when the request starts
    - Set to `DONE` on successful mapping
    - Set to `ERROR` on failure (with error message stored)
    
    **Request Body:**
    - **queue_entry** (required): Dictionary containing:
      - **encounter_id** (required): Encounter identifier (UUID)
      - **raw_payload** (required): Dictionary with encounter data
      - **queue_id** (optional): Queue identifier (UUID, used for database updates)
      - **parsed_payload** (optional): Parsed payload dictionary
    
    **Response:**
    - **success** (boolean): Whether the mapping was successful
    - **data** (object, if success is true): Contains:
      - **experity_actions**: Full Experity mapping object (JSON) with:
        - `emrId`: EMR identifier
        - `vitals`: Vitals object
        - `guardianAssistedInterview`: Guardian info object
        - `labOrders`: Array of lab orders
        - `icdUpdates`: Array of ICD-10 updates
        - `complaints`: Array of complaint objects
      - **queue_id**: Queue identifier (if available)
      - **encounter_id**: Encounter identifier
      - **processed_at**: ISO 8601 timestamp
    - **error** (object, if success is false): Error details with code and message
    
    **Behavior:**
    - If `queue_id` is not provided, the endpoint attempts to find it by `encounter_id`
    - Queue entry status is automatically managed during processing
    - On error, the queue entry status is set to `ERROR` and attempts counter is incremented
    
    **Example Request:**
    ```json
    {
      "queue_entry": {
        "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
        "raw_payload": {
          "encounterId": "550e8400-e29b-41d4-a716-446655440000",
          "emrId": "EMR12345",
          "chiefComplaints": [
            {
              "mainProblem": "Fever and cough",
              "bodyParts": ["chest", "throat"]
            }
          ]
        }
      }
    }
    ```
    
    Requires HMAC signature authentication via X-Timestamp and X-Signature headers.
    """
    import logging
    import json
    logger = logging.getLogger(__name__)
    
    if not AZURE_AI_AVAILABLE or not call_azure_ai_agent:
        raise HTTPException(
            status_code=500,
            detail="Azure AI client is not available. Check server configuration."
        )
    
    # Parse request body after HMAC verification (body already consumed and cached by dependency)
    try:
        # Use cached body from HMAC verification if available, otherwise read it
        if hasattr(request, "_body") and request._body:
            body_bytes = request._body
            body_json = json.loads(body_bytes.decode('utf-8'))
        else:
            body_json = await request.json()
        request_data = ExperityMapRequest(**body_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON in request body: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request format: {str(e)}"
        )
    
    conn = None
    queue_entry = request_data.queue_entry
    queue_id = queue_entry.get("queue_id")
    encounter_id = queue_entry.get("encounter_id")
    
    try:
        # Validate queue_entry structure (already validated by Pydantic, but double-check)
        if not encounter_id:
            return ExperityMapResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "queue_entry must contain 'encounter_id' field"
                }
            )
        
        if not queue_entry.get("raw_payload"):
            return ExperityMapResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "queue_entry must contain 'raw_payload' field"
                }
            )
        
        # Try to get queue_id from database if not provided
        if not queue_id:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cursor.execute(
                    "SELECT queue_id FROM queue WHERE encounter_id = %s",
                    (encounter_id,)
                )
                result = cursor.fetchone()
                if result:
                    queue_id = str(result.get('queue_id'))
            finally:
                cursor.close()
                if not queue_id:  # Only close conn if we're done with it
                    conn.close()
                    conn = None
        
        # Update queue status to PROCESSING if queue_id exists
        if queue_id and conn is None:
            conn = get_db_connection()
        
        if queue_id and conn:
            try:
                update_queue_status_and_experity_action(
                    conn=conn,
                    queue_id=queue_id,
                    status='PROCESSING',
                    increment_attempts=False
                )
            except Exception as e:
                logger.warning(f"Failed to update queue status to PROCESSING: {str(e)}")
                # Continue even if database update fails
        
        # Call Azure AI agent with retry logic at endpoint level
        # This provides additional retries for transient errors beyond the client-level retries
        endpoint_max_retries = 3
        endpoint_retry_delay = 2  # seconds
        
        experity_mapping = None
        last_endpoint_error = None
        
        # Performance timing
        import time
        endpoint_start_time = time.perf_counter()
        
        for endpoint_attempt in range(endpoint_max_retries):
            try:
                logger.info(
                    f"Endpoint-level attempt {endpoint_attempt + 1}/{endpoint_max_retries} "
                    f"for encounter_id: {encounter_id}"
                )
                experity_mapping = await call_azure_ai_agent(queue_entry)
                # Success - break out of retry loop
                break
            except AzureAIAuthenticationError as e:
                # Authentication errors should not be retried
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_AUTH_ERROR",
                        "message": "Failed to authenticate with Azure AI",
                        "details": {"azure_message": str(e)}
                    }
                )
                # Update queue status to ERROR
                if queue_id and conn:
                    try:
                        update_queue_status_and_experity_action(
                            conn=conn,
                            queue_id=queue_id,
                            status='ERROR',
                            error_message=str(e),
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=502, detail=error_response.dict())
            
            except AzureAIRateLimitError as e:
                # Rate limit errors: retry with longer delays, respecting Retry-After header
                last_endpoint_error = e
                if endpoint_attempt < endpoint_max_retries - 1:
                    # Determine wait time: use Retry-After if available, otherwise use progressive delays
                    if hasattr(e, 'retry_after') and e.retry_after:
                        wait_time = e.retry_after
                        logger.info(f"Using Retry-After header value: {wait_time} seconds")
                    else:
                        # Progressive delays for rate limits: 60s, 120s, 180s
                        rate_limit_delays = [60, 120, 180]
                        wait_time = rate_limit_delays[min(endpoint_attempt, len(rate_limit_delays) - 1)]
                    
                    # Add jitter (±5 seconds) to avoid synchronized retries
                    jitter = random.uniform(-5, 5)
                    wait_time = max(30, wait_time + jitter)  # Minimum 30 seconds
                    
                    logger.warning(
                        f"Rate limit error on attempt {endpoint_attempt + 1}/{endpoint_max_retries}. "
                        f"Waiting {wait_time:.1f} seconds before retry to allow rate limit to reset..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                # Exhausted retries for rate limit
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_RATE_LIMIT",
                        "message": f"Azure AI rate limit exceeded after {endpoint_max_retries} attempts with extended waits",
                        "details": {
                            "azure_message": str(e),
                            "attempts": endpoint_max_retries,
                            "suggestion": "Please wait a few minutes before trying again, or check your Azure AI quota limits"
                        }
                    }
                )
                # Update queue status to ERROR
                if queue_id and conn:
                    try:
                        update_queue_status_and_experity_action(
                            conn=conn,
                            queue_id=queue_id,
                            status='ERROR',
                            error_message=str(e),
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=502, detail=error_response.dict())
            
            except AzureAITimeoutError as e:
                # Timeout errors can be retried
                last_endpoint_error = e
                if endpoint_attempt < endpoint_max_retries - 1:
                    wait_time = endpoint_retry_delay * (endpoint_attempt + 1)
                    logger.warning(
                        f"Timeout error on attempt {endpoint_attempt + 1}/{endpoint_max_retries}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                # Exhausted retries
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_TIMEOUT",
                        "message": f"Request to Azure AI agent timed out after {endpoint_max_retries} attempts",
                        "details": {"azure_message": str(e), "attempts": endpoint_max_retries}
                    }
                )
                # Update queue status to ERROR
                if queue_id and conn:
                    try:
                        update_queue_status_and_experity_action(
                            conn=conn,
                            queue_id=queue_id,
                            status='ERROR',
                            error_message=str(e),
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=504, detail=error_response.dict())
            
            except (AzureAIResponseError, AzureAIClientError) as e:
                # Response/Client errors can be retried (e.g., JSON parsing errors, incomplete responses)
                last_endpoint_error = e
                if endpoint_attempt < endpoint_max_retries - 1:
                    wait_time = endpoint_retry_delay * (endpoint_attempt + 1)
                    logger.warning(
                        f"Azure AI error on attempt {endpoint_attempt + 1}/{endpoint_max_retries}: {str(e)}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                # Exhausted retries
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_ERROR",
                        "message": f"Azure AI agent returned an error after {endpoint_max_retries} attempts",
                        "details": {"azure_message": str(e), "attempts": endpoint_max_retries}
                    }
                )
                # Update queue status to ERROR
                if queue_id and conn:
                    try:
                        update_queue_status_and_experity_action(
                            conn=conn,
                            queue_id=queue_id,
                            status='ERROR',
                            error_message=str(e),
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=502, detail=error_response.dict())
        
        # Log total endpoint processing time
        endpoint_total_time = time.perf_counter() - endpoint_start_time
        logger.info(f"⏱️  Total endpoint processing time: {endpoint_total_time:.3f}s")
        
        # Check if we got a successful response
        if experity_mapping is None:
            # This should not happen, but handle it gracefully
            error_response = ExperityMapResponse(
                success=False,
                error={
                    "code": "AZURE_AI_ERROR",
                    "message": f"Failed to get response from Azure AI after {endpoint_max_retries} attempts",
                    "details": {"last_error": str(last_endpoint_error) if last_endpoint_error else "Unknown error"}
                }
            )
            if queue_id and conn:
                try:
                    update_queue_status_and_experity_action(
                        conn=conn,
                        queue_id=queue_id,
                        status='ERROR',
                        error_message="No response from Azure AI after retries",
                        increment_attempts=True
                    )
                except Exception:
                    pass
            raise HTTPException(status_code=502, detail=error_response.dict())
        
        # Update queue status to DONE and store experity_actions (now a full JSON object)
        if queue_id and conn:
            try:
                update_queue_status_and_experity_action(
                    conn=conn,
                    queue_id=queue_id,
                    status='DONE',
                    experity_actions=experity_mapping,
                    increment_attempts=False
                )
            except Exception as e:
                logger.warning(f"Failed to update queue status to DONE: {str(e)}")
                # Continue even if database update fails
        
        # Build success response
        # experity_actions now contains the full LLM response object
        response_data = {
            "experity_actions": experity_mapping,
            "encounter_id": encounter_id,
            "processed_at": datetime.now().isoformat() + "Z"
        }
        
        if queue_id:
            response_data["queue_id"] = queue_id
        
        return ExperityMapResponse(
            success=True,
            data=response_data
        )
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error(f"Database error in map_queue_to_experity: {str(e)}")
        return ExperityMapResponse(
            success=False,
            error={
                "code": "DATABASE_ERROR",
                "message": "Database error occurred",
                "details": {"error": str(e)}
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error in map_queue_to_experity: {str(e)}")
        return ExperityMapResponse(
            success=False,
            error={
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": {"error": str(e)}
            }
        )
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

