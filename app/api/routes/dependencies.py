"""
Shared dependencies and imports for route modules.

This module provides common imports, dependencies, and utilities
that are used across multiple route modules.
"""

import logging
from typing import Optional
from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

# Import authentication
try:
    from app.utils.auth import get_current_client, TokenData
    AUTH_ENABLED = True
except ImportError:
    get_current_client = None
    TokenData = None
    AUTH_ENABLED = False

# Import session-based authentication for web UI
try:
    from app.api.auth_routes import require_auth
    SESSION_AUTH_ENABLED = True
except ImportError:
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
        async def no_auth():
            return None
        return Depends(no_auth)

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))

# Import models
from app.api.models import (
    PatientPayload,
    PatientCreateRequest,
    StatusUpdateRequest,
    EncounterResponse,
    QueueUpdateRequest,
    QueueStatusUpdateRequest,
    QueueRequeueRequest,
    QueueResponse,
    ExperityMapRequest,
    ExperityMapResponse,
    SummaryRequest,
    SummaryResponse,
    VmHeartbeatRequest,
    VmHeartbeatResponse,
    VmHealthStatusResponse,
    ServerHeartbeatRequest,
    ServerHeartbeatResponse,
    ImageUploadResponse,
    AlertRequest,
    AlertResponse,
    AlertItem,
    AlertListResponse,
    AlertResolveResponse,
    ExperityProcessTimeRequest,
    ExperityProcessTimeResponse,
    ExperityProcessTimeItem,
    ExperityProcessTimeListResponse,
)

# Import utilities
from app.api.utils import (
    normalize_status,
    expand_status_shortcuts,
    ensure_client_location_access,
    resolve_location_id,
    use_remote_api_for_reads,
    fetch_locations,
    fetch_remote_patients,
    DEFAULT_STATUSES,
)

# Import database functions
from app.api.database import (
    get_db_connection,
    save_encounter,
    save_summary,
    save_vm_health,
    save_server_health,
    get_latest_vm_health,
    get_summary_by_emr_id,
    get_summary_by_encounter_id,
    create_queue_from_encounter,
    update_queue_status_and_experity_action,
    save_alert,
    get_alerts,
    resolve_alert,
    save_experity_process_time,
    get_experity_process_times,
)

# Import services
from app.api.services import (
    build_patient_payload,
    format_encounter_response,
    format_queue_response,
    format_summary_response,
    filter_patients_by_search,
    get_local_patients,
    filter_within_24h,
)

# Azure AI imports
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
    call_azure_ai_agent = None
    AZURE_AI_AVAILABLE = False
    AzureAIClientError = Exception
    AzureAIAuthenticationError = Exception
    AzureAIRateLimitError = Exception
    AzureAITimeoutError = Exception
    AzureAIResponseError = Exception
    REQUEST_TIMEOUT = 120

# Azure Blob Storage imports
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    BlobServiceClient = None
    ContentSettings = None
    AZURE_BLOB_AVAILABLE = False

# Import patient saving functions
try:
    from app.database.utils import normalize_patient_record
    from tests.save_to_db import insert_patients
except ImportError:
    try:
        from save_to_db import normalize_patient_record, insert_patients
    except ImportError:
        normalize_patient_record = None
        insert_patients = None

__all__ = [
    "logger",
    "AUTH_ENABLED",
    "SESSION_AUTH_ENABLED",
    "get_current_client",
    "TokenData",
    "require_auth",
    "get_auth_dependency",
    "templates",
    "PatientPayload",
    "PatientCreateRequest",
    "StatusUpdateRequest",
    "EncounterResponse",
    "QueueUpdateRequest",
    "QueueStatusUpdateRequest",
    "QueueRequeueRequest",
    "QueueResponse",
    "ExperityMapRequest",
    "ExperityMapResponse",
    "SummaryRequest",
    "SummaryResponse",
    "VmHeartbeatRequest",
    "VmHeartbeatResponse",
    "VmHealthStatusResponse",
    "ImageUploadResponse",
    "AlertRequest",
    "AlertResponse",
    "AlertItem",
    "AlertListResponse",
    "AlertResolveResponse",
    "normalize_status",
    "expand_status_shortcuts",
    "ensure_client_location_access",
    "resolve_location_id",
    "use_remote_api_for_reads",
    "fetch_locations",
    "fetch_remote_patients",
    "DEFAULT_STATUSES",
    "get_db_connection",
    "save_encounter",
    "save_summary",
    "save_vm_health",
    "get_latest_vm_health",
    "get_summary_by_emr_id",
    "get_summary_by_encounter_id",
    "create_queue_from_encounter",
    "update_queue_status_and_experity_action",
    "save_alert",
    "get_alerts",
    "resolve_alert",
    "build_patient_payload",
    "format_encounter_response",
    "format_queue_response",
    "format_summary_response",
    "filter_patients_by_search",
    "get_local_patients",
    "filter_within_24h",
    "call_azure_ai_agent",
    "AzureAIClientError",
    "AzureAIAuthenticationError",
    "AzureAIRateLimitError",
    "AzureAITimeoutError",
    "AzureAIResponseError",
    "REQUEST_TIMEOUT",
    "AZURE_AI_AVAILABLE",
    "AZURE_BLOB_AVAILABLE",
    "BlobServiceClient",
    "ContentSettings",
    "normalize_patient_record",
    "insert_patients",
]

