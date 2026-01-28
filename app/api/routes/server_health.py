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
from app.api.models import ServerHeartbeatRequest, ServerHeartbeatResponse
from app.api.database import save_server_health
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

