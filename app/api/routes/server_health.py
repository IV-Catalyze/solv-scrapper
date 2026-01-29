"""
Server health routes for monitoring server status.

This module contains routes related to server health and heartbeat tracking.
"""

from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import psycopg2

from app.api.routes.dependencies import (
    logger,
    TokenData,
    get_db_connection,
)
from app.api.models import (
    ServerHeartbeatRequest,
    ServerHeartbeatResponse,
    ServerHealthResponse,
    VmInfo,
)
from app.api.database import (
    save_server_health,
    get_server_health_by_server_id,
    get_vms_by_server_id,
)
from app.utils.auth import verify_api_key_auth

router = APIRouter()


async def verify_server_api_key_auth(request: Request) -> TokenData:
    """
    Verify authentication for server heartbeat endpoints using X-API-Key header.

    This is simpler than HMAC for server monitoring systems that need to quickly
    send heartbeats without complex signature generation. Uses the same secret
    keys as HMAC authentication for consistency.

    Args:
        request: FastAPI request object

    Returns:
        TokenData object with client information

    Raises:
        HTTPException: If API key authentication fails
    """
    return await verify_api_key_auth(request, "server heartbeat endpoints", "API_KEY")


@router.post(
    "/server/heartbeat",
    tags=["Server"],
    summary="Update server heartbeat",
    description=(
        "Receive and process server heartbeat updates with resource metrics. "
        "Updates the server health record with current status and system metrics. "
        "Uses X-API-Key authentication."
    ),
    response_model=ServerHeartbeatResponse,
    status_code=201,
    responses={
        201: {
            "description": "Server heartbeat processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "serverId": "server1",
                        "status": "healthy",
                        "lastHeartbeat": "2025-01-22T10:30:00Z",
                        "metadata": {
                            "cpuUsage": 45.2,
                            "memoryUsage": 62.8,
                            "diskUsage": 30.1,
                        },
                    }
                }
            },
        },
        400: {"description": "Invalid request data or invalid status value"},
        401: {"description": "X-API-Key header required or invalid"},
        500: {"description": "Server error"},
    },
)
async def server_heartbeat(
    heartbeat_data: ServerHeartbeatRequest,
    request: Request,
    current_client: TokenData = Depends(verify_server_api_key_auth),
) -> ServerHeartbeatResponse:
    """
    Update server heartbeat status with resource metrics.

    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key (same key used for other endpoints)
    - Example: `X-API-Key: your-hmac-secret-key`
    - This is simpler than HMAC signature authentication for server monitoring systems

    **Request Body:**
    - `serverId` (required): Server identifier
    - `status` (required): Server status: `healthy`, `unhealthy`, or `down`
    - `metadata` (optional): Metadata object with system metrics
      (e.g., cpuUsage, memoryUsage, diskUsage)

    **Response:**
    Returns the updated server health record with `serverId`, `status`,
    `lastHeartbeat`, and `metadata`.
    """
    conn = None

    try:
        # Validate required fields
        if not heartbeat_data.serverId:
            raise HTTPException(
                status_code=400,
                detail="serverId is required. Please provide a server identifier.",
            )

        if not heartbeat_data.status:
            raise HTTPException(
                status_code=400,
                detail="status is required. Please provide a server status.",
            )

        # Validate status
        valid_statuses = ["healthy", "unhealthy", "down"]
        if heartbeat_data.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status: {heartbeat_data.status}. "
                    f"Must be one of: {', '.join(valid_statuses)}"
                ),
            )

        # Prepare server health data
        server_health_dict: Dict[str, Any] = {
            "server_id": heartbeat_data.serverId,
            "status": heartbeat_data.status,
            "metadata": heartbeat_data.metadata,
        }

        # Get database connection
        conn = get_db_connection()

        # Save/update the server health record
        saved_server_health = save_server_health(conn, server_health_dict)

        # Format the response - pass data using field names (camelCase)
        # The model will accept both field names and aliases due to
        # populate_by_name=True
        response_data: Dict[str, Any] = {
            "serverId": saved_server_health["server_id"],
            "status": saved_server_health["status"],
            "lastHeartbeat": saved_server_health["last_heartbeat"],
            "metadata": saved_server_health.get("metadata"),
        }

        # Create response model and serialize with by_alias=False
        # to output camelCase field names
        server_response = ServerHeartbeatResponse(**response_data)
        response_dict = server_response.model_dump(
            exclude_none=True, exclude_unset=True, by_alias=False
        )

        return JSONResponse(content=response_dict, status_code=201)

    except HTTPException:
        raise
    except ValueError as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get(
    "/server/health/{serverId}",
    tags=["Server"],
    summary="Get server health status with VM details",
    description=(
        "Retrieve the health status for a specific server including all associated VMs. "
        "Returns server metrics, VM counts, and detailed VM information. "
        "Uses X-API-Key authentication."
    ),
    response_model=ServerHealthResponse,
    status_code=200,
    responses={
        200: {
            "description": "Server health status retrieved successfully",
        },
        404: {"description": "Server not found"},
        401: {"description": "X-API-Key header required or invalid"},
        500: {"description": "Server error"},
    },
)
async def get_server_health(
    serverId: str,
    request: Request,
    current_client: TokenData = Depends(verify_server_api_key_auth),
) -> ServerHealthResponse:
    """
    Get the current server health status with VM details.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key (same key used for other endpoints)
    - Example: `X-API-Key: your-hmac-secret-key`
    
    **Path Parameters:**
    - `serverId`: Server identifier (e.g., "server1")
    
    **Response:**
    Returns comprehensive server health information including:
    - Server status and last heartbeat
    - Resource metrics (CPU, memory, disk usage) extracted from metadata
    - VM counts (total and healthy)
    - List of all VMs on the server with their status
    
    **Example Response:**
    ```json
    {
      "serverId": "server1",
      "status": "healthy",
      "lastHeartbeat": "2025-01-22T10:30:00Z",
      "cpuUsage": 45.2,
      "memoryUsage": 62.8,
      "diskUsage": 30.1,
      "vmCount": 8,
      "healthyVmCount": 8,
      "vms": [
        {
          "vmId": "server1-vm1",
          "status": "healthy",
          "lastHeartbeat": "2025-01-22T10:30:00Z",
          "uiPathStatus": "running",
          "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
        }
      ]
    }
    ```
    """
    conn = None
    
    try:
        # Validate serverId input
        if not serverId or not serverId.strip():
            raise HTTPException(
                status_code=400,
                detail="serverId is required and cannot be empty"
            )
        
        # Sanitize serverId (remove leading/trailing whitespace)
        serverId = serverId.strip()
        
        # Get database connection
        conn = get_db_connection()
        
        # Get server health record
        server_health = get_server_health_by_server_id(conn, serverId)
        
        if not server_health:
            logger.warning(f"Server health not found for serverId: {serverId}")
            raise HTTPException(
                status_code=404,
                detail=f"Server '{serverId}' not found"
            )
        
        # Get all VMs for this server
        vms = get_vms_by_server_id(conn, serverId)
        
        # Extract metadata fields (cpuUsage, memoryUsage, diskUsage)
        metadata = server_health.get('metadata') or {}
        cpu_usage = metadata.get('cpuUsage') if isinstance(metadata, dict) else None
        memory_usage = metadata.get('memoryUsage') if isinstance(metadata, dict) else None
        disk_usage = metadata.get('diskUsage') if isinstance(metadata, dict) else None
        
        # Calculate VM counts
        vm_count = len(vms)
        healthy_vm_count = sum(1 for vm in vms if vm.get('status') == 'healthy')
        
        # Format VM list
        vm_list = []
        for vm in vms:
            vm_info = {
                'vmId': vm.get('vm_id'),
                'status': vm.get('status'),
                'lastHeartbeat': vm.get('last_heartbeat'),
                'uiPathStatus': vm.get('uipath_status'),
                'processingQueueId': str(vm['processing_queue_id']) if vm.get('processing_queue_id') else None,
            }
            vm_list.append(vm_info)
        
        # Build response
        response_data = {
            'serverId': server_health.get('server_id'),
            'status': server_health.get('status'),
            'lastHeartbeat': server_health.get('last_heartbeat'),
            'cpuUsage': cpu_usage,
            'memoryUsage': memory_usage,
            'diskUsage': disk_usage,
            'vmCount': vm_count,
            'healthyVmCount': healthy_vm_count,
            'vms': vm_list,
        }
        
        # Create response model
        server_response = ServerHealthResponse(**response_data)
        response_dict = server_response.model_dump(
            exclude_none=True, exclude_unset=True, by_alias=False
        )
        
        logger.info(f"Successfully retrieved server health for serverId: {serverId} (VMs: {vm_count}, Healthy: {healthy_vm_count})")
        return JSONResponse(content=response_dict, status_code=200)
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error retrieving server health for serverId {serverId}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error retrieving server health for serverId {serverId}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

