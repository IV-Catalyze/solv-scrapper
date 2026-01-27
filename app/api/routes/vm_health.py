"""
VM health routes for monitoring VM worker status.

This module contains all routes related to VM health and heartbeat tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    require_auth,
    TokenData,
    VmHeartbeatRequest,
    VmHeartbeatResponse,
    VmHealthStatusResponse,
    get_db_connection,
    save_vm_health,
    get_latest_vm_health,
)
from app.utils.auth import verify_api_key_auth

router = APIRouter()


async def verify_vm_api_key_auth(request: Request) -> TokenData:
    """
    Verify authentication for VM heartbeat endpoints using X-API-Key header.
    
    This is simpler than HMAC for VM monitoring systems that need to quickly
    send heartbeats without complex signature generation. Uses the same secret
    keys as HMAC authentication for consistency.
    
    Args:
        request: FastAPI request object
        
    Returns:
        TokenData object with client information
        
    Raises:
        HTTPException: If API key authentication fails
    """
    return await verify_api_key_auth(request, "VM heartbeat endpoints", "VM_API_KEY")


@router.post(
    "/vm/heartbeat",
    tags=["VM"],
    summary="Update VM heartbeat",
    description="Receive and process VM heartbeat updates. Updates the VM health record with current status, server ID, UiPath status, and processing queue ID. Uses X-API-Key authentication.",
    response_model=VmHeartbeatResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM heartbeat processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "vmId": "server1-vm1",
                        "serverId": "server1",
                        "lastHeartbeat": "2025-01-22T10:30:00Z",
                        "status": "healthy",
                        "uiPathStatus": "running"
                    }
                }
            }
        },
        400: {"description": "Invalid request data or invalid status value"},
        401: {"description": "X-API-Key header required or invalid"},
        500: {"description": "Server error"},
    },
)
async def vm_heartbeat(
    heartbeat_data: VmHeartbeatRequest,
    request: Request,
    current_client: TokenData = Depends(verify_vm_api_key_auth)
) -> VmHeartbeatResponse:
    """
    Update VM heartbeat status.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key (same key used for other endpoints)
    - Example: `X-API-Key: your-hmac-secret-key`
    - This is simpler than HMAC signature authentication for VM monitoring systems
    
    **Request Body:**
    - `vmId` (required): VM identifier
    - `serverId` (optional): Server identifier
    - `status` (required): VM status: `healthy`, `unhealthy`, or `idle`
    - `processingQueueId` (optional): Queue ID that the VM is currently processing
    - `uiPathStatus` (optional): UiPath status (e.g., "running", "stopped", "error")
    - `metadata` (optional): Metadata object with system metrics (e.g., cpuUsage, memoryUsage, diskUsage)
    
    **Response:**
    Returns the updated VM health record with `success`, `vmId`, `serverId`, `lastHeartbeat`, `status`, and `uiPathStatus`.
    
    **Example Request:**
    ```json
    {
      "vmId": "server1-vm1",
      "serverId": "server1",
      "status": "healthy",
      "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
      "uiPathStatus": "running",
      "metadata": {
        "cpuUsage": 45.2,
        "memoryUsage": 62.8,
        "diskUsage": 30.1
      }
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
            'server_id': heartbeat_data.serverId,
            'status': heartbeat_data.status,
            'processing_queue_id': heartbeat_data.processingQueueId,
            'uipath_status': heartbeat_data.uiPathStatus,
            'metadata': heartbeat_data.metadata,
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
            'serverId': saved_vm_health.get('server_id'),
            'lastHeartbeat': saved_vm_health['last_heartbeat'],
            'status': saved_vm_health['status'],
            'uiPathStatus': saved_vm_health.get('uipath_status'),
        }
        
        # Create response model and serialize with by_alias=False to output camelCase field names
        vm_response = VmHeartbeatResponse(**response_data)
        response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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


@router.get(
    "/vm/health",
    tags=["VM"],
    summary="Get VM health status",
    description="Retrieve the current system health status based on the latest VM heartbeat. System is considered 'up' if a heartbeat was received within the last 2 minutes.",
    response_model=VmHealthStatusResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM health status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "systemStatus": "up",
                        "vmId": "vm-worker-1",
                        "lastHeartbeat": "2025-01-21T10:30:00Z",
                        "status": "healthy",
                        "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_vm_health(
    request: Request,
    current_user: dict = Depends(require_auth)
) -> VmHealthStatusResponse:
    """
    Get the current VM health status.
    
    Returns the latest VM heartbeat information and determines if the system is up or down.
    System is considered 'up' if:
    - A heartbeat exists and was received within the last 2 minutes (120 seconds)
    - The VM status is 'healthy' or 'idle'
    
    System is considered 'down' if:
    - No heartbeat exists
    - The last heartbeat is older than 2 minutes
    - The VM status is 'unhealthy'
    
    **Response:**
    Returns a status object with `systemStatus` ('up' or 'down'), `vmId`, `lastHeartbeat`, `status`, and optional `processingQueueId`.
    """
    conn = None
    
    try:
        # Get database connection
        conn = get_db_connection()
        
        # Get the latest VM health record
        vm_health = get_latest_vm_health(conn)
        
        if not vm_health:
            # No heartbeat exists - system is down
            response_data = {
                'systemStatus': 'down',
                'vmId': None,
                'lastHeartbeat': None,
                'status': None,
                'processingQueueId': None,
            }
            vm_response = VmHealthStatusResponse(**response_data)
            response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
            return JSONResponse(content=response_dict)
        
        # Parse the last heartbeat timestamp
        last_heartbeat = vm_health.get('last_heartbeat')
        if not last_heartbeat:
            # No heartbeat timestamp - system is down
            response_data = {
                'systemStatus': 'down',
                'vmId': vm_health.get('vm_id'),
                'lastHeartbeat': None,
                'status': vm_health.get('status'),
                'processingQueueId': str(vm_health['processing_queue_id']) if vm_health.get('processing_queue_id') else None,
            }
            vm_response = VmHealthStatusResponse(**response_data)
            response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
            return JSONResponse(content=response_dict)
        
        # Parse timestamp - it might be a datetime object or a string
        last_heartbeat_dt = None
        last_heartbeat_str = None
        
        if isinstance(last_heartbeat, datetime):
            last_heartbeat_dt = last_heartbeat
            last_heartbeat_str = last_heartbeat.isoformat() + 'Z'
        elif isinstance(last_heartbeat, str):
            last_heartbeat_str = last_heartbeat
            try:
                # Replace 'Z' with '+00:00' for UTC timezone if present
                timestamp_str = last_heartbeat_str.replace('Z', '+00:00')
                last_heartbeat_dt = datetime.fromisoformat(timestamp_str)
                # If no timezone info, assume UTC
                if last_heartbeat_dt.tzinfo is None:
                    last_heartbeat_dt = last_heartbeat_dt.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError) as e:
                # Invalid timestamp format - consider system down
                response_data = {
                    'systemStatus': 'down',
                    'vmId': vm_health.get('vm_id'),
                    'lastHeartbeat': last_heartbeat_str,
                    'status': vm_health.get('status'),
                    'processingQueueId': str(vm_health['processing_queue_id']) if vm_health.get('processing_queue_id') else None,
                }
                vm_response = VmHealthStatusResponse(**response_data)
                response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
                return JSONResponse(content=response_dict)
        else:
            # Unknown type - consider system down
            response_data = {
                'systemStatus': 'down',
                'vmId': vm_health.get('vm_id'),
                'lastHeartbeat': None,
                'status': vm_health.get('status'),
                'processingQueueId': str(vm_health['processing_queue_id']) if vm_health.get('processing_queue_id') else None,
            }
            vm_response = VmHealthStatusResponse(**response_data)
            response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
            return JSONResponse(content=response_dict)
        
        # Calculate time difference (2 minutes = 120 seconds)
        current_time = datetime.now(timezone.utc)
        # If last_heartbeat_dt doesn't have timezone, assume UTC
        if last_heartbeat_dt.tzinfo is None:
            last_heartbeat_dt = last_heartbeat_dt.replace(tzinfo=timezone.utc)
        time_diff = (current_time - last_heartbeat_dt).total_seconds()
        timeout_threshold = 120  # 2 minutes
        
        vm_status = vm_health.get('status', '').lower()
        
        # Determine system status
        if time_diff > timeout_threshold:
            # Heartbeat is too old - system is down
            system_status = 'down'
        elif vm_status == 'unhealthy':
            # VM status is unhealthy - system is down
            system_status = 'down'
        elif vm_status in ('healthy', 'idle'):
            # Recent heartbeat and healthy/idle status - system is up
            system_status = 'up'
        else:
            # Unknown status - consider down
            system_status = 'down'
        
        # Format the response
        response_data = {
            'systemStatus': system_status,
            'vmId': vm_health.get('vm_id'),
            'lastHeartbeat': last_heartbeat_str,
            'status': vm_health.get('status'),
            'processingQueueId': str(vm_health['processing_queue_id']) if vm_health.get('processing_queue_id') else None,
        }
        
        # Create response model and serialize with by_alias=False to output camelCase field names
        vm_response = VmHealthStatusResponse(**response_data)
        response_dict = vm_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
        if conn:
            conn.close()

