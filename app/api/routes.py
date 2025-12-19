#!/usr/bin/env python3
"""
FastAPI application to expose patient data via REST API.
"""

import os
import sys
import asyncio
import random
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# Configure logging
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException, Query, Request, Depends, Body, UploadFile, File
    from fastapi import Path as PathParam
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
        AzureAIResponseError,
        REQUEST_TIMEOUT
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

# Import Azure Blob Storage for image uploads
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    print("Warning: azure-storage-blob not installed. Image upload endpoint will not work.")
    BlobServiceClient = None
    ContentSettings = None
    AZURE_BLOB_AVAILABLE = False

# Azure Blob Storage configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "images")

# Initialize Azure Blob client
blob_service_client = None
container_client = None
if AZURE_BLOB_AVAILABLE and AZURE_STORAGE_CONNECTION_STRING:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
        print(f"Azure Blob Storage initialized. Container: {AZURE_STORAGE_CONTAINER_NAME}")
    except Exception as e:
        print(f"Warning: Failed to initialize Azure Blob Storage: {e}")
        blob_service_client = None
        container_client = None

# Allowed image MIME types
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

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
    version="1.0.4",
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
        {
            "name": "VM",
            "description": "Manage VM health and heartbeat tracking. Monitor VM worker status and processing queue assignments."
        },
        {
            "name": "Images",
            "description": "Upload and manage images. Store images in Azure Blob Storage with secure access."
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

# Import from new modules
from app.api.models import (
    PatientPayload,
    PatientCreateRequest,
    PatientBatchRequest,
    StatusUpdateRequest,
    EncounterCreateRequest,
    EncounterResponse,
    QueueUpdateRequest,
    QueueStatusUpdateRequest,
    QueueRequeueRequest,
    QueueResponse,
    ExperityMapRequest,
    ExperityAction,
    ExperityMapResponse,
    SummaryRequest,
    SummaryResponse,
    VmHeartbeatRequest,
    VmHeartbeatResponse,
    ImageUploadResponse,
)
from app.api.utils import (
    normalize_status,
    parse_datetime,
    expand_status_shortcuts,
    ensure_client_location_access,
    resolve_location_id,
    use_remote_api_for_reads,
    fetch_locations,
    fetch_remote_patients,
    DEFAULT_STATUSES,
)
from app.api.database import (
    get_db_connection,
    fetch_pending_records,
    fetch_confirmed_records,
    save_encounter,
    save_queue,
    save_summary,
    save_vm_health,
    get_summary_by_emr_id,
    create_queue_from_encounter,
    update_queue_status_and_experity_action,
    format_patient_record,
)
from app.api.services import (
    build_patient_payload,
    decorate_patient_payload,
    format_encounter_response,
    format_queue_response,
    format_summary_response,
    prepare_dashboard_patients,
    fetch_pending_payloads,
    filter_patients_by_search,
    get_local_patients,
    filter_within_24h,
)

# ============================================================================
# ROUTE HANDLERS
# ============================================================================


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
        # First expand any shortcuts like 'active'
        expanded_statuses = expand_status_shortcuts(statuses)
        normalized_statuses = [
            normalize_status(status)
            for status in expanded_statuses
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


# Remove all the duplicate functions and models below - they've been moved to separate modules
# Keeping only the route handlers from here on

# Token generation endpoint removed - HMAC authentication only
# Clients authenticate each request using HMAC signatures


# Duplicate models and functions removed - now imported from:
# - app.api.models (all BaseModel classes)
# - app.api.utils (utility functions)
# - app.api.database (database functions)
# - app.api.services (service/business logic functions)


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
        # First expand any shortcuts like 'active'
        expanded_statuses = expand_status_shortcuts(statuses)
        normalized_statuses = [
            normalize_status(status)
            for status in expanded_statuses
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
    except Exception as e:
        logger.error(f"Error fetching patients: {str(e)}")
        raise

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
                        "bookingId": "0Pa1Z6",
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
    emrId: str,
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
            "booking_number", "patient_number",
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
                        "bookingId": "0Pa1Z6",
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
                    "bookingId": normalized.get('booking_id'),
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
            "bookingId": normalized.get('booking_id'),
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
    emrId: str,
    status_data: StatusUpdateRequest,
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
    - `encounterPayload` (required): Full encounter JSON object. Must contain `id` (the ID of the encounter) field.
    
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
    summary="Update queue entry",
    description="Update a queue entry's Experity actions. Returns the updated queue entry with emrId, status, attempts, and encounterPayload.",
    response_model=QueueResponse,
    responses={
        200: {
            "description": "Queue entry updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "status": "PENDING",
                        "attempts": 0,
                        "encounterPayload": {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                            "traumaType": "BURN",
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
        404: {"description": "Queue entry not found"},
        500: {"description": "Server error"},
    },
)
async def update_queue_experity_action(
    request_data: QueueUpdateRequest,
    current_client: TokenData = get_auth_dependency()
) -> QueueResponse:
    """
    Update a queue entry's Experity actions.
    
    **Request Body:**
    - `encounter_id` (optional): Encounter identifier (UUID). Either `encounter_id` or `queue_id` must be provided.
    - `queue_id` (optional): Queue identifier (UUID). Either `encounter_id` or `queue_id` must be provided.
    - `experityAction` (optional): Array of Experity action objects to store in parsed_payload.
    
    **Response:**
    Returns the updated queue entry with `emrId`, `status`, `attempts`, and `encounterPayload`.
    
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
        
        # Create model for validation, then return dict with camelCase keys
        # FastAPI's jsonable_encoder uses aliases for models, but preserves dict keys
        queue_response = QueueResponse(**formatted_response)
        response_dict = queue_response.model_dump(by_alias=False)
        
        # Return dict directly - FastAPI will serialize it as-is (camelCase)
        # Bypassing response_model serialization which would use aliases
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_dict)
        
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
    summary="List queue entries",
    response_model=List[QueueResponse],
    responses={
        200: {
            "description": "List of queue entries",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "emrId": "EMR12345",
                            "status": "PENDING",
                            "attempts": 0,
                            "encounterPayload": {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                                "traumaType": "BURN",
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
                    ]
                }
            }
        },
        400: {"description": "Invalid query parameters"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def list_queue(
    queue_id: Optional[str] = Query(
        default=None,
        alias="queue_id",
        description="Filter by queue identifier (UUID)"
    ),
    encounter_id: Optional[str] = Query(
        default=None,
        alias="encounter_id",
        description="Filter by encounter identifier (UUID)"
    ),
    status: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: PENDING, PROCESSING, DONE, ERROR"
    ),
    emr_id: Optional[str] = Query(
        default=None,
        alias="emr_id",
        description="Filter by EMR identifier"
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return"
    ),
    claim: bool = Query(
        default=False,
        alias="claim",
        description="If true, atomically claim a PENDING item using FOR UPDATE SKIP LOCKED (sets status to PROCESSING). Requires status=PENDING and limit=1."
    ),
    current_client: TokenData = get_auth_dependency()
) -> List[QueueResponse]:
    """
    **Query Parameters (all optional):**
    - `queue_id`: Filter by queue identifier (UUID)
    - `encounter_id`: Filter by encounter identifier (UUID)
    - `status`: Filter by status: `PENDING`, `PROCESSING`, `DONE`, `ERROR`
    - `emr_id`: Filter by EMR identifier
    - `limit`: Maximum number of records to return (must be >= 1)
    - `claim`: If `true`, atomically claim a PENDING item (sets status to PROCESSING). 
      Uses `FOR UPDATE SKIP LOCKED` for safe concurrent access. Requires `status=PENDING` and `limit=1`.
    
    **Example:**
    ```
    GET /queue?status=PENDING&limit=10
    GET /queue?encounter_id=550e8400-e29b-41d4-a716-446655440000
    GET /queue?status=PENDING&limit=1&claim=true  # Atomically claim next PENDING item
    ```
    
    **Response:**
    Returns an array of queue entries. Each entry contains `emrId`, `status`, `attempts`, and `encounterPayload`.
    Results are ordered by creation time (newest first), except when `claim=true` (FIFO ordering).
    
    **Claim Mode (claim=true):**
    - Uses `FOR UPDATE SKIP LOCKED` to prevent race conditions
    - Automatically updates claimed item's status to `PROCESSING`
    - Returns empty array if no PENDING items available (all locked or none exist)
    - Safe for multiple concurrent workers
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
        
        # Validate claim mode requirements
        if claim:
            if status != 'PENDING':
                raise HTTPException(
                    status_code=400,
                    detail="claim=true requires status=PENDING"
                )
            if limit != 1:
                raise HTTPException(
                    status_code=400,
                    detail="claim=true requires limit=1"
                )
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        if claim:
            # CLAIM MODE: Atomic claim with FOR UPDATE SKIP LOCKED
            # Uses FIFO ordering (ASC) for fair queue processing
            query = """
                SELECT * FROM queue 
                WHERE status = 'PENDING' 
                ORDER BY created_at ASC 
                LIMIT 1 
                FOR UPDATE SKIP LOCKED
            """
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                # Immediately update status to PROCESSING
                cursor.execute(
                    """
                    UPDATE queue 
                    SET status = 'PROCESSING', updated_at = CURRENT_TIMESTAMP 
                    WHERE queue_id = %s 
                    RETURNING *
                    """,
                    (result['queue_id'],)
                )
                result = cursor.fetchone()
                conn.commit()
                results = [result] if result else []
            else:
                # No PENDING items available (all locked or none exist)
                results = []
        else:
            # NORMAL MODE: Standard list/filter behavior (unchanged)
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
        
        # Create models for validation, then return dicts with camelCase keys
        # FastAPI's jsonable_encoder uses aliases for models, but preserves dict keys
        response_list = [QueueResponse(**result).model_dump(by_alias=False) for result in formatted_results]
        
        # Return list of dicts directly - FastAPI will serialize as-is (camelCase)
        # Bypassing response_model serialization which would use aliases
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_list)
        
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


@app.patch(
    "/queue/{queue_id}/status",
    tags=["Queue"],
    summary="Update queue entry status",
    description="Update a queue entry's status, optionally increment attempts, and store error messages or experity actions.",
    response_model=QueueResponse,
    responses={
        200: {
            "description": "Queue entry status updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "status": "DONE",
                        "attempts": 1,
                        "encounterPayload": {
                            "id": "550e8400-e29b-41d4-a716-446655440000"
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request data or invalid status value"},
        401: {"description": "Authentication required"},
        404: {"description": "Queue entry not found"},
        500: {"description": "Server error"},
    },
)
async def update_queue_status(
    queue_id: str,
    status_data: QueueStatusUpdateRequest,
    current_client: TokenData = get_auth_dependency()
) -> QueueResponse:
    """
    Update a queue entry's status.
    
    **Path Parameters:**
    - `queue_id`: Queue identifier (UUID)
    
    **Request Body:**
    - `status` (required): New status: `PENDING`, `PROCESSING`, `DONE`, or `ERROR`
    - `errorMessage` (optional): Error message to store (for ERROR status)
    - `incrementAttempts` (optional): Whether to increment the attempts counter (default: false)
    - `experityActions` (optional): Experity actions to store (for DONE status)
    - `dlq` (optional): Mark for Dead Letter Queue (for ERROR status)
    
    **Response:**
    Returns the updated queue entry with `emrId`, `status`, `attempts`, and `encounterPayload`.
    
    **Example Request:**
    ```json
    {
      "status": "DONE",
      "experityActions": {
        "vitals": {},
        "complaints": []
      }
    }
    ```
    """
    if not queue_id or not queue_id.strip():
        raise HTTPException(
            status_code=400,
            detail="queue_id is required in the URL path"
        )
    
    queue_id_clean = queue_id.strip()
    
    # Validate status
    valid_statuses = ['PENDING', 'PROCESSING', 'DONE', 'ERROR']
    if status_data.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {status_data.status}. Must be one of: {', '.join(valid_statuses)}"
        )
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if queue entry exists
        cursor.execute(
            "SELECT * FROM queue WHERE queue_id = %s",
            (queue_id_clean,)
        )
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            raise HTTPException(
                status_code=404,
                detail=f"Queue entry with queue_id '{queue_id_clean}' not found"
            )
        
        # Use the existing update function
        # Note: experityActions can be a dict (full experityActions object) or list
        # The function expects List[Dict[str, Any]], but we'll handle dict by storing it directly in parsed_payload
        experity_actions_list = None
        experity_actions_dict = None
        if status_data.experityActions is not None:
            if isinstance(status_data.experityActions, list):
                experity_actions_list = status_data.experityActions
            elif isinstance(status_data.experityActions, dict):
                # For dict, we'll store it directly in parsed_payload after the status update
                experity_actions_dict = status_data.experityActions
        
        # Update status using the existing function
        update_queue_status_and_experity_action(
            conn=conn,
            queue_id=queue_id_clean,
            status=status_data.status,
            experity_actions=experity_actions_list,
            error_message=status_data.errorMessage,
            increment_attempts=status_data.incrementAttempts or False
        )
        
        # Handle DLQ flag, experity_actions_dict, and errorMessage in parsed_payload
        if status_data.dlq is not None or experity_actions_dict is not None or status_data.errorMessage:
            cursor.execute(
                "SELECT parsed_payload FROM queue WHERE queue_id = %s",
                (queue_id_clean,)
            )
            current_entry = cursor.fetchone()
            parsed_payload = current_entry.get('parsed_payload') if current_entry else {}
            
            import json
            from psycopg2.extras import Json
            if isinstance(parsed_payload, str):
                try:
                    parsed_payload = json.loads(parsed_payload)
                except json.JSONDecodeError:
                    parsed_payload = {}
            elif parsed_payload is None:
                parsed_payload = {}
            
            # Store experity_actions_dict if provided (for DONE status with full experityActions object)
            if experity_actions_dict is not None:
                parsed_payload['experityActions'] = experity_actions_dict
            
            if status_data.dlq:
                parsed_payload['dlq'] = True
            if status_data.errorMessage and status_data.status == 'ERROR':
                parsed_payload['error_message'] = status_data.errorMessage
            
            cursor.execute(
                "UPDATE queue SET parsed_payload = %s WHERE queue_id = %s",
                (Json(parsed_payload), queue_id_clean)
            )
            conn.commit()
        
        # Get updated entry
        cursor.execute(
            "SELECT * FROM queue WHERE queue_id = %s",
            (queue_id_clean,)
        )
        updated_entry = cursor.fetchone()
        
        # Format the response
        formatted_response = format_queue_response(updated_entry)
        queue_response = QueueResponse(**formatted_response)
        response_dict = queue_response.model_dump(by_alias=False)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_dict)
        
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


@app.patch(
    "/queue/{queue_id}/requeue",
    tags=["Queue"],
    summary="Requeue a queue entry",
    description="Requeue a queue entry with updated priority and status. Increments attempts counter.",
    response_model=QueueResponse,
    responses={
        200: {
            "description": "Queue entry requeued successfully",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "status": "PENDING",
                        "attempts": 2,
                        "encounterPayload": {
                            "id": "550e8400-e29b-41d4-a716-446655440000"
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request data or invalid priority value"},
        401: {"description": "Authentication required"},
        404: {"description": "Queue entry not found"},
        500: {"description": "Server error"},
    },
)
async def requeue_queue_entry(
    queue_id: str,
    requeue_data: QueueRequeueRequest,
    current_client: TokenData = get_auth_dependency()
) -> QueueResponse:
    """
    Requeue a queue entry with updated priority.
    
    **Path Parameters:**
    - `queue_id`: Queue identifier (UUID)
    
    **Request Body:**
    - `status` (optional): New status (default: PENDING)
    - `priority` (optional): Priority level: `HIGH`, `NORMAL`, or `LOW` (default: HIGH)
    - `errorMessage` (optional): Optional error message
    
    **Response:**
    Returns the updated queue entry with `emrId`, `status`, `attempts`, and `encounterPayload`.
    The attempts counter is automatically incremented.
    
    **Example Request:**
    ```json
    {
      "status": "PENDING",
      "priority": "HIGH",
      "errorMessage": "Requeued for retry"
    }
    ```
    """
    if not queue_id or not queue_id.strip():
        raise HTTPException(
            status_code=400,
            detail="queue_id is required in the URL path"
        )
    
    queue_id_clean = queue_id.strip()
    
    # Validate status
    valid_statuses = ['PENDING', 'PROCESSING', 'DONE', 'ERROR']
    new_status = requeue_data.status or 'PENDING'
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {new_status}. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Validate priority
    valid_priorities = ['HIGH', 'NORMAL', 'LOW']
    priority = requeue_data.priority or 'HIGH'
    if priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {priority}. Must be one of: {', '.join(valid_priorities)}"
        )
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if queue entry exists
        cursor.execute(
            "SELECT * FROM queue WHERE queue_id = %s",
            (queue_id_clean,)
        )
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            raise HTTPException(
                status_code=404,
                detail=f"Queue entry with queue_id '{queue_id_clean}' not found"
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
        
        # Update priority in parsed_payload
        parsed_payload['priority'] = priority
        if requeue_data.errorMessage:
            parsed_payload['requeue_message'] = requeue_data.errorMessage
        
        # Update queue entry: status, priority, increment attempts
        cursor.execute(
            """
            UPDATE queue
            SET status = %s,
                parsed_payload = %s,
                attempts = attempts + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE queue_id = %s
            RETURNING *
            """,
            (new_status, Json(parsed_payload), queue_id_clean)
        )
        
        updated_entry = cursor.fetchone()
        conn.commit()
        
        # Format the response
        formatted_response = format_queue_response(updated_entry)
        queue_response = QueueResponse(**formatted_response)
        response_dict = queue_response.model_dump(by_alias=False)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_dict)
        
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
                            "bookingId": "0Pa1Z6",
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
        description="Filter by status. Use 'active' for active statuses (checked_in, confirmed). Defaults to checked_in, confirmed if not provided."
    ),
    current_client: TokenData = get_auth_dependency()
):
    """
    **Query Parameters:**
    - `locationId` (optional) - Required unless DEFAULT_LOCATION_ID is set
    - `statuses` (optional) - Defaults to checked_in, confirmed. Use 'active' for patients with checked_in/confirmed status.
    - `limit` (optional)
    
    **Example:**
    ```
    GET /patients?locationId=AXjwbE&statuses=confirmed&limit=50
    GET /patients?locationId=AXjwbE&statuses=active
    ```
    """
    # Check if 'active' shortcut was requested (for 24h filter)
    is_active_filter = statuses is not None and any(
        s.strip().lower() == "active" for s in statuses if isinstance(s, str)
    )
    
    if statuses is None:
        normalized_statuses = DEFAULT_STATUSES.copy()
    else:
        # First expand any shortcuts like 'active'
        expanded_statuses = expand_status_shortcuts(statuses)
        normalized_statuses = [
            normalize_status(status)
            for status in expanded_statuses
            if isinstance(status, str)
        ]
        normalized_statuses = [status for status in normalized_statuses if status]
        if not normalized_statuses:
            raise HTTPException(status_code=400, detail="At least one valid status must be provided")

    def filter_within_24h(patients: list) -> list:
        """Filter patients to only include those captured within the last 24 hours."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=24)
        
        filtered = []
        for patient in patients:
            captured_at = patient.get("captured_at") or patient.get("capturedAt")
            if captured_at:
                if isinstance(captured_at, str):
                    # Parse ISO format timestamp
                    try:
                        ts = captured_at.replace("Z", "+00:00")
                        captured_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                    except ValueError:
                        captured_dt = None
                elif isinstance(captured_at, datetime):
                    captured_dt = captured_at.replace(tzinfo=None) if captured_at.tzinfo else captured_at
                else:
                    captured_dt = None
                
                if captured_dt and captured_dt >= cutoff:
                    filtered.append(patient)
            # If no captured_at, check created_at as fallback
            else:
                created_at = patient.get("created_at") or patient.get("createdAt")
                if created_at:
                    if isinstance(created_at, str):
                        try:
                            ts = created_at.replace("Z", "+00:00")
                            created_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                        except ValueError:
                            created_dt = None
                    elif isinstance(created_at, datetime):
                        created_dt = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
                    else:
                        created_dt = None
                    
                    if created_dt and created_dt >= cutoff:
                        filtered.append(patient)
        return filtered

    try:
        normalized_location_id = resolve_location_id(locationId, required=False)
        normalized_location_id = ensure_client_location_access(normalized_location_id, current_client)
        use_remote_reads = use_remote_api_for_reads()

        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            patients_raw = await fetch_remote_patients(normalized_location_id, normalized_statuses, limit)
            
            # Apply 24h filter if 'active' shortcut was used
            if is_active_filter:
                patients_raw = filter_within_24h(patients_raw)
            
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
            
            # Apply 24h filter if 'active' shortcut was used
            if is_active_filter:
                patients_raw = filter_within_24h(patients_raw)
            
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
        
        # Use by_alias=False to output camelCase field names (matching OpenAPI schema)
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
        
        # Use by_alias=False to output camelCase field names (matching OpenAPI schema)
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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


@app.post(
    "/vm/heartbeat",
    tags=["VM"],
    summary="Update VM heartbeat",
    description="Receive and process VM heartbeat updates. Updates the VM health record with current status and processing queue ID.",
    response_model=VmHeartbeatResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM heartbeat processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "vmId": "vm-worker-1",
                        "lastHeartbeat": "2025-01-21T10:30:00Z",
                        "status": "healthy"
                    }
                }
            }
        },
        400: {"description": "Invalid request data or invalid status value"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def vm_heartbeat(
    heartbeat_data: VmHeartbeatRequest,
    current_client: TokenData = get_auth_dependency()
) -> VmHeartbeatResponse:
    """
    Update VM heartbeat status.
    
    **Request Body:**
    - `vmId` (required): VM identifier
    - `status` (required): VM status: `healthy`, `unhealthy`, or `idle`
    - `processingQueueId` (optional): Queue ID that the VM is currently processing
    
    **Response:**
    Returns the updated VM health record with `success`, `vmId`, `lastHeartbeat`, and `status`.
    
    **Example Request:**
    ```json
    {
      "vmId": "vm-worker-1",
      "status": "healthy",
      "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
    }
    ```
    """
    conn = None
    
    try:
        # Validate required fields
        if not heartbeat_data.vmId:
            raise HTTPException(
                status_code=400,
                detail="vmId is required. Please provide a VM identifier."
            )
        
        if not heartbeat_data.status:
            raise HTTPException(
                status_code=400,
                detail="status is required. Please provide a VM status."
            )
        
        # Validate status
        valid_statuses = ['healthy', 'unhealthy', 'idle']
        if heartbeat_data.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {heartbeat_data.status}. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Prepare VM health data
        vm_health_dict = {
            'vm_id': heartbeat_data.vmId,
            'status': heartbeat_data.status,
            'processing_queue_id': heartbeat_data.processingQueueId,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save/update the VM health record
        saved_vm_health = save_vm_health(conn, vm_health_dict)
        
        # Format the response - pass data using field names (camelCase)
        # The model will accept both field names and aliases due to populate_by_name=True
        response_data = {
            'success': True,
            'vmId': saved_vm_health['vm_id'],
            'lastHeartbeat': saved_vm_health['last_heartbeat'],
            'status': saved_vm_health['status'],
        }
        
        # Create response model and serialize with by_alias=False to output camelCase field names
        vm_response = VmHeartbeatResponse(**response_data)
        response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(content=response_dict)
        
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
    summary="Map encounter data to Experity actions",
    response_model=ExperityMapResponse,
    responses={
        200: {
            "description": "Successfully mapped encounter data to Experity actions.",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "experityActions": {
                                "emrId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                                "vitals": {
                                    "gender": "male",
                                    "ageYears": 69,
                                    "heightCm": 167.64,
                                    "weightKg": 63.50,
                                    "bodyMassIndex": 22.60,
                                    "weightClass": "normal",
                                    "pulseRateBpm": 20,
                                    "respirationBpm": 18,
                                    "bodyTemperatureCelsius": 37,
                                    "bloodPressureSystolicMm": 180,
                                    "bloodPressureDiastolicMm": 100,
                                    "pulseOx": 99
                                },
                                "guardianAssistedInterview": {
                                    "present": False,
                                    "guardianName": None,
                                    "relationship": None,
                                    "notes": None
                                },
                                "labOrders": [
                                    {
                                        "orderId": "316d977d-df36-4ed8-9df0-4cc83decc0b1",
                                        "name": "84 - Order and perform COVID test",
                                        "status": "performed",
                                        "priority": None,
                                        "reason": None
                                    }
                                ],
                                "icdUpdates": [],
                                "complaints": [
                                    {
                                        "encounterId": "6984a75c-1d07-4d1b-a35c-0f71d5416f87",
                                        "complaintId": "00f9612e-f37d-451b-9172-25cbddee58a9",
                                        "description": "cough",
                                        "traumaType": "NONE",
                                        "bodyPartRaw": None,
                                        "reviewOfSystemsCategory": "RESPIRATORY",
                                        "gender": "male",
                                        "bodyAreaKey": "Chest",
                                        "subLocationLabel": None,
                                        "experityTemplate": "Chest",
                                        "coordKey": "CHEST_PARENT",
                                        "bodyMapSide": "front",
                                        "ui": {
                                            "bodyMapClick": {
                                                "x": 183,
                                                "y": 556
                                            },
                                            "bodyPartId": 3
                                        },
                                        "mainProblem": "Cough",
                                        "notesTemplateKey": "CHEST_TEMPLATE_B",
                                        "notesPayload": {
                                            "quality": ["Chest tightness"],
                                            "severity": 3
                                        },
                                        "notesFreeText": "Patient reports cough for 10 days with pain scale of 3.",
                                        "reasoning": "Cough is a respiratory symptom mapped to Chest body area."
                                    }
                                ]
                            },
                            "encounter_id": "6984a75c-1d07-4d1b-a35c-0f71d5416f87",
                            "processed_at": "2025-01-21T10:30:00.000Z",
                            "queue_id": None
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid request data. Must provide either: (1) queue_entry with encounter_id or queue_id, or (2) direct encounter object with id field."
        },
        401: {"description": "Authentication required. Provide HMAC signature via X-Timestamp and X-Signature headers."},
        404: {"description": "Queue entry not found in database (Format 1 only)."},
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
    Map encounter data to Experity actions.
    
    **Two Input Formats Supported:**
    
    1. **Queue Entry Wrapper** - Wrap encounter in `queue_entry` object
       - Provide `encounter_id` or `queue_id` 
       - Optionally include `raw_payload` (otherwise fetched from database)
       - Queue status is automatically updated
    
    2. **Direct Encounter** - Send encounter JSON directly
       - Must include `id` field
       - All encounter fields at root level
       - No database lookup, no queue status updates
    
    **Response:** Returns Experity mapping with vitals, complaints, lab orders, and ICD updates.
    
    Requires HMAC authentication via X-Timestamp and X-Signature headers.
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
    
    # Detect input format: queue_entry wrapper (Format 1) or direct encounter (Format 2)
    is_direct_encounter = request_data.queue_entry is None
    if not is_direct_encounter:
        # Format 1: Queue Entry Wrapper
        queue_entry = request_data.queue_entry
        queue_id = queue_entry.get("queue_id")
        encounter_id = queue_entry.get("encounter_id")
        raw_payload = queue_entry.get("raw_payload")
    else:
        # Format 2: Direct Encounter Object
        # Treat the entire request body as the encounter data
        direct_encounter = body_json
        encounter_id = direct_encounter.get("id")
        queue_id = None
        raw_payload = direct_encounter
        
        # Create a queue_entry structure for processing
        # Only set emr_id if emrId actually exists in the encounter (not clientId)
        emr_id_value = direct_encounter.get("emrId") or direct_encounter.get("emr_id")
        queue_entry = {
            "encounter_id": encounter_id,
            "queue_id": None,
            "raw_payload": raw_payload,
        }
        # Only include emr_id if it's actually an emrId (not clientId)
        if emr_id_value:
            queue_entry["emr_id"] = emr_id_value
    
    try:
        # Validate we have encounter data
        # For queue_entry format: need encounter_id or queue_id
        # For direct encounter format: need id field
        if not encounter_id and not queue_id:
            return ExperityMapResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "Request must contain either: (1) queue_entry with 'encounter_id' or 'queue_id', or (2) direct encounter object with 'id' field"
                }
            )
        
        # Connect to database to fetch queue entry if needed
        # Skip database lookup for direct encounter format (we already have all the data)
        cursor = None
        if not is_direct_encounter:
            if not conn:
                conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Fetch queue entry from database if raw_payload is not provided
            # or if we need to get queue_id/encounter_id
            # Skip for direct encounter format
            db_queue_entry = None
            if not is_direct_encounter and (not raw_payload or not queue_id or not encounter_id):
                # Build query to fetch queue entry
                if queue_id:
                    cursor.execute(
                        "SELECT queue_id, encounter_id, emr_id, raw_payload FROM queue WHERE queue_id = %s",
                        (queue_id,)
                    )
                elif encounter_id:
                    cursor.execute(
                        "SELECT queue_id, encounter_id, emr_id, raw_payload FROM queue WHERE encounter_id = %s",
                        (encounter_id,)
                    )
                else:
                    if cursor is not None:
                        cursor.close()
                    return ExperityMapResponse(
                        success=False,
                        error={
                            "code": "VALIDATION_ERROR",
                            "message": "Must provide either queue_id or encounter_id to fetch queue entry"
                        }
                    )
                
                db_queue_entry = cursor.fetchone()
                
                if not db_queue_entry:
                    if cursor is not None:
                        cursor.close()
                    return ExperityMapResponse(
                        success=False,
                        error={
                            "code": "NOT_FOUND",
                            "message": "Queue entry not found in database"
                        }
                    )
                
                # Use database values to fill in missing fields
                if not queue_id:
                    queue_id = str(db_queue_entry.get('queue_id'))
                if not encounter_id:
                    encounter_id = str(db_queue_entry.get('encounter_id'))
                # Get emr_id from database
                db_emr_id = db_queue_entry.get('emr_id')
                if db_emr_id:
                    queue_entry["emr_id"] = str(db_emr_id)
                if not raw_payload:
                    # Get raw_payload from database
                    db_raw_payload = db_queue_entry.get('raw_payload')
                    if isinstance(db_raw_payload, str):
                        import json
                        try:
                            raw_payload = json.loads(db_raw_payload)
                        except json.JSONDecodeError:
                            raw_payload = {}
                    elif db_raw_payload is not None:
                        raw_payload = db_raw_payload
                    else:
                        raw_payload = {}
            
            # Validate we have raw_payload now
            if not raw_payload:
                if cursor is not None:
                    cursor.close()
                return ExperityMapResponse(
                    success=False,
                    error={
                        "code": "VALIDATION_ERROR",
                        "message": "raw_payload is required. Either provide it in the request or ensure the queue entry exists in the database."
                    }
                )
            
            # Update queue_entry with fetched/validated values
            queue_entry = {
                "queue_id": queue_id,
                "encounter_id": encounter_id,
                "raw_payload": raw_payload,
                **{k: v for k, v in queue_entry.items() if k not in ["queue_id", "encounter_id", "raw_payload"]}
            }
            
        finally:
            # Only close cursor if we created it (not in direct encounter mode)
            if cursor is not None:
                cursor.close()
            # Keep conn open if we need it for status updates
        
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
                logger.error(f"Azure AI authentication error: {str(e)}")
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_AUTH_ERROR",
                        "message": "Failed to authenticate with Azure AI. Please check Azure credentials configuration.",
                        "details": {
                            "suggestion": "Verify Azure credentials are properly configured and have access to the Azure AI service"
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
                            error_message="Authentication failed",
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
                logger.error(f"Azure AI rate limit error: {str(e)}")
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_RATE_LIMIT",
                        "message": f"Azure AI rate limit exceeded after {endpoint_max_retries} attempts with extended waits",
                        "details": {
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
                            error_message="Rate limit exceeded",
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=502, detail=error_response.dict())
            
            except AzureAITimeoutError as e:
                # Timeout errors can be retried
                last_endpoint_error = e
                logger.error(f"Azure AI timeout error: {str(e)}")
                if endpoint_attempt < endpoint_max_retries - 1:
                    wait_time = endpoint_retry_delay * (endpoint_attempt + 1)
                    logger.warning(
                        f"Timeout error on attempt {endpoint_attempt + 1}/{endpoint_max_retries}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                # Exhausted retries
                timeout_seconds = REQUEST_TIMEOUT if AZURE_AI_AVAILABLE else 120
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_TIMEOUT",
                        "message": f"Request to Azure AI agent timed out after {endpoint_max_retries} attempts. The request exceeded the {timeout_seconds} second timeout limit.",
                        "details": {
                            "attempts": endpoint_max_retries,
                            "timeout_seconds": timeout_seconds,
                            "suggestion": "Try increasing AZURE_AI_REQUEST_TIMEOUT environment variable or retry the request later"
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
                            error_message=f"Timeout after {endpoint_max_retries} attempts",
                            increment_attempts=True
                        )
                    except Exception:
                        pass
                raise HTTPException(status_code=504, detail=error_response.dict())
            
            except (AzureAIResponseError, AzureAIClientError) as e:
                # Response/Client errors can be retried (e.g., JSON parsing errors, incomplete responses)
                last_endpoint_error = e
                logger.error(f"Azure AI error: {str(e)}")
                if endpoint_attempt < endpoint_max_retries - 1:
                    wait_time = endpoint_retry_delay * (endpoint_attempt + 1)
                    logger.warning(
                        f"Azure AI error on attempt {endpoint_attempt + 1}/{endpoint_max_retries}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                # Exhausted retries
                error_type = "response error" if isinstance(e, AzureAIResponseError) else "client error"
                error_response = ExperityMapResponse(
                    success=False,
                    error={
                        "code": "AZURE_AI_ERROR",
                        "message": f"Azure AI agent encountered a {error_type} after {endpoint_max_retries} attempts. Please try again later or contact support if the issue persists.",
                        "details": {
                            "attempts": endpoint_max_retries,
                            "error_type": error_type,
                            "suggestion": "Retry the request or check Azure AI service status"
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
                            error_message=f"Azure AI {error_type} after {endpoint_max_retries} attempts",
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
            logger.error(f"No response from Azure AI after {endpoint_max_retries} attempts")
            error_response = ExperityMapResponse(
                success=False,
                error={
                    "code": "AZURE_AI_ERROR",
                    "message": f"Failed to get response from Azure AI after {endpoint_max_retries} attempts",
                    "details": {
                        "attempts": endpoint_max_retries,
                        "suggestion": "Please try again later or contact support if the issue persists"
                    }
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
        
        # Build success response with camelCase field names.
        # `experity_mapping` may wrap the core actions in one or more nested
        # `experityActions` keys (depending on how the Azure agent responded).
        # To avoid returning `experityActions.experityActions...`, unwrap
        # until we reach the actual payload that contains vitals/complaints/etc.
        experity_actions_payload = experity_mapping
        protected_keys = {"vitals", "complaints", "icdUpdates", "labOrders", "guardianAssistedInterview"}

        # Iteratively unwrap while we see an `experityActions` envelope whose
        # inner dict looks like the real payload (has any of the protected keys).
        while (
            isinstance(experity_actions_payload, dict)
            and "experityActions" in experity_actions_payload
            and isinstance(experity_actions_payload["experityActions"], dict)
            and protected_keys.intersection(experity_actions_payload["experityActions"].keys())
        ):
            experity_actions_payload = experity_actions_payload["experityActions"]

        response_data = {
            "experityActions": experity_actions_payload,
            "encounterId": encounter_id,
            "processedAt": datetime.now().isoformat() + "Z",
        }

        # Add emrId to response - get from queue_entry (which gets it from DB or direct encounter)
        emr_id = queue_entry.get("emr_id")
        if emr_id:
            response_data["emrId"] = emr_id

        # If the Azure response included its own queueId, prefer that when our local
        # value is missing. This keeps the response consistent without changing the
        # existing contract.
        if queue_id is None and isinstance(experity_mapping, dict) and "queueId" in experity_mapping:
            queue_id = experity_mapping.get("queueId")
        
        if queue_id:
            response_data["queueId"] = queue_id
        
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
                "message": "A database error occurred while processing the request",
                "details": {
                    "suggestion": "Please try again later or contact support if the issue persists"
                }
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error in map_queue_to_experity: {str(e)}", exc_info=True)
        return ExperityMapResponse(
            success=False,
            error={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred while processing the request",
                "details": {
                    "suggestion": "Please try again later or contact support if the issue persists"
                }
            }
        )
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================================
# IMAGE UPLOAD ENDPOINTS
# ============================================================================

class ImageUploadResponse(BaseModel):
    """Response model for image upload."""
    success: bool
    image_url: Optional[str] = None
    blob_name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None


async def verify_image_upload_auth(request: Request) -> bool:
    """
    Verify authentication for image uploads using X-API-Key header.
    
    Note: HMAC authentication doesn't work with multipart file uploads because
    the request body can only be read once, and FastAPI consumes it for file parsing.
    Instead, we use a simple API key check for image uploads.
    """
    api_key = request.headers.get("X-API-Key")
    
    # Check if API key matches any configured HMAC secret (reuse existing secrets)
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="X-API-Key header required for image uploads",
            headers={"WWW-Authenticate": "API-Key"}
        )
    
    # Verify against configured HMAC secrets
    from app.config.intellivisit_clients import INTELLIVISIT_CLIENTS
    
    for client_cfg in INTELLIVISIT_CLIENTS.values():
        secret = client_cfg.get("hmac_secret_key")
        if secret and api_key == secret:
            return True
    
    raise HTTPException(
        status_code=401,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "API-Key"}
    )


@app.post(
    "/images/upload",
    response_model=ImageUploadResponse,
    tags=["Images"],
    summary="Upload an image",
    description="""
Upload an image file to Azure Blob Storage.

**Supported formats:** JPEG, PNG, GIF, WebP

**Max file size:** 10MB

**Authentication:** Use `X-API-Key` header with your HMAC secret key.
(Note: HMAC signature auth is not used for file uploads due to multipart body handling)

**Returns:** The public URL of the uploaded image.
    """,
    responses={
        200: {"description": "Image uploaded successfully"},
        400: {"description": "Invalid file type or file too large"},
        401: {"description": "Missing or invalid X-API-Key header"},
        500: {"description": "Upload failed"},
        503: {"description": "Azure Blob Storage not configured"},
    }
)
async def upload_image(
    request: Request,
    file: UploadFile = File(..., description="Image file to upload"),
    folder: Optional[str] = Query(None, description="Optional folder path (e.g., 'encounters/123')"),
):
    """
    Upload an image to Azure Blob Storage.
    
    The image will be stored with a unique filename and the public URL will be returned.
    """
    # Verify API key authentication
    await verify_image_upload_auth(request)
    
    # Check if Azure Blob Storage is available
    if not AZURE_BLOB_AVAILABLE or not container_client:
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage is not configured. Please set AZURE_STORAGE_CONNECTION_STRING environment variable."
        )
    
    # Validate content type
    content_type = file.content_type
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type}. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES.keys())}"
        )
    
    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read file: {str(e)}"
        )
    
    # Check file size
    file_size = len(content)
    if file_size > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {file_size} bytes. Maximum allowed: {MAX_IMAGE_SIZE} bytes (10MB)"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty file uploaded"
        )
    
    # Generate unique blob name
    file_extension = ALLOWED_IMAGE_TYPES[content_type]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    
    # Sanitize original filename (remove extension, we'll add the correct one)
    original_name = file.filename or "image"
    # Remove any existing extension
    if "." in original_name:
        original_name = original_name.rsplit(".", 1)[0]
    safe_name = "".join(c for c in original_name if c.isalnum() or c in "_-").rstrip()
    if not safe_name:
        safe_name = "image"
    
    # Build blob name with optional folder
    if folder:
        # Sanitize folder path
        safe_folder = "/".join(
            "".join(c for c in part if c.isalnum() or c in "._-") 
            for part in folder.split("/") 
            if part
        )
        blob_name = f"{safe_folder}/{timestamp}_{unique_id}_{safe_name}{file_extension}"
    else:
        blob_name = f"{timestamp}_{unique_id}_{safe_name}{file_extension}"
    
    # Upload to Azure Blob Storage
    try:
        blob_client = container_client.get_blob_client(blob_name)
        
        # Set content settings for proper content type
        content_settings = ContentSettings(content_type=content_type)
        
        blob_client.upload_blob(
            content,
            content_settings=content_settings,
            overwrite=True
        )
        
        # Get the blob URL
        image_url = blob_client.url
        
        return ImageUploadResponse(
            success=True,
            image_url=image_url,
            blob_name=blob_name,
            content_type=content_type,
            size=file_size
        )
        
    except Exception as e:
        logger.error(f"Failed to upload image to Azure Blob Storage: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload image: {str(e)}"
        )


@app.get(
    "/images/status",
    tags=["Images"],
    summary="Check Azure Blob Storage status",
    description="Check if Azure Blob Storage is properly configured and accessible."
)
async def check_blob_storage_status(
    _auth: TokenData = Depends(get_current_client) if AUTH_ENABLED else Depends(lambda: None)
):
    """Check Azure Blob Storage configuration status."""
    return {
        "azure_blob_available": AZURE_BLOB_AVAILABLE,
        "connection_configured": bool(AZURE_STORAGE_CONNECTION_STRING),
        "container_name": AZURE_STORAGE_CONTAINER_NAME,
        "container_client_initialized": container_client is not None,
        "allowed_types": list(ALLOWED_IMAGE_TYPES.keys()),
        "max_size_bytes": MAX_IMAGE_SIZE,
        "max_size_mb": MAX_IMAGE_SIZE / (1024 * 1024)
    }


def sanitize_blob_name(image_name: str) -> str:
    """
    Sanitize image name to prevent path traversal attacks.
    
    Removes any path traversal sequences and limits to safe characters.
    
    Args:
        image_name: The image name from the URL path
        
    Returns:
        Sanitized image name (used as blob name internally)
        
    Raises:
        HTTPException: If image name contains invalid characters or path traversal attempts
    """
    # Check for path traversal attempts (before normalization)
    if ".." in image_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid image name: path traversal not allowed"
        )
    
    # Remove leading/trailing slashes and normalize
    image_name = image_name.strip("/")
    
    # Check if path was normalized to something outside our container
    # After normalization, paths like ../../../etc/passwd might become etc/passwd
    # We should reject anything that doesn't look like a valid image path
    if not image_name:
        raise HTTPException(
            status_code=400,
            detail="Image name cannot be empty"
        )
    
    # Check for absolute paths or paths that might escape the container
    if image_name.startswith("/") or "//" in image_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid image name: absolute paths not allowed"
        )
    
    # Check for invalid characters (allow alphanumeric, dots, hyphens, underscores, and forward slashes for folder paths)
    # But prevent any attempts at escaping or special characters
    if any(c in image_name for c in ['\\', '\0', '\r', '\n', '\t']):
        raise HTTPException(
            status_code=400,
            detail="Invalid image name: contains invalid characters"
        )
    
    # Additional check: reject common system paths that might have been normalized
    dangerous_paths = ['etc', 'usr', 'var', 'sys', 'proc', 'dev', 'root', 'home', 'bin', 'sbin']
    first_part = image_name.split('/')[0].lower()
    if first_part in dangerous_paths and '/' not in image_name.replace(first_part, '', 1):
        raise HTTPException(
            status_code=400,
            detail="Invalid image name: path traversal not allowed"
        )
    
    return image_name


def get_content_type_from_blob_name(blob_name: str) -> str:
    """
    Determine content type from blob file extension.
    
    Args:
        blob_name: The blob name
        
    Returns:
        MIME type string (defaults to image/jpeg if unknown)
    """
    blob_name_lower = blob_name.lower()
    
    if blob_name_lower.endswith('.jpg') or blob_name_lower.endswith('.jpeg'):
        return "image/jpeg"
    elif blob_name_lower.endswith('.png'):
        return "image/png"
    elif blob_name_lower.endswith('.gif'):
        return "image/gif"
    elif blob_name_lower.endswith('.webp'):
        return "image/webp"
    else:
        # Default to JPEG if extension is unknown
        return "image/jpeg"


@app.get(
    "/images/{image_name:path}",
    tags=["Images"],
    summary="View an image",
    description="""
Retrieve and view an image from Azure Blob Storage via proxy.

**Authentication:** Uses HMAC authentication (X-Timestamp and X-Signature headers).

**Path parameter:**
- `image_name`: The name of the image in the container (can include folder paths like `encounters/123/image.jpg`)

**Returns:** The image file streamed from Azure Blob Storage.
    """,
    responses={
        200: {
            "description": "Image retrieved successfully",
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/gif": {},
                "image/webp": {},
            }
        },
        400: {"description": "Invalid image name"},
        401: {"description": "Authentication required"},
        404: {"description": "Image not found"},
        503: {"description": "Azure Blob Storage not configured"},
    }
)
async def view_image(
    image_name: str,
    _auth: TokenData = Depends(get_current_client) if AUTH_ENABLED else Depends(lambda: None)
):
    """
    Proxy endpoint to view images from Azure Blob Storage.
    
    This endpoint fetches the image from Azure and streams it back to the client.
    The image name can include folder paths (e.g., 'encounters/123/image.jpg').
    """
    # Check if Azure Blob Storage is available
    if not AZURE_BLOB_AVAILABLE or not container_client:
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage is not configured. Please set AZURE_STORAGE_CONNECTION_STRING environment variable."
        )
    
    # Sanitize image name to prevent path traversal attacks
    try:
        sanitized_blob_name = sanitize_blob_name(image_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image name: {str(e)}"
        )
    
    # Get blob client
    try:
        blob_client = container_client.get_blob_client(sanitized_blob_name)
        
        # Check if blob exists
        if not blob_client.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Image not found: '{sanitized_blob_name}'"
            )
        
        # Get blob properties to determine content type
        blob_properties = blob_client.get_blob_properties()
        content_type = blob_properties.content_settings.content_type
        
        # If content type is not set or is generic, try to infer from filename
        if not content_type or content_type == "application/octet-stream":
            content_type = get_content_type_from_blob_name(sanitized_blob_name)
        
        # Download blob content
        blob_data = blob_client.download_blob()
        
        # Create a generator function to stream the blob
        def generate():
            try:
                # Stream the blob in chunks
                chunk_size = 8192  # 8KB chunks
                while True:
                    chunk = blob_data.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            except Exception as e:
                logger.error(f"Error streaming blob {sanitized_blob_name}: {str(e)}")
                raise
        
        # Return streaming response with proper headers
        return StreamingResponse(
            generate(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{sanitized_blob_name.split("/")[-1]}"',
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve image '{sanitized_blob_name}': {str(e)}")
        
        # Check if it's a 404 error from Azure
        error_msg = str(e).lower()
        if "not found" in error_msg or "404" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail=f"Image not found: '{sanitized_blob_name}'"
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve image: {str(e)}"
        )
