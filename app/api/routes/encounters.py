"""
Encounter routes for managing encounter records.

This module contains all routes related to encounter data management.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    TokenData,
    EncounterResponse,
    get_db_connection,
    save_encounter,
    create_queue_from_encounter,
    format_encounter_response,
)

router = APIRouter()


@router.post(
    "/encounter",
    tags=["Encounters"],
    summary="Create or update encounter record",
    response_model=EncounterResponse,
    status_code=201,
    responses={
        201: {
            "description": "Encounter record created or updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "encounterPayload": {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                            "attributes": {
                                "gender": "male",
                                "ageYears": 69
                            },
                            "chiefComplaints": [
                                {
                                    "id": "00f9612e-f37d-451b-9172-25cbddee58a9",
                                    "description": "cough",
                                    "type": "search"
                                }
                            ],
                            "status": "COMPLETE",
                            "createdBy": "user@example.com"
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request data or missing required fields"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_encounter(
    request: Request,
    current_client: TokenData = get_auth_dependency()
) -> EncounterResponse:
    """
    **Request Body:**
    - `emrId` (required): EMR identifier for the patient
    - `encounterPayload` (required): Full encounter JSON object. Must contain `id` (the ID of the encounter) field.
    
    **Example:**
    ```json
    POST /encounter
    {
      "emrId": "EMR12345",
      "encounterPayload": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "attributes": {
          "gender": "male",
          "ageYears": 69
        },
        "chiefComplaints": [
          {
            "id": "00f9612e-f37d-451b-9172-25cbddee58a9",
            "description": "cough",
            "type": "search"
          }
        ],
        "status": "COMPLETE",
        "createdBy": "user@example.com",
      }
      }
   
    
    **Response:**
    Returns the stored encounter with `emrId` and `encounterPayload`.
    If an encounter with the same `encounterId` (from `encounterPayload.id` or `encounterPayload.encounterId`) exists, it will be updated.
    
    **Note on createdBy:**
    - The `createdBy` field is preserved in the encounter record exactly as provided.

    """
    conn = None
    
    try:
        # Capture raw JSON body
        request_body = await request.json()
        
        # Extract emrId (support both camelCase and snake_case)
        emr_id = request_body.get('emrId') or request_body.get('emr_id')
        if not emr_id:
            raise HTTPException(
                status_code=400,
                detail="emrId is required. Please provide an EMR identifier for the patient."
            )
        
        # Extract encounterPayload (support both camelCase and snake_case)
        encounter_payload = request_body.get('encounterPayload') or request_body.get('encounter_payload')
        if not encounter_payload:
            raise HTTPException(
                status_code=400,
                detail="encounterPayload is required. Please provide the full encounter JSON payload."
            )
        
        # Validate encounterPayload is a dictionary
        if not isinstance(encounter_payload, dict):
            raise HTTPException(
                status_code=400,
                detail="encounterPayload must be a JSON object."
            )
        
        # Extract encounter_id from within encounterPayload
        # Try both 'id' and 'encounterId' fields (support both camelCase and snake_case)
        encounter_id = (
            encounter_payload.get('id') or 
            encounter_payload.get('encounterId') or 
            encounter_payload.get('encounter_id')
        )
        
        if not encounter_id:
            raise HTTPException(
                status_code=400,
                detail="encounterPayload must contain either an 'id' or 'encounterId' field to identify the encounter."
            )
        
        # Build encounter_dict with only the 3 required fields
        encounter_dict = {
            'encounter_id': str(encounter_id),
            'emr_id': str(emr_id),
            'encounter_payload': encounter_payload,  # Store full encounter JSON
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the encounter
        saved_encounter = save_encounter(conn, encounter_dict)
        
        # Automatically create queue entry from encounter
        try:
            create_queue_from_encounter(conn, saved_encounter)
        except Exception as e:
            # Log error but don't fail the encounter creation
            logger.warning(f"Failed to create queue entry for encounter {encounter_id}: {str(e)}")
        
        # Format the response
        formatted_response = format_encounter_response(saved_encounter)
        
        return EncounterResponse(**formatted_response)
        
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

