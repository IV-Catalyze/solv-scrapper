"""
Summary routes for managing patient summary records.

This module contains all routes related to patient summaries.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
import psycopg2
from psycopg2.extras import RealDictCursor

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    TokenData,
    SummaryRequest,
    SummaryResponse,
    get_db_connection,
    save_summary,
    get_summary_by_emr_id,
    get_summary_by_encounter_id,
    format_summary_response,
)

router = APIRouter()


@router.post(
    "/summary",
    tags=["Summaries"],
    summary="Create summary record",
    status_code=201,
        responses={
        201: {
            "description": "Summary record created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
                        "encounterId": "550e8400-e29b-41d4-a716-446655440000",
                        "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data or missing required fields"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_summary(
    summary_data: SummaryRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    **Request Body:**
    - `emrId` (required): EMR identifier for the patient
    - `encounterId` (required): Encounter identifier (UUID) for the encounter
    - `note` (required): Summary note text containing clinical information
    
    **Example:**
    ```json
    POST /summary
    {
      "emrId": "EMR12345",
      "encounterId": "550e8400-e29b-41d4-a716-446655440000",
      "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days."
    }
    ```
    
    **Response:**
    Returns the created summary record with auto-generated `id` and timestamps.
    """
    conn = None
    
    try:
        # Validate required fields
        if not summary_data.emrId:
            raise HTTPException(
                status_code=400,
                detail="emrId is required. Please provide an EMR identifier."
            )
        
        if not summary_data.encounterId:
            raise HTTPException(
                status_code=400,
                detail="encounterId is required. Please provide an encounter identifier (UUID)."
            )
        
        if not summary_data.note:
            raise HTTPException(
                status_code=400,
                detail="note is required. Please provide summary note text."
            )
        
        # Prepare summary data
        summary_dict = {
            'emr_id': summary_data.emrId,
            'encounter_id': summary_data.encounterId,
            'note': summary_data.note,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the summary
        saved_summary = save_summary(conn, summary_dict)
        
        # Format the response
        formatted_response = format_summary_response(saved_summary)
        
        # Create model for validation, then return dict with camelCase keys
        # FastAPI's jsonable_encoder uses aliases for models, but preserves dict keys
        summary_response = SummaryResponse(**formatted_response)
        response_dict = summary_response.model_dump(by_alias=False)
        
        # Return dict directly - FastAPI will serialize it as-is (camelCase)
        # Bypassing response_model serialization which would use aliases
        return response_dict
        
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
    "/summary",
    tags=["Summaries"],
    summary="Get summary by EMR ID, Queue ID, or Encounter ID",
    responses={
        200: {
            "description": "Summary record",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
                        "encounterId": "550e8400-e29b-41d4-a716-446655440000",
                        "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request - either emrId, queueId, or encounterId must be provided"},
        401: {"description": "Authentication required"},
        404: {"description": "Queue entry or summary not found"},
        500: {"description": "Server error"},
    },
)
async def get_summary(
    emrId: Optional[str] = Query(None, alias="emrId", description="EMR identifier for the patient"),
    queueId: Optional[str] = Query(None, alias="queueId", description="Queue identifier (UUID). If provided, will lookup emrId from queue entry."),
    encounterId: Optional[str] = Query(None, alias="encounterId", description="Encounter identifier (UUID). If provided, will lookup summary by encounter ID."),
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    Get the most recent summary record for a patient.
    
    Can be retrieved by `emrId`, `queueId`, or `encounterId`. If `queueId` is provided, the system will
    first lookup the associated `emrId` from the queue entry, then retrieve the summary. If `encounterId`
    is provided, the summary will be retrieved directly by encounter ID.
    
    **Examples:**
    ```
    GET /summary?emrId=EMR12345
    GET /summary?queueId=550e8400-e29b-41d4-a716-446655440000
    GET /summary?encounterId=550e8400-e29b-41d4-a716-446655440000
    ```
    
    Returns the summary with the latest `updatedAt` timestamp. If multiple summaries exist, only the most recent one is returned.
    """
    conn = None
    cursor = None
    
    try:
        # Validate that at least one parameter is provided
        if not emrId and not queueId and not encounterId:
            raise HTTPException(
                status_code=400,
                detail="Either emrId, queueId, or encounterId must be provided."
            )
        
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        summary = None
        
        # If encounterId is provided, use it directly
        if encounterId:
            # Close cursor before calling get_summary_by_encounter_id (which creates its own cursor)
            cursor.close()
            cursor = None
            
            # Retrieve the summary using encounter_id
            summary = get_summary_by_encounter_id(conn, encounterId)
            
            if not summary:
                raise HTTPException(
                    status_code=404,
                    detail=f"Summary not found for Encounter ID: {encounterId}"
                )
        else:
            # Resolve emr_id: either use provided emrId or lookup from queue
            emr_id_to_use = None
            
            if queueId:
                # Lookup emr_id from queue table
                cursor.execute(
                    "SELECT emr_id FROM queue WHERE queue_id = %s",
                    (queueId,)
                )
                queue_entry = cursor.fetchone()
                
                if not queue_entry:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Queue entry not found: {queueId}"
                    )
                
                emr_id_to_use = queue_entry.get('emr_id')
                if not emr_id_to_use:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Queue entry exists but has no emr_id associated: {queueId}"
                    )
            else:
                # Use provided emrId directly
                emr_id_to_use = emrId
            
            # Close cursor before calling get_summary_by_emr_id (which creates its own cursor)
            cursor.close()
            cursor = None
            
            # Retrieve the summary using the resolved emr_id
            summary = get_summary_by_emr_id(conn, emr_id_to_use)
            
            if not summary:
                raise HTTPException(
                    status_code=404,
                    detail=f"Summary not found for EMR ID: {emr_id_to_use}"
                )
        
        # Format the response
        formatted_response = format_summary_response(summary)
        
        # Create model for validation, then return dict with camelCase keys
        # FastAPI's jsonable_encoder uses aliases for models, but preserves dict keys
        summary_response = SummaryResponse(**formatted_response)
        response_dict = summary_response.model_dump(by_alias=False)
        
        # Return dict directly - FastAPI will serialize it as-is (camelCase)
        # Bypassing response_model serialization which would use aliases
        return response_dict
        
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

