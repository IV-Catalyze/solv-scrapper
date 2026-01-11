"""
Patient routes for managing patient records.

This module contains all routes related to patient data management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg2.extras import RealDictCursor
import psycopg2

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    TokenData,
    PatientPayload,
    PatientCreateRequest,
    StatusUpdateRequest,
    get_db_connection,
    ensure_client_location_access,
    resolve_location_id,
    normalize_status,
    expand_status_shortcuts,
    DEFAULT_STATUSES,
    use_remote_api_for_reads,
    fetch_remote_patients,
    get_local_patients,
    filter_patients_by_search,
    build_patient_payload,
    normalize_patient_record,
    insert_patients,
)

router = APIRouter()


@router.get(
    "/patient/{emrId}",
    tags=["Patients"],
    response_model=PatientPayload,
    responses={
        200: {
            "description": "Patient record",
            "content": {
                "application/json": {
                    "example": {
                        "emrId": "EMR12345",
                        "bookingId": "0Pa1Z6",
                        "locationId": "AXjwbE",
                        "locationName": "Demo Clinic",
                        "legalFirstName": "John",
                        "legalLastName": "Doe",
                        "dob": "1990-01-15",
                        "mobilePhone": "+1234567890",
                        "sexAtBirth": "M",
                        "capturedAt": "2025-11-21T10:30:00Z",
                        "reasonForVisit": "Annual checkup",
                        "createdAt": "2025-11-21T10:30:00Z",
                        "updatedAt": "2025-11-21T10:30:00Z",
                        "status": "confirmed"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Patient not found"},
        500: {"description": "Server error"},
    },
)
async def get_patient_by_emr_id(
    emrId: str,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    **Example:**
    ```
    GET /patient/EMR12345
    ```
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query for the most recent patient record with the given emr_id
        query = """
            SELECT 
                id,
                emr_id,
                booking_id,
                booking_number,
                patient_number,
                location_id,
                location_name,
                status,
                legal_first_name,
                legal_last_name,
                dob,
                mobile_phone,
                sex_at_birth,
                captured_at,
                reason_for_visit,
                created_at,
                updated_at
            FROM patients
            WHERE emr_id = %s
            ORDER BY captured_at DESC
            LIMIT 1;
        """
        
        cursor.execute(query, (emrId,))
        record = cursor.fetchone()
        
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emrId}' not found"
            )
        
        ensure_client_location_access(record.get("location_id"), current_client)
        
        response_payload = build_patient_payload(record)

        # Remove these fields completely from the response (always exclude)
        fields_to_always_exclude = [
            "booking_number", "patient_number",
            "appointment_date", "appointment_date_at_clinic_tz", "calendar_date",
            "status_class", "status_label", "captured_display", "source"
        ]
        # Remove excluded fields regardless of their values
        filtered_payload = {
            k: v for k, v in response_payload.items()
            if k not in fields_to_always_exclude
        }

        # Create model and exclude both None and unset values from serialization
        # Use by_alias=True to output camelCase field names
        patient = PatientPayload(**filtered_payload)
        return patient.model_dump(exclude_none=True, exclude_unset=True, by_alias=True)
        
    except HTTPException:
        # Re-raise HTTP exceptions
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


@router.post(
    "/patients/create",
    tags=["Patients"],
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Patient record",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Patient record created successfully",
                        "emrId": "EMR12345",
                        "bookingId": "0Pa1Z6",
                        "status": "created",
                        "insertedCount": 1
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_patient(
    patient_data: PatientCreateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    """
    if not normalize_patient_record or not insert_patients:
        raise HTTPException(
            status_code=503,
            detail="Patient save functionality unavailable"
        )
    
    conn = None
    try:
        # Convert Pydantic model to dict (use by_alias=False to get internal field names for normalization)
        patient_dict = patient_data.model_dump(exclude_none=True, by_alias=False)
        
        # Normalize the patient record (normalize_patient_record accepts both camelCase and snake_case)
        normalized = normalize_patient_record(patient_dict)
        
        # Check if emr_id is required
        emr_id = normalized.get("emr_id")
        if not emr_id:
            raise HTTPException(
                status_code=400,
                detail="emr_id is required. Please provide an EMR identifier for the patient."
            )
        
        conn = get_db_connection()

        # If location_id is missing, try to reuse existing record's location_id (and other fields) for updates.
        if not normalized.get("location_id"):
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM patients WHERE emr_id = %s ORDER BY updated_at DESC NULLS LAST, captured_at DESC NULLS LAST LIMIT 1",
                (emr_id,),
            )
            existing = cursor.fetchone()
            cursor.close()

            if existing:
                # Merge: keep any newly provided fields, fill gaps from existing record.
                merge_fields = [
                    "location_id",
                    "location_name",
                    "booking_id",
                    "booking_number",
                    "patient_number",
                    "legal_first_name",
                    "legal_last_name",
                    "dob",
                    "mobile_phone",
                    "sex_at_birth",
                    "reason_for_visit",
                ]
                for field in merge_fields:
                    if normalized.get(field) is None and existing.get(field) is not None:
                        normalized[field] = existing[field]

            # After merge, still no location_id -> cannot create a brand new record without it.
            if not normalized.get("location_id"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "location_id is required for new patients. "
                        "For existing patients, ensure an initial record with location_id was created before "
                        "sending status-only updates."
                    ),
                )

        normalized_location_id = ensure_client_location_access(normalized.get("location_id"), current_client)
        normalized["location_id"] = normalized_location_id

        inserted_count = insert_patients(conn, [normalized], on_conflict='update')
        
        if inserted_count == 0:
            # Record might already exist, try to fetch it
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM patients WHERE emr_id = %s LIMIT 1",
                (normalized['emr_id'],)
            )
            existing = cursor.fetchone()
            cursor.close()
            
            if existing:
                return {
                    "message": "Patient record already exists and was updated",
                    "emrId": normalized['emr_id'],
                    "bookingId": normalized.get('booking_id'),
                    "status": "updated"
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create patient record"
                )
        
        return {
            "message": "Patient record created successfully",
            "emrId": normalized['emr_id'],
            "bookingId": normalized.get('booking_id'),
            "status": "created",
            "insertedCount": inserted_count
        }
        
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


@router.patch(
    "/patients/{emrId}",
    tags=["Patients"],
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Status update result",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Patient status updated successfully",
                        "emrId": "EMR12345",
                        "oldStatus": "confirmed",
                        "newStatus": "checked_in",
                        "updatedAt": "2025-11-21T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        404: {"description": "Patient not found"},
        500: {"description": "Server error"},
    },
)
async def update_patient_status(
    emrId: str,
    status_data: StatusUpdateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    """
    if not emrId or not emrId.strip():
        raise HTTPException(
            status_code=400,
            detail="emrId is required in the URL path"
        )
    
    emr_id_clean = emrId.strip()
    normalized_status = normalize_status(status_data.status)
    
    if not normalized_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status value: {status_data.status}"
        )
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if patient exists
        cursor.execute(
            "SELECT id, emr_id, status, location_id FROM patients WHERE emr_id = %s LIMIT 1",
            (emr_id_clean,)
        )
        existing = cursor.fetchone()
        
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emr_id_clean}' not found"
            )
        
        ensure_client_location_access(existing.get("location_id"), current_client)
        
        # Update status
        cursor.execute(
            """
            UPDATE patients
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE emr_id = %s
            RETURNING id, emr_id, status, updated_at
            """,
            (normalized_status, emr_id_clean)
        )
        
        updated = cursor.fetchone()
        conn.commit()
        
        return {
            "message": "Patient status updated successfully",
            "emrId": emr_id_clean,
            "oldStatus": existing.get("status"),
            "newStatus": normalized_status,
            "updatedAt": updated.get("updated_at").isoformat() if updated.get("updated_at") else None
        }
        
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
    "/patients",
    tags=["Patients"],
    response_model=List[PatientPayload],
    responses={
        200: {
            "description": "List of patient records",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "emrId": "EMR12345",
                            "bookingId": "0Pa1Z6",
                            "locationId": "AXjwbE",
                            "locationName": "Demo Clinic",
                            "legalFirstName": "John",
                            "legalLastName": "Doe",
                            "dob": "1990-01-15",
                            "mobilePhone": "+1234567890",
                            "sexAtBirth": "M",
                            "capturedAt": "2025-11-21T10:30:00Z",
                            "reasonForVisit": "Annual checkup",
                            "createdAt": "2025-11-21T10:30:00Z",
                            "updatedAt": "2025-11-21T10:30:00Z",
                            "status": "confirmed"
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
async def list_patients(
    request: Request,
    locationId: Optional[str] = Query(
        default=None,
        alias="locationId",
        description="Location identifier. Required unless DEFAULT_LOCATION_ID is set.",
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        alias="limit",
        description="Maximum number of records to return"
    ),
    statuses: Optional[List[str]] = Query(
        default=None,
        alias="statuses",
        description="Filter by status. Use 'active' for active statuses (checked_in, confirmed). Defaults to checked_in, confirmed if not provided."
    ),
    current_client: TokenData = get_auth_dependency()
):
    """
    **Query Parameters:**
    - `locationId` (optional) - Required unless DEFAULT_LOCATION_ID is set
    - `statuses` (optional) - Defaults to checked_in, confirmed. Use 'active' for patients with checked_in/confirmed status.
    - `limit` (optional)
    
    **Example:**
    ```
    GET /patients?locationId=AXjwbE&statuses=confirmed&limit=50
    GET /patients?locationId=AXjwbE&statuses=active
    ```
    """
    # Check if 'active' shortcut was requested (for 24h filter)
    is_active_filter = statuses is not None and any(
        s.strip().lower() == "active" for s in statuses if isinstance(s, str)
    )
    
    if statuses is None:
        normalized_statuses = DEFAULT_STATUSES.copy()
    else:
        # First expand any shortcuts like 'active'
        expanded_statuses = expand_status_shortcuts(statuses)
        normalized_statuses = [
            normalize_status(status)
            for status in expanded_statuses
            if isinstance(status, str)
        ]
        normalized_statuses = [status for status in normalized_statuses if status]
        if not normalized_statuses:
            raise HTTPException(status_code=400, detail="At least one valid status must be provided")

    def filter_within_24h(patients: list) -> list:
        """Filter patients to only include those captured within the last 24 hours."""
        cutoff = datetime.now() - timedelta(hours=24)
        
        filtered = []
        for patient in patients:
            captured_at = patient.get("captured_at") or patient.get("capturedAt")
            if captured_at:
                if isinstance(captured_at, str):
                    # Parse ISO format timestamp
                    try:
                        ts = captured_at.replace("Z", "+00:00")
                        captured_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                    except ValueError:
                        captured_dt = None
                elif isinstance(captured_at, datetime):
                    captured_dt = captured_at.replace(tzinfo=None) if captured_at.tzinfo else captured_at
                else:
                    captured_dt = None
                
                if captured_dt and captured_dt >= cutoff:
                    filtered.append(patient)
            # If no captured_at, check created_at as fallback
            else:
                created_at = patient.get("created_at") or patient.get("createdAt")
                if created_at:
                    if isinstance(created_at, str):
                        try:
                            ts = created_at.replace("Z", "+00:00")
                            created_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                        except ValueError:
                            created_dt = None
                    elif isinstance(created_at, datetime):
                        created_dt = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
                    else:
                        created_dt = None
                    
                    if created_dt and created_dt >= cutoff:
                        filtered.append(patient)
        return filtered

    try:
        normalized_location_id = resolve_location_id(locationId, required=False)
        normalized_location_id = ensure_client_location_access(normalized_location_id, current_client)
        use_remote_reads = use_remote_api_for_reads()

        if use_remote_reads and normalized_location_id:
            # Fetch patients directly from production API
            patients_raw = await fetch_remote_patients(normalized_location_id, normalized_statuses, limit)
            
            # Apply 24h filter if 'active' shortcut was used
            if is_active_filter:
                patients_raw = filter_within_24h(patients_raw)
            
            # Remove excluded fields
            fields_to_exclude = ["status_class", "status_label", "captured_display", "source"]
            filtered_patients = [
                {k: v for k, v in patient.items() if k not in fields_to_exclude}
                for patient in patients_raw
            ]
            # Use by_alias=True to output camelCase field names
            return [PatientPayload(**patient).model_dump(exclude_none=True, exclude_unset=True, by_alias=True) for patient in filtered_patients]

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            patients_raw = get_local_patients(cursor, normalized_location_id, normalized_statuses, limit)
            
            # Apply 24h filter if 'active' shortcut was used
            if is_active_filter:
                patients_raw = filter_within_24h(patients_raw)
            
            # Remove excluded fields
            fields_to_exclude = ["status_class", "status_label", "captured_display", "source"]
            filtered_patients = [
                {k: v for k, v in patient.items() if k not in fields_to_exclude}
                for patient in patients_raw
            ]
            # Use by_alias=True to output camelCase field names
            return [PatientPayload(**patient).model_dump(exclude_none=True, exclude_unset=True, by_alias=True) for patient in filtered_patients]
        finally:
            cursor.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

