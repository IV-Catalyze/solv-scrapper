"""
Experity process time routes for monitoring process durations.

This module contains all routes related to Experity process time tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
import psycopg2

from app.api.routes.dependencies import (
    logger,
    require_auth,
    TokenData,
    get_db_connection,
)
from app.api.models import (
    ExperityProcessTimeRequest,
    ExperityProcessTimeResponse,
    ExperityProcessTimeItem,
    ExperityProcessTimeListResponse,
)
from app.api.database import (
    save_experity_process_time,
    get_experity_process_times,
)
from app.utils.auth import verify_api_key_auth

router = APIRouter()


async def verify_experity_api_key_auth(request: Request) -> TokenData:
    """
    Verify authentication for Experity process time endpoints using X-API-Key header.
    
    Args:
        request: FastAPI request object
        
    Returns:
        TokenData object with client information
        
    Raises:
        HTTPException: If API key authentication fails
    """
    return await verify_api_key_auth(request, "Experity process time endpoints", "API_KEY")


@router.post(
    "/experity/process-time",
    tags=["Experity"],
    summary="Submit Experity process time",
    description="Submit a process time record for monitoring Experity process durations. Uses X-API-Key authentication.",
    response_model=ExperityProcessTimeResponse,
    status_code=200,
    responses={
        200: {
            "description": "Process time recorded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "processTimeId": "550e8400-e29b-41d4-a716-446655440000",
                        "success": True,
                        "processName": "Encounter process time",
                        "startedAt": "2025-01-22T10:30:00Z",
                        "endedAt": "2025-01-22T10:35:00Z",
                        "durationSeconds": 300,
                        "createdAt": "2025-01-22T10:35:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "X-API-Key header required or invalid"},
        500: {"description": "Server error"},
    },
)
async def create_process_time(
    process_time_data: ExperityProcessTimeRequest,
    request: Request,
    current_client: TokenData = Depends(verify_experity_api_key_auth)
) -> ExperityProcessTimeResponse:
    """
    Submit a process time record for Experity process monitoring.
    
    **Authentication:**
    - Use `X-API-Key` header with your HMAC secret key
    - Example: `X-API-Key: your-hmac-secret-key`
    
    **Request Body:**
    - `processName` (required): Process name - 'Encounter process time' or 'Experity process time'
    - `startedAt` (required): ISO 8601 timestamp when the process started
    - `endedAt` (required): ISO 8601 timestamp when the process ended
    
    **Response:**
    Returns the created process time record with `processTimeId`, `success`, and timestamps.
    
    **Example Request:**
    ```json
    {
      "processName": "Encounter process time",
      "startedAt": "2025-01-22T10:30:00Z",
      "endedAt": "2025-01-22T10:35:00Z"
    }
    ```
    """
    conn = None
    
    try:
        # Prepare process time data for database
        process_time_dict = {
            'process_name': process_time_data.processName,
            'started_at': process_time_data.startedAt,
            'ended_at': process_time_data.endedAt,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the process time record
        saved_process_time = save_experity_process_time(conn, process_time_dict)
        
        # Format timestamps
        started_at = saved_process_time.get('started_at')
        if isinstance(started_at, datetime):
            started_at_str = started_at.isoformat() + 'Z'
        elif isinstance(started_at, str):
            started_at_str = started_at
        else:
            started_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
        
        ended_at = saved_process_time.get('ended_at')
        ended_at_str = None
        if ended_at:
            if isinstance(ended_at, datetime):
                ended_at_str = ended_at.isoformat() + 'Z'
            elif isinstance(ended_at, str):
                ended_at_str = ended_at
        
        created_at = saved_process_time.get('created_at')
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat() + 'Z'
        elif isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
        
        # Format the response
        response_data = {
            'processTimeId': str(saved_process_time['process_time_id']),
            'success': True,
            'processName': saved_process_time['process_name'],
            'startedAt': started_at_str,
            'endedAt': ended_at_str,
            'durationSeconds': saved_process_time.get('duration_seconds'),
            'createdAt': created_at_str,
        }
        
        # Create response model and serialize
        process_time_response = ExperityProcessTimeResponse(**response_data)
        response_dict = process_time_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
    "/experity/process-time",
    tags=["Experity"],
    summary="Retrieve Experity process time records",
    description="Retrieve process time records with filtering and pagination. Supports filtering by process name and date range.",
    response_model=ExperityProcessTimeListResponse,
    status_code=200,
    responses={
        200: {
            "description": "Process time records retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "processTimes": [
                            {
                                "processTimeId": "550e8400-e29b-41d4-a716-446655440000",
                                "processName": "Encounter process time",
                                "startedAt": "2025-01-22T10:30:00Z",
                                "endedAt": "2025-01-22T10:35:00Z",
                                "durationSeconds": 300,
                                "createdAt": "2025-01-22T10:35:00Z"
                            }
                        ],
                        "total": 15,
                        "limit": 50,
                        "offset": 0
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_process_times_list(
    processName: Optional[str] = Query(None, description="Filter by process name (Encounter process time, Experity process time)"),
    startedAfter: Optional[str] = Query(None, description="Filter by start time (ISO 8601 timestamp) - only records started after this"),
    startedBefore: Optional[str] = Query(None, description="Filter by start time (ISO 8601 timestamp) - only records started before this"),
    completedOnly: Optional[bool] = Query(False, description="Only return completed processes (with endedAt set)"),
    limit: int = Query(50, ge=1, le=100, description="Number of records to return (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(require_auth)
) -> ExperityProcessTimeListResponse:
    """
    Retrieve process time records with filtering and pagination.
    
    **Query Parameters:**
    - `processName` (optional): Filter by process name
    - `startedAfter` (optional): Filter by start time - only records started after this timestamp
    - `startedBefore` (optional): Filter by start time - only records started before this timestamp
    - `completedOnly` (optional): Only return completed processes (default: false)
    - `limit` (optional): Number of records to return (default: 50, max: 100)
    - `offset` (optional): Pagination offset (default: 0)
    
    **Response:**
    Returns a list of process time records with `processTimes`, `total`, `limit`, and `offset`.
    """
    conn = None
    
    try:
        # Validate query parameters
        if processName and processName not in ['Encounter process time', 'Experity process time']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid processName: {processName}. Must be one of: Encounter process time, Experity process time"
            )
        
        # Build filters
        filters = {}
        if processName:
            filters['process_name'] = processName
        if startedAfter:
            filters['started_after'] = startedAfter
        if startedBefore:
            filters['started_before'] = startedBefore
        if completedOnly:
            filters['completed_only'] = True
        
        # Get database connection
        conn = get_db_connection()
        
        # Get process times
        process_times_list, total = get_experity_process_times(conn, filters=filters, limit=limit, offset=offset)
        
        # Format process times for response
        formatted_process_times = []
        for process_time in process_times_list:
            # Format timestamps
            started_at = process_time.get('started_at')
            if isinstance(started_at, datetime):
                started_at_str = started_at.isoformat() + 'Z'
            elif isinstance(started_at, str):
                started_at_str = started_at
            else:
                started_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
            
            ended_at = process_time.get('ended_at')
            ended_at_str = None
            if ended_at:
                if isinstance(ended_at, datetime):
                    ended_at_str = ended_at.isoformat() + 'Z'
                elif isinstance(ended_at, str):
                    ended_at_str = ended_at
            
            created_at = process_time.get('created_at')
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat() + 'Z'
            elif isinstance(created_at, str):
                created_at_str = created_at
            else:
                created_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
            
            formatted_process_time = {
                'processTimeId': str(process_time['process_time_id']),
                'processName': process_time['process_name'],
                'startedAt': started_at_str,
                'endedAt': ended_at_str,
                'durationSeconds': process_time.get('duration_seconds'),
                'createdAt': created_at_str,
            }
            formatted_process_times.append(ExperityProcessTimeItem(**formatted_process_time))
        
        # Create response
        response_data = {
            'processTimes': formatted_process_times,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
        
        process_time_list_response = ExperityProcessTimeListResponse(**response_data)
        response_dict = process_time_list_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
