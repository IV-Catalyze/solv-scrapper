#!/usr/bin/env python3
"""
Comprehensive test script for the simplified encounter endpoint on PRODUCTION API.
Tests POST /encounter with emrId and encounterPayload.
"""

import json
import requests
import sys
import hmac
import hashlib
import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Production API Base URL
BASE_URL = os.getenv("API_BASE_URL", "https://app-97926.on-aptible.com")

def generate_hmac_headers(method: str, path: str, body: any, secret_key: str) -> dict:
    """
    Generate HMAC authentication headers for a request.
    Matches the format used in tests/conftest.py
    """
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Convert body to bytes
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        # Use default JSON serialization to match requests library
        body_str = json.dumps(body)
        body_bytes = body_str.encode('utf-8')
    elif isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif isinstance(body, bytes):
        body_bytes = body
    elif body is None:
        body_bytes = b''
    else:
        body_bytes = b''
    
    # Calculate body hash
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    
    # Create canonical string
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
    # Generate HMAC signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    headers = {
        "X-Timestamp": timestamp,
        "X-Signature": signature_b64
    }
    
    # Only add Content-Type for requests with body
    if method.upper() in ["POST", "PUT", "PATCH"] and body_bytes:
        headers["Content-Type"] = "application/json"
    
    return headers

def test_encounter_endpoint(emr_id: str, encounter_payload_file: str, test_name: str = ""):
    """Test the POST /encounter endpoint."""
    
    # Load the encounter payload from file
    payload_path = Path(encounter_payload_file)
    if not payload_path.exists():
        print(f"❌ Error: File not found: {encounter_payload_file}")
        return False, None
    
    with open(payload_path, 'r') as f:
        encounter_payload = json.load(f)
    
    # Extract encounter_id from payload
    encounter_id = encounter_payload.get('id') or encounter_payload.get('encounterId') or encounter_payload.get('encounter_id')
    
    # Prepare request body
    request_body = {
        "emrId": emr_id,
        "encounterPayload": encounter_payload
    }
    
    print(f"\n🧪 {test_name}")
    print(f"   EMR ID: {emr_id}")
    print(f"   Encounter ID (from payload): {encounter_id}")
    print(f"   Payload file: {encounter_payload_file}")
    print(f"   Payload size: {len(json.dumps(encounter_payload))} bytes")
    
    # Get HMAC secret from environment
    hmac_secret = os.getenv(
        "INTELLIVISIT_STAGING_HMAC_SECRET",
        os.getenv("INTELLIVISIT_HMAC_SECRET", "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM")
    )
    
    if not hmac_secret:
        print("❌ Error: HMAC secret not found in environment variables")
        return False, None
    
    # Generate HMAC headers
    headers = generate_hmac_headers("POST", "/encounter", request_body, hmac_secret)
    
    try:
        # Make the request
        response = requests.post(
            f"{BASE_URL}/encounter",
            json=request_body,
            headers=headers,
            timeout=30
        )
        
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ Success! Encounter created/updated")
            response_data = response.json()
            
            # Verify response structure
            print(f"\n📦 Response Data:")
            emr_id_resp = response_data.get('emrId') or response_data.get('emr_id')
            encounter_id_resp = response_data.get('encounterId') or response_data.get('encounter_id')
            encounter_payload_resp = response_data.get('encounterPayload') or response_data.get('encounter_payload')
            
            print(f"   emrId: {emr_id_resp}")
            print(f"   encounterId: {encounter_id_resp}")
            
            # Verify response matches request
            if emr_id_resp != emr_id:
                print(f"   ⚠️  WARNING: Response emrId ({emr_id_resp}) doesn't match request ({emr_id})")
            else:
                print(f"   ✅ emrId matches request")
            
            if encounter_id_resp != str(encounter_id):
                print(f"   ⚠️  WARNING: Response encounterId ({encounter_id_resp}) doesn't match request ({encounter_id})")
            else:
                print(f"   ✅ encounterId matches request")
            
            if encounter_payload_resp:
                payload_keys = list(encounter_payload_resp.keys())[:10]
                print(f"   encounterPayload keys (first 10): {payload_keys}")
                print(f"   encounterPayload has {len(encounter_payload_resp)} top-level keys")
                
                # Verify payload contains original data
                if encounter_payload_resp.get('id') == encounter_id or encounter_payload_resp.get('encounterId') == encounter_id:
                    print(f"   ✅ encounterPayload contains original encounter ID")
                else:
                    print(f"   ⚠️  WARNING: encounterPayload doesn't contain original encounter ID")
            else:
                print(f"   ❌ ERROR: encounterPayload is missing from response")
                return False, response_data
            
            # Check for unexpected fields
            unexpected_fields = [k for k in response_data.keys() if k not in ['emrId', 'emr_id', 'encounterId', 'encounter_id', 'encounterPayload', 'encounter_payload']]
            if unexpected_fields:
                print(f"   ⚠️  WARNING: Unexpected fields in response: {unexpected_fields}")
            else:
                print(f"   ✅ Response contains only expected fields")
            
            return True, response_data
        else:
            print(f"❌ Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Detail: {error_data.get('detail', 'Unknown error')}")
                if 'detail' in error_data:
                    print(f"   Full error: {json.dumps(error_data, indent=2)}")
            except:
                print(f"   Response: {response.text[:500]}")
            return False, None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Could not connect to {BASE_URL}")
        print("   Check your internet connection and API availability")
        return False, None
    except requests.exceptions.Timeout:
        print(f"❌ Error: Request timed out after 30 seconds")
        return False, None
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_invalid_request():
    """Test with invalid request to verify error handling."""
    print(f"\n🧪 Test: Invalid Request (missing emrId)")
    
    request_body = {
        "encounterPayload": {"id": "test-123"}
    }
    
    hmac_secret = os.getenv(
        "INTELLIVISIT_STAGING_HMAC_SECRET",
        "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM"
    )
    
    headers = generate_hmac_headers("POST", "/encounter", request_body, hmac_secret)
    
    try:
        response = requests.post(
            f"{BASE_URL}/encounter",
            json=request_body,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 400:
            print(f"✅ Correctly rejected invalid request (400)")
            error_data = response.json()
            print(f"   Error detail: {error_data.get('detail', 'Unknown')}")
            return True
        else:
            print(f"❌ Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Main test function."""
    print("=" * 70)
    print("🧪 Testing Simplified Encounter Endpoint - PRODUCTION API")
    print("=" * 70)
    print(f"API Base URL: {BASE_URL}")
    
    results = []
    
    # Test 1: cough.json
    print("\n" + "=" * 70)
    success1, response1 = test_encounter_endpoint(
        "EMR_TEST_001", 
        "cough.json",
        "Test 1: Creating encounter from cough.json"
    )
    results.append(("Test 1 (cough.json)", success1))
    
    # Test 2: injury head.json
    print("\n" + "=" * 70)
    success2, response2 = test_encounter_endpoint(
        "EMR_TEST_002", 
        "injury head.json",
        "Test 2: Creating encounter from injury head.json"
    )
    results.append(("Test 2 (injury head.json)", success2))
    
    # Test 3: Invalid request
    print("\n" + "=" * 70)
    success3 = test_invalid_request()
    results.append(("Test 3 (invalid request)", success3))
    
    # Test 4: Update existing encounter (same encounter_id, different emr_id)
    if success1:
        print("\n" + "=" * 70)
        print("Test 4: Updating existing encounter (same encounter_id)")
        success4, response4 = test_encounter_endpoint(
            "EMR_TEST_001_UPDATED", 
            "cough.json",
            "Test 4: Updating encounter with new emrId"
        )
        results.append(("Test 4 (update existing)", success4))
    
    # Summary
    print("\n" + "=" * 70)
    print("📋 Test Summary")
    print("=" * 70)
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

