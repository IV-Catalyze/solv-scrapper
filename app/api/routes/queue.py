"""
Queue routes for managing queue entries and Experity mapping.

This module contains all routes related to queue management and Experity action mapping.
"""

import logging
import json
import os
import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor, Json
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    TokenData,
    QueueUpdateRequest,
    QueueStatusUpdateRequest,
    QueueRequeueRequest,
    QueueResponse,
    ExperityMapRequest,
    ExperityMapResponse,
    get_db_connection,
    update_queue_status_and_experity_action,
    format_queue_response,
    call_azure_ai_agent,
    AzureAIClientError,
    AzureAIAuthenticationError,
    AzureAIRateLimitError,
    AzureAITimeoutError,
    AzureAIResponseError,
    REQUEST_TIMEOUT,
    AZURE_AI_AVAILABLE,
)

router = APIRouter()

@router.post(
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


@router.get(
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


@router.patch(
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


@router.patch(
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


@router.post(
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
    background_tasks: BackgroundTasks,
    current_client: TokenData = get_auth_dependency()
) -> ExperityMapResponse:
    """
    Map encounter data to Experity actions.
    
    **Two Input Formats Supported:**
    
    1. **Queue Entry Wrapper** - Wrap encounter in `queue_entry` object
       - Provide `encounter_id` or `queue_id` 
       - Optionally include `raw_payload` (otherwise fetched from database)
       - Queue status is set to PROCESSING during mapping, experity_actions are stored in parsed_payload
       - Status is NOT automatically set to DONE - update manually via PATCH /queue/{queue_id}/status if needed
    
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
        # Support both camelCase and snake_case field names
        queue_entry = request_data.queue_entry
        
        # Extract queue_id (support both queue_id and queueId)
        queue_id = queue_entry.get("queue_id") or queue_entry.get("queueId")
        
        # Extract encounter_id (support both encounter_id and encounterId)
        encounter_id = queue_entry.get("encounter_id") or queue_entry.get("encounterId")
        
        # If encounter_id not found, try extracting from encounterPayload.id or encounterPayload
        if not encounter_id:
            encounter_payload = queue_entry.get("encounterPayload") or queue_entry.get("encounter_payload")
            if encounter_payload and isinstance(encounter_payload, dict):
                encounter_id = (
                    encounter_payload.get("id") or 
                    encounter_payload.get("encounterId") or 
                    encounter_payload.get("encounter_id")
                )
        
        # Extract raw_payload (support both raw_payload, rawPayload, encounterPayload, and encounter_payload)
        raw_payload = (
            queue_entry.get("raw_payload") or 
            queue_entry.get("rawPayload") or
            queue_entry.get("encounterPayload") or
            queue_entry.get("encounter_payload")
        )
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
        # For queue_entry format: need encounter_id or queue_id (supports both camelCase and snake_case)
        # For direct encounter format: need id field
        if not encounter_id and not queue_id:
            return ExperityMapResponse(
                success=False,
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "Request must contain either: (1) queue_entry with 'encounter_id'/'encounterId' or 'queue_id'/'queueId' (or 'encounterPayload.id'), or (2) direct encounter object with 'id' field"
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
        
        # Pre-extract deterministic data (ICD updates, severity, etc.) before LLM processing
        # This reduces AI work and ensures accuracy for deterministic mappings
        pre_extracted_icd_updates = []
        pre_extracted_severities = {}
        
        try:
            from app.utils.experity_mapper import extract_icd_updates
            pre_extracted_icd_updates = extract_icd_updates(raw_payload)
            logger.info(f"Pre-extracted {len(pre_extracted_icd_updates)} ICD updates before LLM processing")
        except Exception as pre_extract_error:
            logger.warning(f"Failed to pre-extract ICD updates (continuing anyway): {str(pre_extract_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract severity from complaints (always enabled - code-based mapping)
        pre_extracted_severities = {}
        try:
            from app.utils.experity_mapper.complaint.severity_mapper import extract_severities_from_complaints
            
            # Extract chiefComplaints from encounter
            chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
            if isinstance(chief_complaints, list) and len(chief_complaints) > 0:
                pre_extracted_severities = extract_severities_from_complaints(
                    chief_complaints,
                    encounter_id=encounter_id
                )
                logger.info(f"Pre-extracted {len(pre_extracted_severities)} severity values before LLM processing")
            else:
                logger.debug("No chiefComplaints found, skipping severity extraction")
        except Exception as severity_error:
            logger.warning(f"Failed to pre-extract severity (continuing anyway): {str(severity_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract onset from complaints (always enabled - code-based mapping)
        pre_extracted_onsets = {}
        try:
            from app.utils.experity_mapper.complaint.onset_mapper import extract_onsets_from_complaints
            
            # Extract chiefComplaints from encounter (reuse from previous extractions)
            chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
            if isinstance(chief_complaints, list) and len(chief_complaints) > 0:
                pre_extracted_onsets = extract_onsets_from_complaints(
                    chief_complaints,
                    encounter_id=encounter_id
                )
                logger.info(f"Pre-extracted {len(pre_extracted_onsets)} onset values before LLM processing")
            else:
                logger.debug("No chiefComplaints found, skipping onset extraction")
        except Exception as onset_error:
            logger.warning(f"Failed to pre-extract onset (continuing anyway): {str(onset_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract quality from complaints (always enabled - code-based mapping)
        pre_extracted_qualities = {}
        try:
            from app.utils.experity_mapper.complaint.quality_mapper import extract_qualities_from_complaints
            
            # Extract chiefComplaints from encounter (reuse from previous extractions)
            chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
            if isinstance(chief_complaints, list) and len(chief_complaints) > 0:
                pre_extracted_qualities = extract_qualities_from_complaints(
                    chief_complaints,
                    encounter_id=encounter_id
                )
                logger.info(f"Pre-extracted {len(pre_extracted_qualities)} quality values before LLM processing")
            else:
                logger.debug("No chiefComplaints found, skipping quality extraction")
        except Exception as quality_error:
            logger.warning(f"Failed to pre-extract quality (continuing anyway): {str(quality_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract vitals from encounter attributes (always enabled - code-based mapping)
        pre_extracted_vitals = {}
        try:
            from app.utils.experity_mapper.vitals_mapper import extract_vitals
            
            pre_extracted_vitals = extract_vitals(raw_payload)
            logger.info(f"Pre-extracted vitals before LLM processing (preserved {len(pre_extracted_vitals)} fields)")
        except Exception as vitals_error:
            logger.warning(f"Failed to pre-extract vitals (continuing anyway): {str(vitals_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract guardian info from encounter (always enabled - code-based mapping)
        pre_extracted_guardian = {}
        try:
            from app.utils.experity_mapper.guardian_mapper import extract_guardian
            
            pre_extracted_guardian = extract_guardian(raw_payload)
            logger.info(f"Pre-extracted guardian info before LLM processing (preserved {len(pre_extracted_guardian)} fields)")
        except Exception as guardian_error:
            logger.warning(f"Failed to pre-extract guardian (continuing anyway): {str(guardian_error)}")
            # Continue without pre-extraction if it fails
        
        # Extract lab orders from encounter (always enabled - code-based mapping)
        pre_extracted_lab_orders = []
        try:
            from app.utils.experity_mapper.lab_orders_mapper import extract_lab_orders
            
            pre_extracted_lab_orders = extract_lab_orders(raw_payload)
            logger.info(f"Pre-extracted {len(pre_extracted_lab_orders)} lab orders before LLM processing")
        except Exception as lab_orders_error:
            logger.warning(f"Failed to pre-extract lab orders (continuing anyway): {str(lab_orders_error)}")
            # Continue without pre-extraction if it fails
        
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
                
                # Log Azure AI configuration (without secrets)
                try:
                    from app.utils.azure_ai_agent_client import AZURE_SDK_AVAILABLE
                    logger.info(f"Azure SDK available: {AZURE_SDK_AVAILABLE}")
                    if AZURE_SDK_AVAILABLE:
                        project_endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "Not set")
                        deployment_name = os.environ.get("AZURE_AI_DEPLOYMENT_NAME", "Not set")
                        agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID", "Not set")
                        logger.info(f"Azure AI Config - Project: {project_endpoint[:50]}..., Deployment: {deployment_name}, Agent ID: {agent_id}")
                    else:
                        logger.warning("⚠️  Azure SDK not available - check if packages are installed")
                except Exception as config_error:
                    logger.warning(f"Could not log Azure AI config: {config_error}")
                
                logger.info(f"Calling Azure AI agent with encounter_id: {encounter_id}")
                experity_mapping = await call_azure_ai_agent(queue_entry)
                
                # Merge pre-extracted deterministic data into LLM response
                # This overwrites LLM's ICD updates with deterministic extraction
                if pre_extracted_icd_updates:
                    try:
                        from app.utils.experity_mapper import merge_icd_updates_into_response
                        experity_mapping = merge_icd_updates_into_response(
                            experity_mapping,
                            pre_extracted_icd_updates,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted ICD updates into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge ICD updates (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted severity into LLM response (always enabled - code-based mapping)
                if pre_extracted_severities:
                    try:
                        from app.utils.experity_mapper import merge_severity_into_complaints
                        
                        # Get source complaints for better matching
                        chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
                        
                        experity_mapping = merge_severity_into_complaints(
                            experity_mapping,
                            pre_extracted_severities,
                            source_complaints=chief_complaints if isinstance(chief_complaints, list) else None,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted severity values into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge severity (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted onset into LLM response (always enabled - code-based mapping)
                if pre_extracted_onsets:
                    try:
                        from app.utils.experity_mapper import merge_onset_into_complaints
                        
                        # Get source complaints for better matching
                        chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
                        
                        experity_mapping = merge_onset_into_complaints(
                            experity_mapping,
                            pre_extracted_onsets,
                            source_complaints=chief_complaints if isinstance(chief_complaints, list) else None,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted onset values into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge onset (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted quality into LLM response (always enabled - code-based mapping)
                if pre_extracted_qualities:
                    try:
                        from app.utils.experity_mapper import merge_quality_into_complaints
                        
                        # Get source complaints for better matching
                        chief_complaints = raw_payload.get("chiefComplaints") or raw_payload.get("chief_complaints", [])
                        
                        experity_mapping = merge_quality_into_complaints(
                            experity_mapping,
                            pre_extracted_qualities,
                            source_complaints=chief_complaints if isinstance(chief_complaints, list) else None,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted quality values into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge quality (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted vitals into LLM response (always enabled - code-based mapping)
                if pre_extracted_vitals:
                    try:
                        from app.utils.experity_mapper import merge_vitals_into_response
                        
                        experity_mapping = merge_vitals_into_response(
                            experity_mapping,
                            pre_extracted_vitals,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted vitals into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge vitals (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted guardian into LLM response (always enabled - code-based mapping)
                if pre_extracted_guardian:
                    try:
                        from app.utils.experity_mapper import merge_guardian_into_response
                        
                        experity_mapping = merge_guardian_into_response(
                            experity_mapping,
                            pre_extracted_guardian,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted guardian info into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge guardian (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Merge pre-extracted lab orders into LLM response (always enabled - code-based mapping)
                if pre_extracted_lab_orders:
                    try:
                        from app.utils.experity_mapper import merge_lab_orders_into_response
                        
                        experity_mapping = merge_lab_orders_into_response(
                            experity_mapping,
                            pre_extracted_lab_orders,
                            overwrite=True  # Always use deterministic extraction
                        )
                        logger.info("Merged pre-extracted lab orders into LLM response")
                    except Exception as merge_error:
                        logger.warning(f"Failed to merge lab orders (continuing anyway): {str(merge_error)}")
                        # Continue even if merge fails
                
                # Validate and fix format issues in the response
                try:
                    from app.utils.response_validator import validate_and_fix_experity_response
                    # Get source encounter data for validation
                    source_encounter = queue_entry.get("raw_payload") or queue_entry.get("encounterPayload") or {}
                    experity_mapping = validate_and_fix_experity_response(experity_mapping, source_encounter)
                    logger.info("Response validation and format correction completed")
                except Exception as validation_error:
                    logger.warning(f"Response validation failed (continuing anyway): {str(validation_error)}")
                    # Continue even if validation fails
                
                # Success - break out of retry loop
                break
            except AzureAIAuthenticationError as e:
                # Authentication errors should not be retried
                error_message = str(e)
                # Log detailed error for debugging, but don't expose it to UI
                logger.error(f"Azure AI authentication error (not shown to user): {error_message}")
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
                error_message = str(e)
                logger.error(f"Azure AI error: {error_message}")
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
                # Log detailed error for debugging, but don't expose it to UI
                logger.error(f"Azure AI detailed error (not shown to user): {error_message}")
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
        
        # Store experity_actions in parsed_payload without updating status
        # Status remains as-is (typically PROCESSING) and can be updated manually later
        if queue_id and conn:
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                # Get current parsed_payload
                cursor.execute(
                    "SELECT parsed_payload FROM queue WHERE queue_id = %s",
                    (queue_id,)
                )
                queue_entry = cursor.fetchone()
                
                if queue_entry:
                    # Parse current parsed_payload
                    parsed_payload = queue_entry.get('parsed_payload')
                    if isinstance(parsed_payload, str):
                        try:
                            parsed_payload = json.loads(parsed_payload)
                        except json.JSONDecodeError:
                            parsed_payload = {}
                    elif parsed_payload is None:
                        parsed_payload = {}
                    
                    # Store experity_actions without changing status
                    parsed_payload['experityAction'] = experity_mapping
                    
                    # Update only parsed_payload, keep status unchanged
                    from psycopg2.extras import Json
                    cursor.execute(
                        "UPDATE queue SET parsed_payload = %s, updated_at = CURRENT_TIMESTAMP WHERE queue_id = %s",
                        (Json(parsed_payload), queue_id)
                    )
                    conn.commit()
                    logger.info(f"Stored experity_actions for queue_id: {queue_id} (status unchanged)")
                cursor.close()
            except Exception as e:
                logger.warning(f"Failed to store experity_actions: {str(e)}")
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

        # Add startedAt from encounter if present
        started_at = raw_payload.get("startedAt") or raw_payload.get("started_at")
        if started_at:
            response_data["startedAt"] = started_at

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
        # Enhanced error logging with full context
        import traceback
        error_type = type(e).__name__
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(
            f"❌ Unexpected error in map_queue_to_experity: {error_type}: {error_message}",
            exc_info=True
        )
        logger.error(f"Full traceback:\n{error_traceback}")
        
        # Log additional context if available
        try:
            if hasattr(e, '__cause__') and e.__cause__:
                logger.error(f"Caused by: {type(e.__cause__).__name__}: {str(e.__cause__)}")
            if hasattr(e, '__context__') and e.__context__:
                logger.error(f"Context: {type(e.__context__).__name__}: {str(e.__context__)}")
        except:
            pass
        
        # Check if it's an import error (SDK not installed)
        if "No module named" in error_message or "ImportError" in error_type:
            logger.error("⚠️  Azure SDK may not be installed. Check requirements.txt and deployment.")
        
        return ExperityMapResponse(
            success=False,
            error={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred while processing the request",
                "details": {
                    "error_type": error_type,
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

