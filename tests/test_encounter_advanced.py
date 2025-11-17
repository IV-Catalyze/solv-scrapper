#!/usr/bin/env python3
"""
Advanced tests for the /encounter POST endpoint
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

def get_db_connection():
    """Get database connection"""
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(database_url)
    else:
        return psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'solvhealth_patients'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', '')
        )

def test_update_existing_encounter():
    """Test that updating an existing encounter works"""
    print("\n" + "=" * 60)
    print("Test 1: Updating Existing Encounter")
    print("=" * 60)
    
    encounter_data = {
        "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
        "traumaType": "BURN",
        "chiefComplaints": [
            {
                "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
                "description": "Injury Head - UPDATED",
                "type": "trauma",
                "part": "head",
                "bodyParts": []
            }
        ],
        "status": "IN_PROGRESS",  # Changed from COMPLETE
        "createdBy": "test.user@example.com",  # Changed
        "startedAt": "2025-11-12T22:19:01.432Z"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/encounter",
            json=encounter_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 201:
            result = response.json()
            print("✅ Encounter updated successfully")
            print(f"   Status changed to: {result.get('status')}")
            print(f"   Created by: {result.get('created_by')}")
            print(f"   Chief complaints count: {len(result.get('chief_complaints', []))}")
            print(f"   Updated at: {result.get('updated_at')}")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_missing_patient_id():
    """Test that missing patientId returns 400"""
    print("\n" + "=" * 60)
    print("Test 2: Missing Required Field (patientId)")
    print("=" * 60)
    
    encounter_data = {
        "id": "test-missing-patient-id",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "encounterId": "test-missing-patient-id",
        # patientId is missing
        "traumaType": "BURN",
        "status": "COMPLETE"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/encounter",
            json=encounter_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 422:  # Pydantic validation error
            print("✅ Correctly rejected missing patientId (422)")
            return True
        elif response.status_code == 400:
            error = response.json()
            if "patientId" in error.get('detail', '').lower():
                print("✅ Correctly rejected missing patientId (400)")
                return True
            else:
                print(f"⚠️  Got 400 but error message doesn't mention patientId")
                print(f"   {error.get('detail', 'N/A')}")
                return False
        else:
            print(f"❌ Expected 400 or 422, got {response.status_code}")
            print(f"   {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_database_persistence():
    """Test that data is actually saved to database"""
    print("\n" + "=" * 60)
    print("Test 3: Database Persistence Verification")
    print("=" * 60)
    
    encounter_id = "e170d6fc-ae47-4ecd-b648-69f074505c4d"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM encounters WHERE encounter_id = %s",
            (encounter_id,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            print("✅ Encounter found in database")
            print(f"   Encounter ID: {result[1]}")
            print(f"   Patient ID: {result[3]}")
            print(f"   Status: {result[6]}")
            print(f"   Trauma Type: {result[4]}")
            print(f"   Created At: {result[9]}")
            print(f"   Updated At: {result[10]}")
            return True
        else:
            print("❌ Encounter not found in database")
            return False
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_empty_chief_complaints():
    """Test with empty chief complaints array"""
    print("\n" + "=" * 60)
    print("Test 4: Empty Chief Complaints")
    print("=" * 60)
    
    encounter_data = {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "encounterId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "traumaType": "BURN",
        "chiefComplaints": [],  # Empty array
        "status": "COMPLETE",
        "startedAt": "2025-11-12T22:19:01.432Z"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/encounter",
            json=encounter_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 201:
            result = response.json()
            print("✅ Encounter created with empty chief complaints")
            print(f"   Chief complaints: {result.get('chief_complaints', [])}")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Advanced Encounter Endpoint Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Update Existing", test_update_existing_encounter()))
    results.append(("Missing patientId", test_missing_patient_id()))
    results.append(("Database Persistence", test_database_persistence()))
    results.append(("Empty Chief Complaints", test_empty_chief_complaints()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

