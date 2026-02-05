"""
Server health routes for monitoring server status.

This module contains routes related to server health and heartbeat tracking.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import JSONResponse
import psycopg2

from app.api.routes.dependencies import (
    logger,
    TokenData,
    get_db_connection,
    require_auth,
)
from app.api.models import (
    ServerHeartbeatRequest,
    ServerHeartbeatResponse,
    ServerHealthResponse,
    VmInfo,
    HealthDashboardResponse,
    DashboardServerInfo,
    DashboardVmInfo,
    DashboardStatistics,
)
from app.utils.resource_alerts import process_resource_alerts
from app.api.database import (
    save_server_health,
    get_server_health_by_server_id,
    get_vms_by_server_id,
    get_all_servers_health,
    get_all_vms_health,
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

        # Check resource thresholds and create/resolve alerts if needed
        try:
            metadata = heartbeat_data.metadata
            if metadata:
                alert_results = process_resource_alerts(
                    conn,
                    heartbeat_data.serverId,
                    metadata
                )
                if alert_results['created'] > 0 or alert_results['resolved'] > 0:
                    logger.info(
                        f"Resource alerts processed for {heartbeat_data.serverId}: "
                        f"created={alert_results['created']}, "
                        f"resolved={alert_results['resolved']}"
                    )
        except Exception as e:
            # Log but don't fail the heartbeat if alert processing fails
            logger.warning(
                f"Failed to process resource alerts for {heartbeat_data.serverId}: {str(e)}"
            )

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
          "workflowStatus": "running",
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
                'workflowStatus': vm.get('workflow_status'),
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


@router.get(
    "/server/health",
    tags=["Server"],
    summary="List all server health statuses with VM details",
    description=(
        "Retrieve health status for all servers including all associated VMs. "
        "Returns server metrics, VM counts, and detailed VM information for each server. "
        "Supports optional filtering by status. Uses X-API-Key authentication."
    ),
    response_model=List[ServerHealthResponse],
    status_code=200,
    responses={
        200: {
            "description": "Server health statuses retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
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
                                    "workflowStatus": "running",
                                    "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
                                }
                            ]
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
async def list_server_health(
    status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by server status (healthy, unhealthy, down)"
    ),
    current_client: TokenData = Depends(verify_server_api_key_auth),
) -> List[ServerHealthResponse]:
    """
    Get health status for all servers with VM details.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key (same key used for other endpoints)
    - Example: `X-API-Key: your-hmac-secret-key`
    
    **Query Parameters:**
    - `status` (optional): Filter by server status - 'healthy', 'unhealthy', or 'down'
    
    **Response:**
    Returns a list of server health information. Each server includes:
    - Server status and last heartbeat
    - Resource metrics (CPU, memory, disk usage) extracted from metadata
    - VM counts (total and healthy)
    - List of all VMs on the server with their status
    
    **Example:**
    ```
    GET /server/health
    GET /server/health?status=healthy
    GET /server/health?status=unhealthy
    ```
    
    **Example Response:**
    ```json
    [
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
            "workflowStatus": "running",
            "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
          }
        ]
      }
    ]
    ```
    """
    conn = None
    
    try:
        # Validate status parameter if provided
        if status:
            valid_statuses = ['healthy', 'unhealthy', 'down']
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}"
                )
        
        # Get database connection
        conn = get_db_connection()
        
        # Get all servers (with optional filtering by status)
        servers = get_all_servers_health(conn, status=status)
        
        # Build response list
        server_list = []
        for server in servers:
            server_id = server.get('server_id')
            
            # Get all VMs for this server
            vms = get_vms_by_server_id(conn, server_id)
            
            # Extract metadata fields (cpuUsage, memoryUsage, diskUsage)
            metadata = server.get('metadata') or {}
            cpu_usage = metadata.get('cpuUsage') if isinstance(metadata, dict) else None
            memory_usage = metadata.get('memoryUsage') if isinstance(metadata, dict) else None
            disk_usage = metadata.get('diskUsage') if isinstance(metadata, dict) else None
            
            # Calculate VM counts
            vm_count = len(vms)
            healthy_vm_count = sum(1 for vm in vms if vm.get('status') == 'healthy')
            
            # Format VM list
            vm_list: List[VmInfo] = []
            for vm in vms:
                last_heartbeat = vm.get('last_heartbeat')
                if isinstance(last_heartbeat, datetime):
                    last_heartbeat_str = last_heartbeat.isoformat() + 'Z'
                else:
                    last_heartbeat_str = last_heartbeat
                
                vm_info = {
                    'vmId': vm.get('vm_id'),
                    'status': vm.get('status'),
                    'lastHeartbeat': last_heartbeat_str,
                    'workflowStatus': vm.get('workflow_status'),
                    'processingQueueId': str(vm['processing_queue_id']) if vm.get('processing_queue_id') else None,
                }
                vm_list.append(VmInfo(**vm_info))
            
            # Format server last heartbeat
            server_last_heartbeat = server.get('last_heartbeat')
            if isinstance(server_last_heartbeat, datetime):
                server_last_heartbeat_str = server_last_heartbeat.isoformat() + 'Z'
            else:
                server_last_heartbeat_str = server_last_heartbeat
            
            # Build response data
            response_data = {
                'serverId': server.get('server_id'),
                'status': server.get('status'),
                'lastHeartbeat': server_last_heartbeat_str,
                'cpuUsage': cpu_usage,
                'memoryUsage': memory_usage,
                'diskUsage': disk_usage,
                'vmCount': vm_count,
                'healthyVmCount': healthy_vm_count,
                'vms': vm_list,
            }
            
            # Create response model
            server_response = ServerHealthResponse(**response_data)
            server_list.append(server_response)
        
        # Convert to list of dicts with camelCase keys
        response_list = [
            server.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
            for server in server_list
        ]
        
        logger.info(f"Successfully retrieved health for {len(server_list)} server(s)")
        return JSONResponse(content=response_list, status_code=200)
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error retrieving server health list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error retrieving server health list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get(
    "/health/dashboard",
    tags=["Server"],
    summary="Get comprehensive health dashboard",
    description=(
        "Retrieve comprehensive health status for all servers, VMs, and AI Agent Workflow processes. "
        "Supports filtering by serverId and status. Uses session-based authentication."
    ),
    response_model=HealthDashboardResponse,
    status_code=200,
    responses={
        200: {
            "description": "Health dashboard retrieved successfully",
        },
        400: {"description": "Invalid query parameters"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_health_dashboard(
    serverId: Optional[str] = Query(
        None,
        alias="serverId",
        description="Filter by specific server identifier"
    ),
    status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (healthy, unhealthy, idle, down)"
    ),
    current_user: dict = Depends(require_auth)
) -> HealthDashboardResponse:
    """
    Get comprehensive health dashboard for all servers and VMs.
    
    **Authentication:**
    - Session-based authentication required (same as UI endpoints)
    
    **Query Parameters:**
    - `serverId` (optional): Filter by specific server identifier
    - `status` (optional): Filter by status - 'healthy', 'unhealthy', 'idle', or 'down'
      - For servers: healthy, unhealthy, down
      - For VMs: healthy, unhealthy, idle
    
    **Response:**
    Returns comprehensive health information including:
    - Overall system status
    - List of all servers with their VMs
    - System-wide statistics
    
    **Example:**
    ```
    GET /health/dashboard
    GET /health/dashboard?serverId=server1
    GET /health/dashboard?status=healthy
    GET /health/dashboard?serverId=server1&status=healthy
    ```
    """
    conn = None
    
    try:
        # Validate status parameter if provided
        if status:
            valid_statuses = ['healthy', 'unhealthy', 'idle', 'down']
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}"
                )
        
        # Get database connection
        conn = get_db_connection()
        
        # Get all servers (with optional filtering)
        server_status_filter = status if status in ['healthy', 'unhealthy', 'down'] else None
        servers = get_all_servers_health(conn, server_id=serverId, status=server_status_filter)
        
        # Get all VMs (with optional filtering)
        vm_status_filter = status if status in ['healthy', 'unhealthy', 'idle'] else None
        all_vms = get_all_vms_health(conn, server_id=serverId, status=vm_status_filter)
        
        # Group VMs by server_id
        vms_by_server: Dict[str, List[Dict[str, Any]]] = {}
        for vm in all_vms:
            vm_server_id = vm.get('server_id')
            if vm_server_id:
                if vm_server_id not in vms_by_server:
                    vms_by_server[vm_server_id] = []
                vms_by_server[vm_server_id].append(vm)
        
        # Build server list with VMs
        server_list = []
        for server in servers:
            server_id = server.get('server_id')
            
            # Get VMs for this server
            server_vms = vms_by_server.get(server_id, [])
            
            # Extract metadata fields
            metadata = server.get('metadata') or {}
            cpu_usage = metadata.get('cpuUsage') if isinstance(metadata, dict) else None
            memory_usage = metadata.get('memoryUsage') if isinstance(metadata, dict) else None
            disk_usage = metadata.get('diskUsage') if isinstance(metadata, dict) else None
            
            # Calculate VM counts for this server
            vm_count = len(server_vms)
            healthy_vm_count = sum(1 for vm in server_vms if vm.get('status') == 'healthy')
            
            # Format VM list
            vm_list = []
            for vm in server_vms:
                vm_info = {
                    'vmId': vm.get('vm_id'),
                    'status': vm.get('status'),
                    'lastHeartbeat': vm.get('last_heartbeat'),
                    'workflowStatus': vm.get('workflow_status'),
                    'processingQueueId': str(vm['processing_queue_id']) if vm.get('processing_queue_id') else None,
                    'metadata': vm.get('metadata'),
                }
                vm_list.append(DashboardVmInfo(**vm_info))
            
            # Build server info
            server_info = {
                'serverId': server.get('server_id'),
                'status': server.get('status'),
                'lastHeartbeat': server.get('last_heartbeat'),
                'cpuUsage': cpu_usage,
                'memoryUsage': memory_usage,
                'diskUsage': disk_usage,
                'vmCount': vm_count,
                'healthyVmCount': healthy_vm_count,
                'vms': vm_list,
            }
            server_list.append(DashboardServerInfo(**server_info))
        
        # Calculate statistics (use all data, not filtered)
        all_servers_for_stats = get_all_servers_health(conn)
        all_vms_for_stats = get_all_vms_health(conn)
        
        # Server statistics
        total_servers = len(all_servers_for_stats)
        healthy_servers = sum(1 for s in all_servers_for_stats if s.get('status') == 'healthy')
        unhealthy_servers = sum(1 for s in all_servers_for_stats if s.get('status') == 'unhealthy')
        down_servers = sum(1 for s in all_servers_for_stats if s.get('status') == 'down')
        
        # VM statistics
        total_vms = len(all_vms_for_stats)
        healthy_vms = sum(1 for v in all_vms_for_stats if v.get('status') == 'healthy')
        unhealthy_vms = sum(1 for v in all_vms_for_stats if v.get('status') == 'unhealthy')
        idle_vms = sum(1 for v in all_vms_for_stats if v.get('status') == 'idle')
        vms_processing = sum(1 for v in all_vms_for_stats if v.get('processing_queue_id') is not None)
        vms_with_workflow_running = sum(1 for v in all_vms_for_stats if v.get('workflow_status') == 'running')
        vms_with_workflow_stopped = sum(1 for v in all_vms_for_stats if v.get('workflow_status') == 'stopped')
        
        # Determine overall status
        # Priority: down > unhealthy > degraded > healthy
        if down_servers > 0 or unhealthy_servers > 0:
            overall_status = "unhealthy"
        elif unhealthy_vms > 0:
            overall_status = "degraded"
        elif idle_vms > 0 and healthy_vms > 0:
            overall_status = "healthy"  # Some VMs idle is normal
        elif healthy_servers == total_servers and healthy_vms == total_vms:
            overall_status = "healthy"
        else:
            overall_status = "healthy"  # Default to healthy
        
        # Build statistics
        statistics = DashboardStatistics(
            totalServers=total_servers,
            healthyServers=healthy_servers,
            unhealthyServers=unhealthy_servers,
            downServers=down_servers,
            totalVms=total_vms,
            healthyVms=healthy_vms,
            unhealthyVms=unhealthy_vms,
            idleVms=idle_vms,
            vmsProcessing=vms_processing,
            vmsWithWorkflowRunning=vms_with_workflow_running,
            vmsWithWorkflowStopped=vms_with_workflow_stopped,
        )
        
        # Build response
        response_data = {
            'overallStatus': overall_status,
            'lastUpdated': datetime.now(timezone.utc).isoformat() + 'Z',
            'servers': server_list,
            'statistics': statistics,
        }
        
        dashboard_response = HealthDashboardResponse(**response_data)
        response_dict = dashboard_response.model_dump(
            exclude_none=True, exclude_unset=True, by_alias=False
        )
        
        logger.info(f"Health dashboard retrieved: {total_servers} servers, {total_vms} VMs, status: {overall_status}")
        return JSONResponse(content=response_dict, status_code=200)
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error retrieving health dashboard: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error retrieving health dashboard: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

