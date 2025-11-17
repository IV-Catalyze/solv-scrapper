#!/usr/bin/env python3
"""
Test script for the /encounter POST endpoint
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

def test_encounter_endpoint():
    """Test the /encounter POST endpoint"""
    
    print("=" * 60)
    print("Testing /encounter POST Endpoint")
    print("=" * 60)
    print()
    
    # Step 1: Check if API is running
    print("Step 1: Checking if API server is running...")
    try:
        response = requests.get(f"{API_BASE_URL}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API server is running")
        else:
            print(f"⚠️  API server returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server")
        print(f"   Make sure the server is running on {API_BASE_URL}")
        print("   Start it with: python api.py")
        return False
    except Exception as e:
        print(f"❌ Error checking API: {e}")
        return False
    
    print()
    
    # Step 2: Get authentication token
    print("Step 2: Getting authentication token...")
    try:
        token_response = requests.post(
            f"{API_BASE_URL}/auth/token",
            json={
                "client_id": "test-client",
                "expires_hours": 24
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            print("✅ Authentication token obtained")
            print(f"   Token expires at: {token_data.get('expires_at', 'N/A')}")
        else:
            print(f"❌ Failed to get token: {token_response.status_code}")
            print(f"   Response: {token_response.text}")
            # Try without auth (if auth is disabled)
            access_token = None
            print("   Attempting without authentication...")
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        access_token = None
        print("   Attempting without authentication...")
    
    print()
    
    # Step 3: Prepare test data
    print("Step 3: Preparing test encounter data...")
    test_encounter = {
        "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
        "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "patientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
        "encounterId": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
        "traumaType": "BURN",
        "chiefComplaints": [
            {
                "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
                "description": "Injury Head",
                "type": "trauma",
                "part": "head",
                "bodyParts": []
            },
            {
                "id": "726c47ab-a7d9-4836-a7a0-b5e99fc13ac7",
                "description": "Chemical burn",
                "type": "trauma",
                "part": "head",
                "bodyParts": []
            }
        ],
        "status": "COMPLETE",
        "createdBy": "randall.meeker@intellivisit.com",
        "startedAt": "2025-11-12T22:19:01.432Z"
    }
    print("✅ Test data prepared")
    print(f"   Encounter ID: {test_encounter['encounterId']}")
    print(f"   Patient ID: {test_encounter['patientId']}")
    print(f"   Trauma Type: {test_encounter['traumaType']}")
    print(f"   Chief Complaints: {len(test_encounter['chiefComplaints'])}")
    print()
    
    # Step 4: Send POST request
    print("Step 4: Sending POST request to /encounter...")
    headers = {
        "Content-Type": "application/json"
    }
    
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/encounter",
            json=test_encounter,
            headers=headers,
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ Encounter created successfully!")
            result = response.json()
            print()
            print("Response Data:")
            print(json.dumps(result, indent=2))
            print()
            
            # Verify response structure
            required_fields = ['id', 'encounter_id', 'patient_id', 'client_id']
            missing_fields = [field for field in required_fields if field not in result]
            if missing_fields:
                print(f"⚠️  Missing fields in response: {missing_fields}")
            else:
                print("✅ Response contains all required fields")
            
            return True
            
        elif response.status_code == 400:
            print("❌ Bad Request (400)")
            print(f"   Response: {response.text}")
            try:
                error_detail = response.json()
                print(f"   Detail: {error_detail.get('detail', 'N/A')}")
            except:
                pass
            return False
            
        elif response.status_code == 401:
            print("❌ Unauthorized (401)")
            print("   Authentication required. Check your token.")
            return False
            
        elif response.status_code == 500:
            print("❌ Internal Server Error (500)")
            print(f"   Response: {response.text}")
            try:
                error_detail = response.json()
                print(f"   Detail: {error_detail.get('detail', 'N/A')}")
            except:
                pass
            return False
            
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    
    print()
    print("=" * 60)
    print("Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    success = test_encounter_endpoint()
    sys.exit(0 if success else 1)

