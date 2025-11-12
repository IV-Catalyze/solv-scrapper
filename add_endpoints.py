#!/usr/bin/env python3
"""Script to add patient creation endpoints to api.py"""

with open('api.py', 'r') as f:
    content = f.read()

# Endpoints code to add
endpoints_code = '''


@app.post(
    "/patients/create",
    tags=["Patients"],
    summary="Create patient record(s)",
    response_model=Dict[str, Any],
    responses={
        201: {"description": "Patient record(s) created successfully."},
        400: {"description": "Invalid request data."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Database or server error while saving the record(s)."},
    },
)
async def create_patient(
    patient_data: PatientCreateRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    Create a single patient record from the provided data.
    
    This endpoint accepts patient data in JSON format and saves it to the database.
    The data will be normalized and validated before insertion.
    
    **Example request body:**
    ```json
    {
        "emr_id": "12345",
        "location_id": "AXjwbE",
        "location_name": "Exer Urgent Care - Demo",
        "legalFirstName": "John",
        "legalLastName": "Doe",
        "dob": "01/15/1990",
        "mobilePhone": "(555) 123-4567",
        "sexAtBirth": "Male",
        "reasonForVisit": "Fever",
        "status": "checked_in"
    }
    ```
    
    Requires authentication via Bearer token or API key.
    """
    if not normalize_patient_record or not insert_patients:
        raise HTTPException(
            status_code=503,
            detail="Patient save functionality unavailable"
        )
    
    conn = None
    try:
        # Convert Pydantic model to dict
        patient_dict = patient_data.model_dump(exclude_none=True)
        
        # Normalize the patient record
        normalized = normalize_patient_record(patient_dict)
        
        # Check if emr_id is required (based on schema, it's UNIQUE NOT NULL)
        if not normalized.get('emr_id'):
            raise HTTPException(
                status_code=400,
                detail="emr_id is required. Please provide an EMR identifier for the patient."
            )
        
        # Ensure location_id is provided (required by schema)
        if not normalized.get('location_id'):
            raise HTTPException(
                status_code=400,
                detail="location_id is required. Please provide a location identifier."
            )
        
        conn = get_db_connection()
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
                    "emr_id": normalized['emr_id'],
                    "status": "updated"
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create patient record"
                )
        
        return {
            "message": "Patient record created successfully",
            "emr_id": normalized['emr_id'],
            "status": "created",
            "inserted_count": inserted_count
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


@app.post(
    "/patients/batch",
    tags=["Patients"],
    summary="Create multiple patient records",
    response_model=Dict[str, Any],
    responses={
        201: {"description": "Patient records created successfully."},
        400: {"description": "Invalid request data."},
        401: {"description": "Authentication required. Provide a Bearer token or API key."},
        500: {"description": "Database or server error while saving the records."},
    },
)
async def create_patients_batch(
    batch_data: PatientBatchRequest,
    current_client: TokenData = get_auth_dependency()
) -> Dict[str, Any]:
    """
    Create multiple patient records from a batch of data.
    
    This endpoint accepts an array of patient records and saves them to the database.
    Each record will be normalized and validated before insertion.
    
    **Example request body:**
    ```json
    {
        "patients": [
            {
                "emr_id": "12345",
                "location_id": "AXjwbE",
                "legalFirstName": "John",
                "legalLastName": "Doe",
                "dob": "01/15/1990"
            },
            {
                "emr_id": "12346",
                "location_id": "AXjwbE",
                "legalFirstName": "Jane",
                "legalLastName": "Smith",
                "dob": "02/20/1985"
            }
        ]
    }
    ```
    
    Requires authentication via Bearer token or API key.
    """
    if not normalize_patient_record or not insert_patients:
        raise HTTPException(
            status_code=503,
            detail="Patient save functionality unavailable"
        )
    
    if not batch_data.patients:
        raise HTTPException(
            status_code=400,
            detail="No patient records provided in the request"
        )
    
    conn = None
    try:
        # Convert Pydantic models to dicts and normalize
        normalized_patients = []
        errors = []
        
        for idx, patient_data in enumerate(batch_data.patients):
            try:
                patient_dict = patient_data.model_dump(exclude_none=True)
                normalized = normalize_patient_record(patient_dict)
                
                # Validate required fields
                if not normalized.get('emr_id'):
                    errors.append(f"Record {idx + 1}: emr_id is required")
                    continue
                
                if not normalized.get('location_id'):
                    errors.append(f"Record {idx + 1}: location_id is required")
                    continue
                
                normalized_patients.append(normalized)
            except Exception as e:
                errors.append(f"Record {idx + 1}: {str(e)}")
        
        if errors and not normalized_patients:
            raise HTTPException(
                status_code=400,
                detail=f"All records failed validation: {'; '.join(errors)}"
            )
        
        if not normalized_patients:
            raise HTTPException(
                status_code=400,
                detail="No valid patient records to insert"
            )
        
        conn = get_db_connection()
        inserted_count = insert_patients(conn, normalized_patients, on_conflict='update')
        
        response = {
            "message": f"Processed {len(batch_data.patients)} patient record(s)",
            "inserted_count": inserted_count,
            "total_provided": len(batch_data.patients),
            "valid_records": len(normalized_patients)
        }
        
        if errors:
            response["errors"] = errors
            response["status"] = "partial_success"
        else:
            response["status"] = "success"
        
        return response
        
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

'''

# Insert before if __name__ == "__main__":
content = content.replace(
    '\n\nif __name__ == "__main__":',
    endpoints_code + '\n\nif __name__ == "__main__":'
)

with open('api.py', 'w') as f:
    f.write(content)

print('Added endpoints successfully')

