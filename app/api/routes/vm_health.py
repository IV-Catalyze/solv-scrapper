"""
VM health routes for monitoring VM worker status.

This module contains all routes related to VM health and heartbeat tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends, Query
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
from app.api.database import get_vm_health_by_vm_id, get_all_vms_health, update_vm_health_partial
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
    return await verify_api_key_auth(request, "VM heartbeat endpoints", "API_KEY")


@router.get(
    "/vm/health/list",
    tags=["VM"],
    summary="List all VM health statuses",
    description=(
        "Retrieve health status for all VMs. "
        "Returns VM metrics, status, workflow information, and processing queue details for each VM. "
        "Supports optional filtering by status and serverId. Uses X-API-Key authentication."
    ),
    response_model=List[VmHealthStatusResponse],
    status_code=200,
    responses={
        200: {
            "description": "VM health statuses retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "systemStatus": "up",
                            "vmId": "server1-vm1",
                            "lastHeartbeat": "2025-01-22T10:30:00Z",
                            "status": "healthy",
                            "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
                            "serverId": "server1",
                            "workflowStatus": "running",
                            "metadata": {
                                "cpuUsage": 45.2,
                                "memoryUsage": 62.8,
                                "diskUsage": 30.1
                            }
                        }
                    ]
                }
            }
        },
        400: {"description": "Invalid query parameters"},
        401: {"description": "X-API-Key header required or invalid"},
        500: {"description": "Server error"},
    },
)
async def list_vm_health(
    status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by VM status (healthy, unhealthy, idle)"
    ),
    serverId: Optional[str] = Query(
        None,
        alias="serverId",
        description="Filter by server identifier"
    ),
    current_client: TokenData = Depends(verify_vm_api_key_auth),
) -> List[VmHealthStatusResponse]:
    """
    Get health status for all VMs.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key (same key used for other endpoints)
    - Example: `X-API-Key: your-hmac-secret-key`
    
    **Query Parameters:**
    - `status` (optional): Filter by VM status - 'healthy', 'unhealthy', or 'idle'
    - `serverId` (optional): Filter by server identifier
    
    **Response:**
    Returns a list of VM health information. Each VM includes:
    - VM ID, server ID, status, and last heartbeat
    - System status (up/down) calculated based on heartbeat recency and status
    - Workflow status and processing queue ID
    - Metadata with resource metrics (CPU, memory, disk usage)
    
    **Example:**
    ```
    GET /vm/health/list
    GET /vm/health/list?status=healthy
    GET /vm/health/list?serverId=server1
    GET /vm/health/list?status=healthy&serverId=server1
    ```
    
    **Example Response:**
    ```json
    [
      {
        "systemStatus": "up",
        "vmId": "server1-vm1",
        "lastHeartbeat": "2025-01-22T10:30:00Z",
        "status": "healthy",
        "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
        "serverId": "server1",
        "workflowStatus": "running",
        "metadata": {
          "cpuUsage": 45.2,
          "memoryUsage": 62.8,
          "diskUsage": 30.1
        }
      }
    ]
    ```
    """
    conn = None
    
    try:
        # Validate status parameter if provided
        if status:
            valid_statuses = ['healthy', 'unhealthy', 'idle']
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}"
                )
        
        # Get database connection
        conn = get_db_connection()
        
        # Get all VMs (with optional filtering)
        vms = get_all_vms_health(conn, server_id=serverId, status=status)
        
        # Build response list
        vm_list = []
        current_time = datetime.now(timezone.utc)
        timeout_threshold = 120  # 2 minutes
        
        for vm in vms:
            # Parse the last heartbeat timestamp
            last_heartbeat = vm.get('last_heartbeat')
            last_heartbeat_str = None
            last_heartbeat_dt = None
            
            if last_heartbeat:
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
                    except (ValueError, AttributeError):
                        last_heartbeat_dt = None
            
            # Calculate system status
            system_status = 'down'
            if last_heartbeat_dt:
                # If last_heartbeat_dt doesn't have timezone, assume UTC
                if last_heartbeat_dt.tzinfo is None:
                    last_heartbeat_dt = last_heartbeat_dt.replace(tzinfo=timezone.utc)
                time_diff = (current_time - last_heartbeat_dt).total_seconds()
                
                vm_status = vm.get('status', '').lower()
                
                if time_diff > timeout_threshold:
                    system_status = 'down'
                elif vm_status == 'unhealthy':
                    system_status = 'down'
                elif vm_status in ('healthy', 'idle'):
                    system_status = 'up'
                else:
                    system_status = 'down'
            elif vm.get('status'):
                # No heartbeat but has status - consider down
                system_status = 'down'
            
            # Build response data
            response_data = {
                'systemStatus': system_status,
                'vmId': vm.get('vm_id'),
                'lastHeartbeat': last_heartbeat_str,
                'status': vm.get('status'),
                'processingQueueId': str(vm['processing_queue_id']) if vm.get('processing_queue_id') else None,
                'serverId': vm.get('server_id'),
                'workflowStatus': vm.get('workflow_status'),
                'metadata': vm.get('metadata'),
            }
            
            # Create response model
            vm_response = VmHealthStatusResponse(**response_data)
            vm_list.append(vm_response)
        
        # Convert to list of dicts with camelCase keys
        response_list = [
            vm.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
            for vm in vm_list
        ]
        
        logger.info(f"Successfully retrieved health for {len(vm_list)} VM(s)")
        return JSONResponse(content=response_list, status_code=200)
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error retrieving VM health list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error retrieving VM health list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.post(
    "/vm/heartbeat",
    tags=["VM"],
    summary="Update VM heartbeat",
    description="Receive and process VM heartbeat updates. Updates the VM health record with current status, server ID, AI Agent Workflow status, and processing queue ID. Uses X-API-Key authentication.",
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
                        "workflowStatus": "running"
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
    - `workflowStatus` (optional): AI Agent Workflow status (e.g., "running", "stopped", "error")
    - `metadata` (optional): Metadata object with system metrics (e.g., cpuUsage, memoryUsage, diskUsage)
    
    **Response:**
    Returns the updated VM health record with `success`, `vmId`, `serverId`, `lastHeartbeat`, `status`, and `workflowStatus`.
    
    **Example Request:**
    ```json
    {
      "vmId": "server1-vm1",
      "serverId": "server1",
      "status": "healthy",
      "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
      "workflowStatus": "running",
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
            'workflow_status': heartbeat_data.workflowStatus,
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
            'workflowStatus': saved_vm_health.get('workflow_status'),
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


@router.patch(
    "/vm/health/{vmId}",
    tags=["VM"],
    summary="Partially update VM health",
    description=(
        "Partially update a VM health record. Only provided fields will be updated. "
        "The VM must exist (returns 404 if not found). "
        "Uses X-API-Key authentication."
    ),
    response_model=VmHeartbeatResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM health updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "vmId": "server1-vm1",
                        "serverId": "server1",
                        "lastHeartbeat": "2025-01-22T10:30:00Z",
                        "status": "healthy",
                        "workflowStatus": "running"
                    }
                }
            }
        },
        400: {"description": "Invalid request data or invalid status value"},
        401: {"description": "X-API-Key header required or invalid"},
        404: {"description": "VM not found"},
        500: {"description": "Server error"},
    },
)
async def patch_vm_health(
    vmId: str,
    update_data: Dict[str, Any],
    request: Request,
    current_client: TokenData = Depends(verify_vm_api_key_auth)
) -> VmHeartbeatResponse:
    """
    Partially update VM heartbeat status.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key
    - Example: `X-API-Key: your-hmac-secret-key`
    
    **Request Body (all fields optional):**
    - `serverId` (optional): Server identifier
    - `status` (optional): VM status: `healthy`, `unhealthy`, or `idle`
    - `processingQueueId` (optional): Queue ID that the VM is currently processing
    - `workflowStatus` (optional): AI Agent Workflow status (e.g., "running", "stopped", "error")
    - `metadata` (optional): Metadata object with system metrics (e.g., cpuUsage, memoryUsage, diskUsage)
    
    **Response:**
    Returns the updated VM health record with `success`, `vmId`, `serverId`, `lastHeartbeat`, `status`, and `workflowStatus`.
    
    **Note:** The VM must already exist. This endpoint will not create new records.
    
    **Example Request:**
    ```json
    {
      "status": "healthy",
      "workflowStatus": "running",
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
        # Check if VM exists
        conn = get_db_connection()
        existing_vm = get_vm_health_by_vm_id(conn, vmId)
        
        if not existing_vm:
            raise HTTPException(
                status_code=404,
                detail=f"VM with ID '{vmId}' not found."
            )
        
        # Validate status if provided
        if "status" in update_data and update_data["status"]:
            valid_statuses = ['healthy', 'unhealthy', 'idle']
            if update_data["status"] not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {update_data['status']}. Must be one of: {', '.join(valid_statuses)}"
                )
        
        # Prepare update data - only include fields that are provided
        vm_health_dict = {
            'vm_id': vmId,
        }
        
        # Use provided values or keep existing ones
        vm_health_dict['server_id'] = update_data.get('serverId') if 'serverId' in update_data else existing_vm.get('server_id')
        vm_health_dict['status'] = update_data.get('status') if 'status' in update_data else existing_vm.get('status')
        vm_health_dict['processing_queue_id'] = update_data.get('processingQueueId') if 'processingQueueId' in update_data else existing_vm.get('processing_queue_id')
        vm_health_dict['workflow_status'] = update_data.get('workflowStatus') if 'workflowStatus' in update_data else existing_vm.get('workflow_status')
        vm_health_dict['metadata'] = update_data.get('metadata') if 'metadata' in update_data else existing_vm.get('metadata')
        
        # Update the VM health record (partial update)
        saved_vm_health = update_vm_health_partial(conn, vm_health_dict)
        
        # Format the response
        response_data = {
            'success': True,
            'vmId': saved_vm_health['vm_id'],
            'serverId': saved_vm_health.get('server_id'),
            'lastHeartbeat': saved_vm_health['last_heartbeat'],
            'status': saved_vm_health['status'],
            'workflowStatus': saved_vm_health.get('workflow_status'),
        }
        
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
    summary="Get latest VM health status",
    description=(
        "Retrieve the current system health status based on the latest VM heartbeat. "
        "System is considered 'up' if a heartbeat was received within the last 2 minutes "
        "and the VM status is 'healthy' or 'idle'."
    ),
    response_model=VmHealthStatusResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM health status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "systemStatus": "up",
                        "vmId": "server1-vm1",
                        "lastHeartbeat": "2025-01-21T10:30:00Z",
                        "status": "healthy",
                        "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
                        "serverId": "server1",
                        "workflowStatus": "running",
                        "metadata": {
                            "cpuUsage": 45.2,
                            "memoryUsage": 62.8,
                            "diskUsage": 30.1
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_latest_vm_health_status(
    request: Request,
    current_user: dict = Depends(require_auth)
) -> VmHealthStatusResponse:
    """
    Get the current VM health status based on the latest heartbeat.
    
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
                'serverId': None,
                'workflowStatus': None,
                'metadata': None,
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
                'serverId': vm_health.get('server_id'),
                'workflowStatus': vm_health.get('workflow_status'),
                'metadata': vm_health.get('metadata'),
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
                    'serverId': vm_health.get('server_id'),
                    'workflowStatus': vm_health.get('workflow_status'),
                    'metadata': vm_health.get('metadata'),
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
                'serverId': vm_health.get('server_id'),
                'workflowStatus': vm_health.get('workflow_status'),
                'metadata': vm_health.get('metadata'),
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
            'serverId': vm_health.get('server_id'),
            'workflowStatus': vm_health.get('workflow_status'),
            'metadata': vm_health.get('metadata'),
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


@router.get(
    "/vm/health/{vmId}",
    tags=["VM"],
    summary="Get VM health status by VM ID",
    description=(
        "Retrieve the health status for a specific VM based on its latest heartbeat. "
        "System is considered 'up' if a heartbeat was received within the last 2 minutes "
        "and the VM status is 'healthy' or 'idle'."
    ),
    response_model=VmHealthStatusResponse,
    status_code=200,
    responses={
        200: {
            "description": "VM health status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "systemStatus": "up",
                        "vmId": "server1-vm1",
                        "lastHeartbeat": "2025-01-21T10:30:00Z",
                        "status": "healthy",
                        "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
                        "serverId": "server1",
                        "workflowStatus": "running",
                        "metadata": {
                            "cpuUsage": 45.2,
                            "memoryUsage": 62.8,
                            "diskUsage": 30.1
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_vm_health(
    vmId: str,
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
        
        # Get the VM health record for the specified vmId
        vm_health = get_vm_health_by_vm_id(conn, vmId)
        
        if not vm_health:
            # No heartbeat exists for this VM - system is down for this VM
            response_data = {
                'systemStatus': 'down',
                'vmId': vmId,
                'lastHeartbeat': None,
                'status': None,
                'processingQueueId': None,
                'serverId': None,
                'workflowStatus': None,
                'metadata': None,
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
                'serverId': vm_health.get('server_id'),
                'workflowStatus': vm_health.get('workflow_status'),
                'metadata': vm_health.get('metadata'),
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
                    'serverId': vm_health.get('server_id'),
                    'workflowStatus': vm_health.get('workflow_status'),
                    'metadata': vm_health.get('metadata'),
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
                'serverId': vm_health.get('server_id'),
                'workflowStatus': vm_health.get('workflow_status'),
                'metadata': vm_health.get('metadata'),
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
            'serverId': vm_health.get('server_id'),
            'workflowStatus': vm_health.get('workflow_status'),
            'metadata': vm_health.get('metadata'),
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


