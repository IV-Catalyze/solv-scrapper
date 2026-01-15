"""
Image routes for managing image uploads and retrieval from Azure Blob Storage.

This module contains all routes related to image management.
"""

import logging
import os
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from psycopg2.extras import RealDictCursor
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_current_client,
    TokenData,
    AUTH_ENABLED,
    ImageUploadResponse,
    AZURE_BLOB_AVAILABLE,
    BlobServiceClient,
    ContentSettings,
)

router = APIRouter()

# Azure Blob Storage setup (from routes.py)
# These will need to be imported or redefined
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    BlobServiceClient = None
    ContentSettings = None
    AZURE_BLOB_AVAILABLE = False

# Container client initialization (needs to be imported from routes.py or redefined)
container_client = None
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_STORAGE_CONTAINER_NAME = os.getenv('AZURE_STORAGE_CONTAINER_NAME', 'testcontainer')
if AZURE_BLOB_AVAILABLE:
    try:
        if AZURE_STORAGE_CONNECTION_STRING:
            blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
            logger.info(f"Azure Blob Storage initialized. Container: {AZURE_STORAGE_CONTAINER_NAME}")
        else:
            logger.warning("AZURE_STORAGE_CONNECTION_STRING not set. Image upload/retrieval will be disabled.")
    except Exception as e:
        logger.error(f"Failed to initialize Azure Blob Storage: {e}")
        container_client = None

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# Helper functions (from routes.py - need to import or redefine)
def sanitize_blob_name(blob_name: str) -> str:
    """Sanitize blob name to prevent path traversal attacks."""
    # Remove leading/trailing slashes and dots
    blob_name = blob_name.strip('/.')
    # Replace any '..' with empty string
    blob_name = blob_name.replace('..', '')
    # Remove any remaining path separators
    blob_name = blob_name.replace('\\', '/')
    # Split and rejoin to normalize
    parts = [p for p in blob_name.split('/') if p and p != '.' and p != '..']
    return '/'.join(parts)

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

def get_content_type_from_blob_name(blob_name: str) -> str:
    """Determine content type from blob name extension."""
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
        return "image/jpeg"

@router.post(

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

    

    # Generate blob name from original filename

    file_extension = ALLOWED_IMAGE_TYPES[content_type]

    

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

        blob_name = f"{safe_folder}/{safe_name}{file_extension}"

    else:

        blob_name = f"{safe_name}{file_extension}"

    

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




@router.get(

    "/images/list",

    tags=["Images"],

    summary="List images and folders",

    description="""

List images and folders from Azure Blob Storage.



**Authentication:** Uses HMAC authentication (X-Timestamp and X-Signature headers).



**Query parameters:**

- `folder`: Optional folder path to list (e.g., 'encounters/123'). If not provided, lists root level.



**Returns:** JSON object with folders and images arrays.

    """,

    responses={

        200: {"description": "List of folders and images"},

        401: {"description": "Authentication required"},

        503: {"description": "Azure Blob Storage not configured"},

    }

)

async def list_images(

    folder: Optional[str] = Query(None, description="Folder path to list"),

    _auth: TokenData = Depends(get_current_client) if AUTH_ENABLED else Depends(lambda: None)

):

    """

    List images and folders from Azure Blob Storage.

    

    Returns a structured list of folders and images in the specified folder path.

    """

    # Check if Azure Blob Storage is available

    if not AZURE_BLOB_AVAILABLE or not container_client:

        raise HTTPException(

            status_code=503,

            detail="Azure Blob Storage is not configured. Please set AZURE_STORAGE_CONNECTION_STRING environment variable."

        )

    

    # Sanitize folder path if provided

    prefix = ""

    if folder:

        # Sanitize folder path

        folder = folder.strip("/")

        if ".." in folder:

            raise HTTPException(

                status_code=400,

                detail="Invalid folder path: path traversal not allowed"

            )

        prefix = folder + "/" if folder else ""

    

    try:

        # List blobs with the prefix

        folders_dict = {}  # folder_name -> earliest creation time

        images = []

        

        # List all blobs with the prefix

        blob_list = container_client.list_blobs(name_starts_with=prefix)

        

        for blob in blob_list:

            # Remove prefix from blob name

            relative_name = blob.name[len(prefix):] if prefix else blob.name

            

            # Skip if empty (this would be the folder itself)

            if not relative_name:

                continue

            

            # Get blob creation time (use last_modified as creation time indicator)

            # Note: Azure Blob Storage doesn't track folder creation separately,

            # so we use the earliest last_modified time of blobs in the folder

            blob_creation_time = None

            if hasattr(blob, 'last_modified') and blob.last_modified:

                blob_creation_time = blob.last_modified

            elif hasattr(blob, 'creation_time') and blob.creation_time:

                blob_creation_time = blob.creation_time

            

            # Check if this is a folder (contains a slash) or an image file

            if "/" in relative_name:

                # This is in a subfolder - extract the folder name

                folder_name = relative_name.split("/")[0]

                

                # Track the earliest creation time for this folder

                if folder_name not in folders_dict:

                    folders_dict[folder_name] = blob_creation_time

                elif blob_creation_time and (folders_dict[folder_name] is None or blob_creation_time < folders_dict[folder_name]):

                    folders_dict[folder_name] = blob_creation_time

            else:

                # This is an image file

                # Check if it's a valid image extension

                blob_lower = relative_name.lower()

                if any(blob_lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):

                    # Get blob properties for size and last modified

                    blob_client = container_client.get_blob_client(blob.name)

                    try:

                        props = blob_client.get_blob_properties()

                        images.append({

                            "name": relative_name,

                            "full_path": blob.name,

                            "size": props.size,

                            "last_modified": props.last_modified.isoformat() if props.last_modified else None,

                            "content_type": props.content_settings.content_type if props.content_settings else None

                        })

                    except Exception:

                        # If we can't get properties, still include the image

                        images.append({

                            "name": relative_name,

                            "full_path": blob.name,

                            "size": None,

                            "last_modified": None,

                            "content_type": None

                        })

        

        # Convert folders dict to list of dicts with creation time, then sort by creation time

        folders_list = [

            {

                "name": folder_name,

                "created_at": folders_dict[folder_name].isoformat() if folders_dict[folder_name] else None

            }

            for folder_name in folders_dict.keys()

        ]

        

        # Sort folders by creation time (newest first, folders without dates go to bottom)

        folders_list.sort(key=lambda x: (

            x["created_at"] if x["created_at"] else "0000-01-01T00:00:00",  # Put no-date folders at bottom

            x["name"]

        ), reverse=True)

        

        return {

            "folder": folder or "",

            "folders": [f["name"] for f in folders_list],  # Return just names for backward compatibility

            "folders_with_metadata": folders_list,  # Include full metadata with creation times

            "images": images,

            "total_folders": len(folders_list),

            "total_images": len(images)

        }

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Failed to list images: {str(e)}")

        raise HTTPException(

            status_code=500,

            detail=f"Failed to list images: {str(e)}"

        )




@router.get(

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





def sanitize_encounter_id(encounter_id: str) -> str:
    """
    Sanitize encounter ID to prevent path traversal attacks.
    
    Ensures the encounter ID only contains safe characters (alphanumeric, hyphens, underscores)
    and prevents any path traversal attempts.
    
    Args:
        encounter_id: The encounter ID from the URL path
        
    Returns:
        Sanitized encounter ID
        
    Raises:
        HTTPException: If encounter ID contains invalid characters or path traversal attempts
    """
    if not encounter_id:
        raise HTTPException(
            status_code=400,
            detail="Encounter ID cannot be empty"
        )
    
    # Check for path traversal attempts
    if ".." in encounter_id or "/" in encounter_id or "\\" in encounter_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid encounter ID: path traversal not allowed"
        )
    
    # Allow only alphanumeric, hyphens, and underscores
    if not all(c.isalnum() or c in "-_" for c in encounter_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid encounter ID: only alphanumeric characters, hyphens, and underscores are allowed"
        )
    
    # Trim whitespace
    encounter_id = encounter_id.strip()
    
    # Check length (reasonable limit)
    if len(encounter_id) == 0:
        raise HTTPException(
            status_code=400,
            detail="Encounter ID cannot be empty"
        )
    
    if len(encounter_id) > 255:
        raise HTTPException(
            status_code=400,
            detail="Encounter ID too long (maximum 255 characters)"
        )
    
    return encounter_id


@router.delete(
    "/images/encounter/{encounter_id}",
    tags=["Images"],
    summary="Delete all images for an encounter",
    description="""
Delete all images stored for a specific encounter ID from Azure Blob Storage.

**Authentication:** Uses HMAC authentication (X-Timestamp and X-Signature headers).

**Path parameter:**
- `encounter_id`: The encounter ID whose images should be deleted

**Returns:** JSON object with deletion summary including count and list of deleted blob names.
    """,
    responses={
        200: {"description": "Images deleted successfully"},
        400: {"description": "Invalid encounter ID"},
        401: {"description": "Authentication required"},
        404: {"description": "No images found for encounter ID"},
        500: {"description": "Deletion failed"},
        503: {"description": "Azure Blob Storage not configured"},
    }
)
async def delete_encounter_images(
    encounter_id: str,
    _auth: TokenData = Depends(get_current_client) if AUTH_ENABLED else Depends(lambda: None)
):
    """
    Delete all images for a specific encounter ID.
    
    This endpoint deletes all blobs (images) stored in the encounters/{encounter_id}/ folder
    from Azure Blob Storage. The folder structure is simulated using blob name prefixes.
    """
    # Check if Azure Blob Storage is available
    if not AZURE_BLOB_AVAILABLE or not container_client:
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage is not configured. Please set AZURE_STORAGE_CONNECTION_STRING environment variable."
        )
    
    # Sanitize encounter ID to prevent path traversal attacks
    try:
        sanitized_encounter_id = sanitize_encounter_id(encounter_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid encounter ID: {str(e)}"
        )
    
    # Build folder prefix
    folder_prefix = f"encounters/{sanitized_encounter_id}/"
    
    try:
        # List all blobs with the prefix
        blob_list = container_client.list_blobs(name_starts_with=folder_prefix)
        
        # Convert generator to list to iterate multiple times if needed
        blobs = list(blob_list)
        
        # Check if any blobs exist
        if not blobs:
            raise HTTPException(
                status_code=404,
                detail=f"No images found for encounter ID: {sanitized_encounter_id}"
            )
        
        # Delete each blob
        deleted_blobs = []
        failed_deletions = []
        
        for blob in blobs:
            try:
                container_client.delete_blob(blob.name)
                deleted_blobs.append(blob.name)
                logger.info(f"Deleted blob: {blob.name}")
            except Exception as e:
                error_msg = f"Failed to delete blob {blob.name}: {str(e)}"
                logger.error(error_msg)
                failed_deletions.append({
                    "blob_name": blob.name,
                    "error": str(e)
                })
        
        # If all deletions failed, return error
        if len(deleted_blobs) == 0 and len(failed_deletions) > 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete images for encounter ID {sanitized_encounter_id}. All deletions failed."
            )
        
        # Build response
        response = {
            "success": True,
            "encounter_id": sanitized_encounter_id,
            "deleted_count": len(deleted_blobs),
            "deleted_blobs": deleted_blobs,
            "message": f"Successfully deleted {len(deleted_blobs)} image(s) for encounter {sanitized_encounter_id}"
        }
        
        # Include failed deletions in response if any
        if failed_deletions:
            response["failed_deletions"] = failed_deletions
            response["failed_count"] = len(failed_deletions)
            response["message"] += f" ({len(failed_deletions)} failed)"
            # If some deletions failed, we still return 200 but with partial success info
            logger.warning(f"Partial deletion: {len(deleted_blobs)} succeeded, {len(failed_deletions)} failed for encounter {sanitized_encounter_id}")
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"Failed to delete images for encounter {sanitized_encounter_id}: {str(e)}")
        
        # Check if it's a 404 error from Azure
        error_msg = str(e).lower()
        if "not found" in error_msg or "404" in error_msg or "does not exist" in error_msg:
            raise HTTPException(
                status_code=404,
                detail=f"No images found for encounter ID: {sanitized_encounter_id}"
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete images for encounter ID {sanitized_encounter_id}: {str(e)}"
        )


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





# @router.get(

    # "/images/",

    # summary="Images Gallery",

    # response_class=HTMLResponse,

    # include_in_schema=False,

    # responses={

        # 200: {

            # "content": {"text/html": {"example": "<!-- Images Gallery UI -->"}},

            # "description": "Images gallery page with folder navigation.",

        # },

        # 303: {"description": "Redirect to login page if not authenticated."},

    # },

# )

# async def images_gallery(

    # request: Request,

    # current_user: dict = Depends(require_auth),

# ):

    # """

    # Render the Images Gallery UI.

    

    # This page provides an interface to:

    # - Browse folders and images in Azure Blob Storage

    # - Navigate through folder hierarchy

    # - View image thumbnails and full-size images

    

    # Requires authentication - users must be logged in to access this page.

    # """

    # response = templates.TemplateResponse(

        # "images_gallery.html",

        # {

            # "request": request,

            # "current_user": current_user,

            # "page_title": "Experity Screenshots",

            # "page_subtitle": "Browse images and folders from Experity",

            # "current_page_id": "images",

        # },

    # )

    # Use no-cache instead of no-store to allow history navigation while preventing stale cache

    # response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"

    # response.headers["Pragma"] = "no-cache"

    # response.headers["Expires"] = "0"

    # return response





# @router.get(

    # "/queue/list",

    # summary="Queue List",

    # response_class=HTMLResponse,

    # include_in_schema=False,

    # responses={

        # 200: {

            # "content": {"text/html": {"example": "<!-- Queue List UI -->"}},

            # "description": "Queue list page showing queue entries with patient names, encounter IDs, and status.",

        # },

        # 303: {"description": "Redirect to login page if not authenticated."},

    # },

# )

# async def queue_list_ui(

    # request: Request,

    # status: Optional[str] = Query(

        # default=None,

        # alias="status",

        # description="Filter by status: PENDING, PROCESSING, DONE, ERROR"

    # ),

    # page: int = Query(

        # default=1,

        # ge=1,

        # alias="page",

        # description="Page number (1-indexed)"

    # ),

    # per_page: int = Query(

        # default=50,

        # ge=1,

        # le=200,

        # alias="per_page",

        # description="Number of records per page (1-200)"

    # ),

    # current_user: dict = Depends(require_auth),

# ):

    # """

    # Render the Queue List UI.

    

    # This page provides an interface to:

    # - View queue entries with patient names and encounter IDs

    # - Filter by status

    # - View verification details for each queue entry

    

    # Requires authentication - users must be logged in to access this page.

    # """

    # conn = None

    # cursor = None

    

    # try:

        # Validate status if provided

        # if status and status not in ['PENDING', 'PROCESSING', 'DONE', 'ERROR']:

            # status = None

        

        # conn = get_db_connection()

        # cursor = conn.cursor(cursor_factory=RealDictCursor)

        

        # Query queue table with LEFT JOIN to patients table to get patient names

        # Patient names are stored in patients table, not in encounter payload

        # Note: We don't join queue_validations here to avoid errors if table doesn't exist

        # Validation existence is checked when the user clicks "View Verification"

        # query = """

            # SELECT 

                # q.queue_id,

                # q.encounter_id,

                # q.emr_id,

                # q.status,

                # q.raw_payload as encounter_payload,

                # q.created_at,

                # TRIM(

                    # CONCAT(

                        # COALESCE(p.legal_first_name, ''), 

                        # ' ', 

                        # COALESCE(p.legal_last_name, '')

                    # )

                # ) as patient_name,

                # COALESCE(

                    # q.raw_payload->>'createdBy',

                    # q.raw_payload->>'created_by'

                # ) as created_by

            # FROM queue q

            # LEFT JOIN patients p ON q.emr_id = p.emr_id

        # """

        # params: List[Any] = []

        

        # Build WHERE clause

        # where_clause = ""

        # if status:

            # where_clause = " WHERE q.status = %s"

            # params.append(status)

        

        # Count total records for pagination

        # count_query = f"SELECT COUNT(*) as total FROM queue q{where_clause}"

        # cursor.execute(count_query, tuple(params))

        # total_count = cursor.fetchone().get('total', 0)

        

        # Calculate pagination

        # total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        # current_page = min(page, total_pages) if total_pages > 0 else 1

        # offset = (current_page - 1) * per_page

        

        # Build main query with pagination

        # query = f"""

            # SELECT 

                # q.queue_id,

                # q.encounter_id,

                # q.emr_id,

                # q.status,

                # q.raw_payload as encounter_payload,

                # q.created_at,

                # TRIM(

                    # CONCAT(

                        # COALESCE(p.legal_first_name, ''), 

                        # ' ', 

                        # COALESCE(p.legal_last_name, '')

                    # )

                # ) as patient_name,

                # COALESCE(

                    # q.raw_payload->>'createdBy',

                    # q.raw_payload->>'created_by'

                # ) as created_by

            # FROM queue q

            # LEFT JOIN patients p ON q.emr_id = p.emr_id

            # {where_clause}

            # ORDER BY q.created_at DESC

            # LIMIT %s OFFSET %s

        # """

        # params.append(per_page)

        # params.append(offset)

        

        # cursor.execute(query, tuple(params))

        # results = cursor.fetchall()

        

        # Get all queue_ids to check for validations

        # queue_ids = [str(r.get('queue_id', '')) for r in results if r.get('queue_id')]

        

        # Check which queue entries have validations

        # has_validation_set = set()

        # if queue_ids:

            # try:

                # Use IN clause with tuple for PostgreSQL

                # placeholders = ','.join(['%s'] * len(queue_ids))

                # cursor.execute(

                    # f"""

                    # SELECT DISTINCT queue_id 

                    # FROM queue_validations 

                    # WHERE queue_id IN ({placeholders})

                    # """,

                    # tuple(queue_ids)

                # )

                # validation_results = cursor.fetchall()

                # has_validation_set = {str(r.get('queue_id')) for r in validation_results if r.get('queue_id')}

            # except Exception as e:

                # If queue_validations table doesn't exist or error, just continue without validation info

                # logger.warning(f"Could not check validation existence: {e}")

        

        # Format the results for template

        # NOTE: Screenshot checking removed from page load for performance

        # Screenshot availability is checked when user clicks "Verify" button

        # This avoids 100+ Azure Blob Storage API calls per page load

        # queue_entries = []

        # for record in results:

            # queue_id = str(record.get('queue_id', ''))

            

            # Get encounter_id as string

            # encounter_id = str(record.get('encounter_id', '')) if record.get('encounter_id') else None

            

            # Get encounter_payload (raw_payload)

            # encounter_payload = record.get('encounter_payload', {})

            # if isinstance(encounter_payload, str):

                # try:

                    # encounter_payload = json.loads(encounter_payload)

                # except json.JSONDecodeError:

                    # encounter_payload = {}

            # elif encounter_payload is None:

                # encounter_payload = {}

            

            # Screenshot checking removed from page load for performance

            # Screenshot availability is checked when user clicks "Verify" button

            # This avoids 100+ Azure Blob Storage API calls per page load

            # has_screenshots = None  # Will be checked on-demand when user clicks Verify

            # screenshot_error = None

            

            # Get patient_name from JOIN result, handling empty strings and NULL

            # patient_name = record.get('patient_name')

            # if patient_name:

                # patient_name = str(patient_name).strip()

                # if not patient_name:

                    # patient_name = None

            # else:

                # patient_name = None

            

            # Get created_by from record, handling NULL and empty strings

            # created_by = record.get('created_by')

            # if created_by:

                # created_by = str(created_by).strip()

                # if not created_by:

                    # created_by = None

            # else:

                # created_by = None

            

            # Format created_at

            # created_at = record.get('created_at')

            # if created_at:

                # if isinstance(created_at, datetime):

                    # created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')

                # else:

                    # created_at = str(created_at)

            

            # Check if this queue entry has validations

            # has_validation = queue_id in has_validation_set

            

            # queue_entries.append({

                # 'queue_id': queue_id,

                # 'encounter_id': encounter_id,

                # 'emr_id': str(record.get('emr_id')) if record.get('emr_id') else None,

                # 'status': record.get('status', 'PENDING'),

                # 'created_at': created_at,

                # 'patient_name': patient_name,

                # 'created_by': created_by,

                # 'encounter_payload': encounter_payload,

                # 'has_validation': has_validation,

                # has_screenshots and screenshot_error removed - checked on-demand when user clicks Verify

            # })

        

        # Calculate pagination metadata

        # has_next = current_page < total_pages

        # has_prev = current_page > 1

        

        # Calculate page numbers to display (5 pages around current)

        # start_page = max(1, current_page - 2)

        # end_page = min(total_pages, current_page + 2)

        # page_numbers = list(range(start_page, end_page + 1))

        

        # response = templates.TemplateResponse(

            # "queue_list.html",

            # {

                # "request": request,

                # "current_user": current_user,

                # "queue_entries": queue_entries,

                # "status_filter": status,

                # "total_count": total_count,

                # "current_page": current_page,  # Integer for pagination

                # "per_page": per_page,

                # "total_pages": total_pages,

                # "has_next": has_next,

                # "has_prev": has_prev,

                # "page_numbers": page_numbers,

                # "start_page": start_page,

                # "end_page": end_page,

                # "page_title": "Encounters",

                # "current_page_id": "encounters",  # String for navigation highlighting

            # },

        # )

        # Use no-cache instead of no-store to allow history navigation while preventing stale cache

        # response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"

        # response.headers["Pragma"] = "no-cache"

        # response.headers["Expires"] = "0"

        # return response

        

    # except Exception as e:

        # logger.error(f"Error rendering queue list: {e}", exc_info=True)

        # raise HTTPException(

            # status_code=500,

            # detail=f"Error loading queue list: {str(e)}"

        # )

    # finally:

        # if cursor:

            # cursor.close()

        # if conn:

            # conn.close()





# @router.get(

    # "/emr/validation",

    # summary="EMR Image Validation",

    # response_class=HTMLResponse,

    # include_in_schema=False,

    # responses={

        # 200: {

            # "content": {"text/html": {"example": "<!-- EMR Image Validation UI -->"}},

            # "description": "EMR image validation tool for comparing JSON responses against screenshots.",

        # },

        # 303: {"description": "Redirect to login page if not authenticated."},

    # },

# )

# async def emr_validation_ui(

    # request: Request,

    # current_user: dict = Depends(require_auth),

# ):

    # """

    # Render the EMR Image Validation UI.

    

    # This page provides an interface to:

    # - Upload EMR screenshots

    # - Paste JSON responses

    # - Validate JSON against screenshots using Azure OpenAI GPT-4o

    # - View validation results with detailed comparisons

    

    # Requires authentication - users must be logged in to access this page.

    # """

    # Hardcoded configuration

    # project_endpoint = "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"

    # agent_name = "ImageMapper"

    

    # response = templates.TemplateResponse(

        # "emr_validation.html",

        # {

            # "request": request,

            # "project_endpoint": project_endpoint,

            # "agent_name": agent_name,

            # "current_user": current_user,

            # "page_title": "EMR Image Validation",

            # "page_subtitle": "Compare JSON response against EMR screenshot",

            # "show_navigation": False,

            # "show_user_menu": False,

        # },

    # )

    # Use no-cache instead of no-store to allow history navigation while preventing stale cache

    # response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"

    # response.headers["Pragma"] = "no-cache"

    # response.headers["Expires"] = "0"

    # return response




@router.get(

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
