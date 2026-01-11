"""
Summary routes for managing patient summary records.

This module contains all routes related to patient summaries.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Query
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    TokenData,
    SummaryRequest,
    SummaryResponse,
    get_db_connection,
    save_summary,
    get_summary_by_emr_id,
    format_summary_response,
)

router = APIRouter()


@router.post(
    "/summary",
    tags=["Summaries"],
    summary="Create summary record",
    response_model=SummaryResponse,
    status_code=201,
    responses={
        201: {
            "description": "Summary record created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
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
) -> SummaryResponse:
    """
    **Request Body:**
    - `emrId` (required): EMR identifier for the patient
    - `note` (required): Summary note text containing clinical information
    
    **Example:**
    ```json
    POST /summary
    {
      "emrId": "EMR12345",
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
        
        if not summary_data.note:
            raise HTTPException(
                status_code=400,
                detail="note is required. Please provide summary note text."
            )
        
        # Prepare summary data
        summary_dict = {
            'emr_id': summary_data.emrId,
            'note': summary_data.note,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the summary
        saved_summary = save_summary(conn, summary_dict)
        
        # Format the response
        formatted_response = format_summary_response(saved_summary)
        
        # Use by_alias=False to output camelCase field names (matching OpenAPI schema)
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
    summary="Get summary by EMR ID",
    response_model=SummaryResponse,
    responses={
        200: {
            "description": "Summary record",
            "content": {
                "application/json": {
                    "example": {
                        "id": 123,
                        "emrId": "EMR12345",
                        "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Summary not found"},
        500: {"description": "Server error"},
    },
)
async def get_summary(
    emrId: str = Query(..., alias="emrId", description="EMR identifier for the patient"),
    current_client: TokenData = get_auth_dependency()
) -> SummaryResponse:
    """
    Get the most recent summary record for a patient.
    
    **Example:**
    ```
    GET /summary?emrId=EMR12345
    ```
    
    Returns the summary with the latest `updatedAt` timestamp. If multiple summaries exist, only the most recent one is returned.
    """
    conn = None
    
    try:
        if not emrId:
            raise HTTPException(
                status_code=400,
                detail="emrId query parameter is required."
            )
        
        # Get database connection
        conn = get_db_connection()
        
        # Retrieve the summary
        summary = get_summary_by_emr_id(conn, emrId)
        
        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"Summary not found for EMR ID: {emrId}"
            )
        
        # Format the response
        formatted_response = format_summary_response(summary)
        
        # Use by_alias=False to output camelCase field names (matching OpenAPI schema)
        return SummaryResponse(**formatted_response).model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
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
        if conn:
            conn.close()

