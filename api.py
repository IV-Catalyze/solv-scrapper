#!/usr/bin/env python3
"""
FastAPI application to expose patient data via REST API.
"""

import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: Required packages not installed. Please run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

app = FastAPI(
    title="Patient Data API",
    description="API to access patient records from the database",
    version="1.0.0"
)


def get_db_connection():
    """Get PostgreSQL database connection from environment variables."""
    import getpass
    default_user = os.getenv('USER', os.getenv('USERNAME', getpass.getuser()))
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'solvhealth_patients'),
        'user': os.getenv('DB_USER', default_user),
        'password': os.getenv('DB_PASSWORD', '')
    }
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection error: {str(e)}"
        )


def format_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format patient record for JSON response."""
    formatted = {}
    for key, value in record.items():
        # Convert datetime objects to ISO format strings
        if isinstance(value, datetime):
            formatted[key] = value.isoformat()
        # Convert date objects to ISO format strings
        elif hasattr(value, 'isoformat') and hasattr(value, 'year'):
            formatted[key] = value.isoformat()
        else:
            formatted[key] = value
    return formatted


def build_patient_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build patient response payload in normalized structure."""
    captured = record.get("captured_at")
    if isinstance(captured, datetime):
        captured = captured.isoformat()

    payload = {
        "emr_id": record.get("emr_id"),
        "booking_id": record.get("booking_id"),
        "booking_number": record.get("booking_number"),
        "patient_number": record.get("patient_number"),
        "location_id": record.get("location_id"),
        "location_name": record.get("location_name"),
        "legalFirstName": record.get("legal_first_name"),
        "legalLastName": record.get("legal_last_name"),
        "dob": record.get("dob"),
        "mobilePhone": record.get("mobile_phone"),
        "sexAtBirth": record.get("sex_at_birth"),
        "captured_at": captured,
        "reasonForVisit": record.get("reason_for_visit")
    }

    return payload


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Patient Data API",
        "version": "1.0.0",
        "endpoints": {
            "GET /patient/{emr_id}": "Get patient record by EMR ID",
            "GET /patients?locationId=...": "List patient records filtered by location ID"
        }
    }


@app.get("/patient/{emr_id}")
async def get_patient_by_emr_id(emr_id: str):
    """
    Get a patient record by EMR ID.
    
    Returns the most recent patient record matching the given EMR ID.
    If multiple records exist, returns the one with the latest captured_at timestamp.
    
    Args:
        emr_id: The EMR ID of the patient to retrieve
        
    Returns:
        Patient record as JSON, or 404 if not found
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
        
        cursor.execute(query, (emr_id,))
        record = cursor.fetchone()
        
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with EMR ID '{emr_id}' not found"
            )
        
        response_payload = build_patient_payload(record)

        return JSONResponse(content=response_payload)
        
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


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv('API_PORT', '8000'))
    host = os.getenv('API_HOST', '0.0.0.0')
    
    uvicorn.run(app, host=host, port=port)


@app.get("/patients")
async def list_patients(locationId: Optional[str] = None, limit: Optional[int] = None):
    """
    List patient records filtered by location ID.
    Returns records ordered by captured_at descending.
    """
    if not locationId:
        raise HTTPException(status_code=400, detail="locationId query parameter is required")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT 
                id,
                emr_id,
                booking_id,
                booking_number,
                patient_number,
                location_id,
                location_name,
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
            WHERE location_id = %s AND emr_id IS NOT NULL
            ORDER BY captured_at DESC
        """

        params: List[Any] = [locationId]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, tuple(params))
        records = cursor.fetchall()

        payload = [build_patient_payload(record) for record in records]
        return JSONResponse(content=payload)

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

