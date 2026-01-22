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
import json
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

# Configure logging
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException, Query, Request, Depends, Body, UploadFile, File, Form, BackgroundTasks
    from fastapi import Path as PathParam
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
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

# Import Azure AI client (using SDK-based implementation)
try:
    from app.utils.azure_ai_agent_client import (
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
    print("Warning: azure_ai_agent_client.py not found. Experity mapping endpoint will not work.")
    call_azure_ai_agent = None
    AZURE_AI_AVAILABLE = False
    AzureAIClientError = Exception
    AzureAIAuthenticationError = Exception
    AzureAIRateLimitError = Exception
    AzureAITimeoutError = Exception
    AzureAIResponseError = Exception
    REQUEST_TIMEOUT = 120

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

# Mount static files directory
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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

# Exception handlers for better error messages
from starlette.exceptions import HTTPException as StarletteHTTPException
import asyncio

@app.exception_handler(504)
async def timeout_exception_handler(request: Request, exc):
    """Handle 504 Gateway Timeout errors with user-friendly message."""
    # If it's an HTML request (browser), return a user-friendly error page
    if "text/html" in request.headers.get("accept", ""):
        error_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Temporarily Unavailable</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .error-container {
            background: white;
            border-radius: 12px;
            padding: 40px;
            max-width: 600px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            text-align: center;
        }
        h1 {
            color: #111920;
            font-size: 28px;
            margin-bottom: 16px;
        }
        p {
            color: #666;
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 24px;
        }
        .actions {
            margin-top: 32px;
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 0 8px;
            transition: background 0.2s;
        }
        .btn:hover {
            background: #5568d3;
        }
        .icon {
            font-size: 64px;
            margin-bottom: 24px;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="icon">⏱️</div>
        <h1>Service Temporarily Unavailable</h1>
        <p>
            The server is taking longer than expected to respond. This may be due to:
        </p>
        <ul style="text-align: left; color: #666; margin: 20px 0;">
            <li>High server load</li>
            <li>Database connection issues</li>
            <li>Temporary service maintenance</li>
        </ul>
        <p>
            Please try again in a few moments. If the problem persists, contact your administrator.
        </p>
        <div class="actions">
            <a href="/" class="btn">Go to Dashboard</a>
            <a href="javascript:location.reload()" class="btn">Retry</a>
        </div>
    </div>
</body>
</html>
        """
        return HTMLResponse(content=error_html, status_code=504)
    # For API requests, return JSON
    return JSONResponse(
        status_code=504,
        content={
            "error": {
                "code": "GATEWAY_TIMEOUT",
                "message": "The server took too long to respond. Please try again later.",
                "details": {
                    "path": str(request.url.path),
                    "suggestion": "Check application logs or try again in a few moments"
                }
            }
        }
    )

@app.exception_handler(asyncio.TimeoutError)
async def asyncio_timeout_handler(request: Request, exc):
    """Handle asyncio timeout errors."""
    return await timeout_exception_handler(request, None)

# Include authentication routes
if SESSION_AUTH_ENABLED and auth_router:
    app.include_router(auth_router)

# ============================================================================
# IMPORT MODULARIZED ROUTE MODULES (Phase 1 Refactoring)
# ============================================================================
# Import route modules - use absolute imports from submodules to avoid circular imports
from app.api.routes.ui import router as ui_router
from app.api.routes.patients import router as patients_router
from app.api.routes.encounters import router as encounters_router
from app.api.routes.summaries import router as summaries_router
from app.api.routes.vm_health import router as vm_health_router
from app.api.routes.queue import router as queue_router
from app.api.routes.queue_validation import router as queue_validation_router
from app.api.routes.images import router as images_router
from app.api.routes.validation import router as validation_router

# Include modularized routers
app.include_router(ui_router)
app.include_router(patients_router, tags=["Patients"])
app.include_router(encounters_router, tags=["Encounters"])
app.include_router(summaries_router, tags=["Summaries"])
app.include_router(vm_health_router, tags=["VM"])
app.include_router(queue_router, tags=["Queue"])
app.include_router(queue_validation_router, tags=["Queue"])
app.include_router(images_router, tags=["Images"])
app.include_router(validation_router, tags=["Validation"])

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
    VmHealthStatusResponse,
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
    get_latest_vm_health,
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
# NOTE: Many routes have been extracted to modular files in app/api/routes/
# See imports above for which modules are included.
# Routes marked with "EXTRACTED" below have been moved to their respective modules.

# ============================================================================
# UI ROUTES - EXTRACTED to app/api/routes/ui.py
# ============================================================================
# The following routes are now in app/api/routes/ui.py:
# - GET / (root dashboard)
# - GET /experity/chat
# - GET /queue/list
# - GET /images/
# - GET /emr/validation

# EXTRACTED ROUTE - Now in app/api/routes/ui.py
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('PORT', os.getenv('API_PORT', '8000')))
    host = os.getenv('API_HOST', '0.0.0.0')
    uvicorn.run(app, host=host, port=port)
        # if conn:
            # conn.close()
# END OF EXTRACTED ROUTE (get_vm_health)

# ============================================================================
# VALIDATION HELPER FUNCTIONS
# ============================================================================

def find_hpi_image_by_encounter_id(encounter_id: str) -> Optional[str]:
    """
    Find the first image with 'hpi' in the filename in the encounters/{encounter_id}/ folder.
    
    DEPRECATED: Use find_hpi_image_by_complaint() instead for complaint-specific images.
    Kept for backward compatibility.
    
    Returns:
        The full blob path to the HPI image, or None if not found
    """
    if not AZURE_BLOB_AVAILABLE or not container_client:
        logger.warning("Azure Blob Storage not available, cannot find HPI image")
        return None
    
    try:
        folder_path = f"encounters/{encounter_id}/"
        
        # List blobs with the prefix
        blobs = container_client.list_blobs(name_starts_with=folder_path)
        
        # Find the first image with 'hpi' in the filename (case-insensitive)
        for blob in blobs:
            blob_name_lower = blob.name.lower()
            # Check if it's an image file and contains 'hpi'
            if any(blob_name_lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                if 'hpi' in blob_name_lower:
                    logger.info(f"Found HPI image: {blob.name}")
                    return blob.name
        
        logger.warning(f"No HPI image found in folder: {folder_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding HPI image for encounter {encounter_id}: {str(e)}")
        return None


def find_hpi_image_by_complaint(encounter_id: str, complaint_id: str) -> Optional[str]:
    """
    Find HPI image for a specific complaint using format: {complaint_id}_hpi.{ext}
    
    Searches for images matching the pattern: {complaint_id}_hpi.{ext}
    Supports multiple image formats: .png, .jpg, .jpeg, .gif, .webp
    
    Args:
        encounter_id: The encounter ID
        complaint_id: The complaint ID (UUID format)
    
    Returns:
        The full blob path to the HPI image, or None if not found
    """
    if not AZURE_BLOB_AVAILABLE or not container_client:
        logger.warning("Azure Blob Storage not available, cannot find HPI image")
        return None
    
    if not complaint_id:
        logger.warning(f"complaint_id is required for finding complaint-specific HPI image")
        return None
    
    try:
        folder_path = f"encounters/{encounter_id}/"
        
        # List blobs with the prefix
        blobs = container_client.list_blobs(name_starts_with=folder_path)
        
        # Search for image with pattern: {complaint_id}_hpi.{ext}
        # Try both underscore and hyphen separators for flexibility
        patterns = [
            f"{complaint_id}_hpi",
            f"{complaint_id}-hpi"
        ]
        
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        
        for blob in blobs:
            blob_name_lower = blob.name.lower()
            # Check if it's an image file
            if any(blob_name_lower.endswith(ext) for ext in image_extensions):
                # Check if it matches any of our patterns
                for pattern in patterns:
                    if pattern.lower() in blob_name_lower:
                        logger.info(f"Found HPI image for complaint {complaint_id}: {blob.name}")
                        return blob.name
        
        logger.warning(f"No HPI image found for complaint {complaint_id} in folder: {folder_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding HPI image for complaint {complaint_id} in encounter {encounter_id}: {str(e)}")
        return None


def find_encounter_image(encounter_id: str, image_type: str) -> Optional[str]:
    """
    Find encounter-level image using format: {encounter_id}_{image_type}.png
    
    Searches for images matching the pattern: {encounter_id}_{image_type}.png
    Supports multiple image formats: .png, .jpg, .jpeg, .gif, .webp
    
    Args:
        encounter_id: The encounter ID
        image_type: The image type (e.g., 'icd', 'historian')
    
    Returns:
        The full blob path to the image, or None if not found
    """
    if not AZURE_BLOB_AVAILABLE or not container_client:
        logger.warning("Azure Blob Storage not available, cannot find encounter image")
        return None
    
    if not image_type:
        logger.warning(f"image_type is required for finding encounter image")
        return None
    
    try:
        folder_path = f"encounters/{encounter_id}/"
        
        # List blobs with the prefix
        blobs = container_client.list_blobs(name_starts_with=folder_path)
        
        # Search for image with pattern: {encounter_id}_{image_type}.{ext}
        # Primary pattern: encounter_id_icd.png, encounter_id_historian.png
        pattern = f"{encounter_id}_{image_type}"
        
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        
        for blob in blobs:
            blob_name_lower = blob.name.lower()
            # Check if it's an image file
            if any(blob_name_lower.endswith(ext) for ext in image_extensions):
                # Check if it matches our pattern (case-insensitive)
                if pattern.lower() in blob_name_lower:
                    logger.info(f"Found {image_type} image for encounter {encounter_id}: {blob.name}")
                    return blob.name
        
        logger.warning(f"No {image_type} image found for encounter {encounter_id} in folder: {folder_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding {image_type} image for encounter {encounter_id}: {str(e)}")
        return None


def get_image_bytes_from_blob(image_path: str) -> Optional[bytes]:
    """
    Download image bytes from Azure Blob Storage with caching support.
    
    This function first checks the in-memory cache before downloading
    from Azure Blob Storage. Downloaded images are automatically cached for
    faster subsequent access.
    
    Backward compatible: Falls back to direct download if cache is unavailable.
    
    Returns:
        Image bytes, or None if error
    """
    # Try cache first (backward compatible - continues if cache unavailable)
    try:
        from app.utils.image_cache import get_cached_image, cache_image
        cached = get_cached_image(image_path)
        if cached:
            logger.debug(f"Image served from cache: {image_path}")
            return cached
    except ImportError:
        # Cache module not available - continue with direct download
        logger.debug("Image cache module not available, using direct download")
    except Exception as e:
        # Cache lookup failed - continue with direct download
        logger.debug(f"Cache lookup failed: {e}, falling back to direct download")
    
    # Original download logic (unchanged for backward compatibility)
    if not AZURE_BLOB_AVAILABLE or not container_client:
        logger.warning("Azure Blob Storage not available, cannot download image")
        return None
    
    try:
        blob_client = container_client.get_blob_client(image_path)
        
        if not blob_client.exists():
            logger.warning(f"Image not found: {image_path}")
            return None
        
        # Download blob content
        blob_data = blob_client.download_blob()
        image_bytes = blob_data.readall()
        
        logger.info(f"Downloaded image from {image_path}, size: {len(image_bytes)} bytes")
        
        # Cache the downloaded image (backward compatible - continues if caching fails)
        try:
            from app.utils.image_cache import cache_image
            cache_image(image_path, image_bytes)
        except ImportError:
            # Cache module not available - continue without caching
            pass
        except Exception as e:
            # Cache failed - continue without caching
            logger.debug(f"Failed to cache image: {e}")
        
        return image_bytes
        
    except Exception as e:
        logger.error(f"Error downloading image from {image_path}: {str(e)}")
        return None


def run_validation_internal(image_bytes: bytes, experity_action_json: str) -> Dict[str, Any]:
    """
    Run validation using Azure AI ImageMapper agent.
    This extracts the core validation logic from /emr/validate endpoint.
    
    Returns:
        Validation result dict (same format as /emr/validate)
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents import AgentsClient
        from azure.core.rest import HttpRequest
        from azure.core.exceptions import HttpResponseError
    except ImportError:
        logger.error("Azure AI Agents SDK not installed")
        return {
            "overall_status": "ERROR",
            "error": "Azure AI Agents SDK not installed"
        }
    
    try:
        # Hardcoded configuration (same as /emr/validate)
        project_endpoint = "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"
        agent_name = "ImageMapper"
        
        # Convert image bytes to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        image_mime_type = "image/jpeg"  # Default, could be improved by detecting from file
        
        # Parse JSON (should already be a string)
        try:
            json_data = json.loads(experity_action_json) if isinstance(experity_action_json, str) else experity_action_json
        except (json.JSONDecodeError, TypeError):
            json_data = experity_action_json  # Already a dict
        
        json_string = json.dumps(json_data, indent=2)
        
        # Initialize Azure AI Agents client
        credential = DefaultAzureCredential()
        agents_client = AgentsClient(
            credential=credential,
            endpoint=project_endpoint,
        )
        
        # Get the agent by name
        agents = agents_client.list_agents()
        agent = None
        for a in agents:
            if a.name == agent_name:
                agent = a
                break
        
        if not agent:
            logger.error(f"Agent '{agent_name}' not found")
            return {
                "overall_status": "ERROR",
                "error": f"Agent '{agent_name}' not found"
            }
        
        agent_id = agent.id
        logger.info(f"Found agent: {agent_id} ({agent.name})")
        
        # Create message content with image and JSON
        message_content = [
            {
                "type": "text",
                "text": f"## JSON TO VALIDATE:\n{json_string}\n\n---\n\nAnalyze the screenshot and return the validation report."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_mime_type};base64,{image_base64}"
                }
            }
        ]
        
        # Create thread and run the agent
        run_params = {
            "agent_id": agent_id,
            "thread": {
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ]
            },
            "polling_interval": 2.0,
        }
        
        logger.info(f"Creating thread and running agent: {agent_id}")
        run = agents_client.create_thread_and_process_run(**run_params)
        
        logger.info(f"Run completed with status: {run.status}")
        
        # Check run status
        if run.status == "failed":
            error_msg = getattr(run, 'last_error', None)
            if error_msg:
                error_msg = getattr(error_msg, 'message', str(error_msg))
            else:
                error_msg = "Unknown error"
            raise Exception(f"Agent run failed: {error_msg}")
        
        if run.status == "cancelled":
            raise Exception("Agent run was cancelled")
        
        if run.status == "expired":
            raise Exception("Agent run expired")
        
        # Get the response from the thread
        if not hasattr(run, 'thread_id') or not run.thread_id:
            raise Exception("Run completed but no thread_id found")
        
        thread_id = run.thread_id
        logger.info(f"Fetching messages from thread: {thread_id}")
        
        # Use send_request to get messages from the thread
        messages_url = f"{project_endpoint}/threads/{thread_id}/messages?api-version=2025-11-15-preview"
        request = HttpRequest("GET", messages_url)
        
        response = agents_client.send_request(request)
        response.raise_for_status()
        messages_data = response.json()
        
        # Extract messages list from response
        messages_list = None
        if isinstance(messages_data, dict):
            messages_list = messages_data.get("data") or messages_data.get("messages") or messages_data.get("value")
        elif isinstance(messages_data, list):
            messages_list = messages_data
        
        if not messages_list:
            raise Exception("No messages found in thread response")
        
        # Find assistant message
        response_text = None
        for msg in reversed(messages_list):
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            role_str = str(role).lower() if role else ""
            
            if role_str in ["assistant", "agent"]:
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                if content:
                    if isinstance(content, list) and len(content) > 0:
                        first_item = content[0]
                        if isinstance(first_item, dict) and "text" in first_item:
                            text_obj = first_item["text"]
                            response_text = text_obj.get("value") if isinstance(text_obj, dict) else str(text_obj)
                        else:
                            response_text = str(first_item)
                    elif isinstance(content, str):
                        response_text = content
                    else:
                        response_text = str(content)
                    
                    if response_text:
                        break
        
        if not response_text:
            raise Exception("No assistant message found in thread")
        
        # Parse JSON response (handle markdown code blocks and extra text)
        try:
            cleaned_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith('```'):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            
            # Try to extract JSON if there's extra text before or after
            # Look for the first { and try to find the matching closing }
            json_start = cleaned_text.find('{')
            if json_start >= 0:
                # Find the matching closing brace
                brace_count = 0
                json_end = -1
                for i in range(json_start, len(cleaned_text)):
                    if cleaned_text[i] == '{':
                        brace_count += 1
                    elif cleaned_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                
                if json_end > json_start:
                    # Extract just the JSON portion
                    cleaned_text = cleaned_text[json_start:json_end]
            
            validation_result = json.loads(cleaned_text)
            
            # Handle new response format with "extraction" and "validation" sections
            if isinstance(validation_result, dict) and "validation" in validation_result:
                validation_result = {
                    **validation_result.get("validation", {}),
                    "extraction": validation_result.get("extraction", {})
                }
            elif isinstance(validation_result, dict) and "overall_status" in validation_result:
                # Already in correct format
                pass
            else:
                # Unexpected format, wrap it
                validation_result = {
                    "overall_status": "ERROR",
                    "error": "Unexpected response format",
                    "raw_response": validation_result
                }
                
        except json.JSONDecodeError as e:
            # If parsing failed, try to extract JSON from the response more aggressively
            try:
                # Try to find JSON object in the response
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    validation_result = json.loads(json_str)
                    logger.warning(f"Successfully extracted JSON from response with extra text")
                else:
                    raise json.JSONDecodeError("No JSON object found", cleaned_text, 0)
            except (json.JSONDecodeError, Exception) as e2:
                validation_result = {
                    "overall_status": "ERROR",
                    "error": f"Failed to parse response as JSON: {str(e)}",
                    "raw_response": response_text[:1000]  # Show more context for debugging
                }
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Error running validation: {str(e)}", exc_info=True)
        return {
            "overall_status": "ERROR",
            "error": str(e)
        }


def save_validation_result(conn, queue_id: str, encounter_id: str, validation_result: Dict[str, Any], complaint_id: Optional[str] = None) -> None:
    """
    Save or update validation result in queue_validations table (upsert).
    
    Args:
        conn: Database connection
        queue_id: Queue identifier
        encounter_id: Encounter identifier
        validation_result: Validation result dictionary
        complaint_id: Optional complaint ID (for complaint-specific validations)
    """
    from psycopg2.extras import Json
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Upsert validation result using composite unique constraint (queue_id, complaint_id)
        cursor.execute(
            """
            INSERT INTO queue_validations (queue_id, encounter_id, complaint_id, validation_result, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (queue_id, complaint_id) 
            DO UPDATE SET 
                validation_result = EXCLUDED.validation_result,
                updated_at = CURRENT_TIMESTAMP
            """,
            (queue_id, encounter_id, complaint_id, Json(validation_result))
        )
        conn.commit()
        complaint_info = f"complaint_id: {complaint_id}" if complaint_id else "no complaint_id"
        logger.info(f"Saved validation result for queue_id: {queue_id}, {complaint_info}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving validation result: {str(e)}", exc_info=True)
        raise e
    finally:
        cursor.close()


def trigger_validation_for_queue_entry(queue_id: str) -> None:
    """
    Main orchestrator function to trigger validation for a queue entry.
    This function:
    1. Reads encounter_id and experityAction from queue table
    2. Extracts complaints from experityAction
    3. For each complaint:
       - Finds its specific HPI image using format: {complaint_id}_hpi.{ext}
       - Validates that complaint's data against the HPI image
       - Saves validation result with complaint_id
    
    This is designed to be called as a background task.
    """
    conn = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get queue entry with encounter_id and parsed_payload
        cursor.execute(
            "SELECT encounter_id, parsed_payload FROM queue WHERE queue_id = %s",
            (queue_id,)
        )
        queue_entry = cursor.fetchone()
        
        if not queue_entry:
            logger.warning(f"Queue entry not found: {queue_id}")
            return
        
        encounter_id = queue_entry.get('encounter_id')
        if not encounter_id:
            logger.warning(f"No encounter_id found for queue_id: {queue_id}")
            return
        
        encounter_id_str = str(encounter_id)
        
        # Parse parsed_payload to get experityAction
        parsed_payload = queue_entry.get('parsed_payload')
        if isinstance(parsed_payload, str):
            try:
                parsed_payload = json.loads(parsed_payload)
            except json.JSONDecodeError:
                parsed_payload = {}
        elif parsed_payload is None:
            parsed_payload = {}
        
        # Get experityAction - check both 'experityAction' and 'experityActions' keys
        experity_action = parsed_payload.get('experityAction') or parsed_payload.get('experityActions')
        
        if not experity_action:
            logger.warning(f"No experityAction found in parsed_payload for queue_id: {queue_id}")
            return
        
        # Extract complaints from experityAction
        # Handle both new format (complaints array) and legacy format (array of actions)
        complaints = []
        if isinstance(experity_action, dict):
            # New format: experityAction.complaints[]
            complaints = experity_action.get('complaints', [])
        elif isinstance(experity_action, list):
            # Legacy format: array of complaint objects
            complaints = experity_action
        
        if not complaints or len(complaints) == 0:
            logger.warning(f"No complaints found in experityAction for queue_id: {queue_id}")
            return
        
        logger.info(f"Found {len(complaints)} complaints to validate for queue_id: {queue_id}")
        
        # Validate each complaint separately
        validation_count = 0
        for idx, complaint in enumerate(complaints):
            if not isinstance(complaint, dict):
                logger.warning(f"Complaint at index {idx} is not a dictionary, skipping")
                continue
            
            complaint_id = complaint.get('complaintId')
            if not complaint_id:
                # This should not happen - azure_ai_agent_client.py guarantees complaintId exists
                # But handle gracefully if it does
                logger.error(f"Complaint at index {idx} has no complaintId - this should not happen! Skipping validation.")
                logger.error(f"Complaint data: {json.dumps(complaint, indent=2)}")
                continue
            
            complaint_id_str = str(complaint_id)
            logger.info(f"Validating complaint {idx + 1}/{len(complaints)}: complaint_id={complaint_id_str}")
            
            # Find HPI image for this specific complaint
            hpi_image_path = find_hpi_image_by_complaint(encounter_id_str, complaint_id_str)
            if not hpi_image_path:
                logger.warning(f"No HPI image found for complaint {complaint_id_str} in encounter {encounter_id_str}")
                # Save error result for this complaint
                error_result = {
                    "overall_status": "ERROR",
                    "error": f"HPI image not found for complaint {complaint_id_str}. Expected format: {complaint_id_str}_hpi.{{ext}}"
                }
                save_validation_result(conn, queue_id, encounter_id_str, error_result, complaint_id_str)
                continue
            
            # Download image bytes
            image_bytes = get_image_bytes_from_blob(hpi_image_path)
            if not image_bytes:
                logger.warning(f"Failed to download image from: {hpi_image_path}")
                # Save error result for this complaint
                error_result = {
                    "overall_status": "ERROR",
                    "error": f"Failed to download HPI image from: {hpi_image_path}"
                }
                save_validation_result(conn, queue_id, encounter_id_str, error_result, complaint_id_str)
                continue
            
            # Convert single complaint to JSON string for validation
            # The validation agent expects a complaint object, not the full experityAction
            complaint_json = json.dumps(complaint, indent=2)
            
            # Run validation for this complaint
            logger.info(f"Running validation for complaint {complaint_id_str} (queue_id: {queue_id})")
            validation_result = run_validation_internal(image_bytes, complaint_json)
            
            # Save validation result with complaint_id
            save_validation_result(conn, queue_id, encounter_id_str, validation_result, complaint_id_str)
            validation_count += 1
            
            status = validation_result.get('overall_status', 'UNKNOWN')
            logger.info(f"Validation completed for complaint {complaint_id_str}: {status}")
        
        logger.info(f"Validation completed for queue_id: {queue_id}. Validated {validation_count}/{len(complaints)} complaints")
        
    except Exception as e:
        logger.error(f"Error in trigger_validation_for_queue_entry for queue_id {queue_id}: {str(e)}", exc_info=True)
    finally:
        if conn:
            cursor.close()
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


