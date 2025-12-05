#!/usr/bin/env python3
"""
Test script for the simplified encounter endpoint.
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

# Base URL for the API
BASE_URL = "http://localhost:8000"

def generate_hmac_headers(method: str, path: str, body: any, secret_key: str) -> dict:
    """
    Generate HMAC authentication headers for a request.
    Matches the format used in tests/conftest.py
    """
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Convert body to bytes
    # For GET requests, body should be empty bytes
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        # Use default JSON serialization to match requests library
        # requests uses json.dumps() with default settings (includes spaces)
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

def test_encounter_endpoint(emr_id: str, encounter_payload_file: str):
    """Test the POST /encounter endpoint."""
    
    # Load the encounter payload from file
    payload_path = Path(encounter_payload_file)
    if not payload_path.exists():
        print(f"❌ Error: File not found: {encounter_payload_file}")
        return False
    
    with open(payload_path, 'r') as f:
        encounter_payload = json.load(f)
    
    # Extract encounter_id from payload
    encounter_id = encounter_payload.get('id') or encounter_payload.get('encounterId') or encounter_payload.get('encounter_id')
    
    # Prepare request body
    request_body = {
        "emrId": emr_id,
        "encounterPayload": encounter_payload
    }
    
    print(f"\n🧪 Testing POST /encounter")
    print(f"   EMR ID: {emr_id}")
    print(f"   Encounter ID (from payload): {encounter_id}")
    print(f"   Payload file: {encounter_payload_file}")
    
    # Get HMAC secret from environment or use default for testing
    hmac_secret = os.getenv(
        "INTELLIVISIT_STAGING_HMAC_SECRET",
        os.getenv("INTELLIVISIT_HMAC_SECRET", "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM")
    )
    
    # Generate HMAC headers - pass dict, function will serialize it correctly
    headers = generate_hmac_headers("POST", "/encounter", request_body, hmac_secret)
    
    try:
        # Make the request - use json parameter so requests serializes it
        # The HMAC was calculated on the same serialization
        response = requests.post(
            f"{BASE_URL}/encounter",
            json=request_body,
            headers=headers,
            timeout=10
        )
        
        print(f"\n📊 Response Status: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ Success! Encounter created/updated")
            response_data = response.json()
            print(f"\n📦 Response Data:")
            print(f"   emrId: {response_data.get('emrId') or response_data.get('emr_id')}")
            print(f"   encounterPayload keys: {list(response_data.get('encounterPayload', {}).keys())[:5]}...")
            # Verify encounterId is NOT in response
            if 'encounterId' in response_data or 'encounter_id' in response_data:
                print("⚠️  Warning: encounterId should not be in response!")
                return False
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Detail: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Could not connect to {BASE_URL}")
        print("   Make sure the server is running: python3 -m uvicorn app.api.routes:app --host 0.0.0.0 --port 8000 --reload")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Main test function."""
    print("=" * 60)
    print("🧪 Testing Simplified Encounter Endpoint")
    print("=" * 60)
    
    # Test with cough.json
    print("\n" + "=" * 60)
    print("Test 1: Creating encounter from cough.json")
    print("=" * 60)
    success1 = test_encounter_endpoint("EMR12345", "cough.json")
    
    # Test with injury head.json
    print("\n" + "=" * 60)
    print("Test 2: Creating encounter from injury head.json")
    print("=" * 60)
    success2 = test_encounter_endpoint("EMR12346", "injury head.json")
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Test Summary")
    print("=" * 60)
    print(f"Test 1 (cough.json): {'✅ PASSED' if success1 else '❌ FAILED'}")
    print(f"Test 2 (injury head.json): {'✅ PASSED' if success2 else '❌ FAILED'}")
    
    if success1 and success2:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

