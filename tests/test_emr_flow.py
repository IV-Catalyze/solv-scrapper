#!/usr/bin/env python3
"""
Test script to verify EMR ID detection and API sending flow.
This simulates the workflow when an EMR ID is found in an API response.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("⚠️  httpx not installed. Install with: pip install httpx")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Simulate the send_patient_to_api function
async def send_patient_to_api(patient_data: dict) -> bool:
    """Send patient data to the API endpoint when EMR ID is available."""
    if not patient_data.get('emr_id'):
        print("❌ No EMR ID in patient data")
        return False
    
    # Get API URL from environment variables
    api_host = os.getenv('API_HOST', 'localhost')
    api_port = os.getenv('API_PORT', '8000')
    api_url = f"http://{api_host}:{api_port}/patients/create"
    
    # Get API token/key if authentication is enabled
    api_token = os.getenv('API_TOKEN')
    api_key = os.getenv('API_KEY')
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Add authentication if available
    if api_token:
        headers['Authorization'] = f'Bearer {api_token}'
    elif api_key:
        headers['X-API-Key'] = api_key
    
    # Prepare patient data for API (convert to API format)
    api_payload = {
        'emr_id': patient_data.get('emr_id') or '',
        'booking_id': patient_data.get('booking_id') or '',
        'booking_number': patient_data.get('booking_number') or '',
        'patient_number': patient_data.get('patient_number') or '',
        'location_id': patient_data.get('location_id') or '',
        'location_name': patient_data.get('location_name') or '',
        'legalFirstName': patient_data.get('legalFirstName') or patient_data.get('legal_first_name') or '',
        'legalLastName': patient_data.get('legalLastName') or patient_data.get('legal_last_name') or '',
        'dob': patient_data.get('dob') or '',
        'mobilePhone': patient_data.get('mobilePhone') or patient_data.get('mobile_phone') or '',
        'sexAtBirth': patient_data.get('sexAtBirth') or patient_data.get('sex_at_birth') or '',
        'reasonForVisit': patient_data.get('reasonForVisit') or patient_data.get('reason_for_visit') or '',
        'status': patient_data.get('status') or 'checked_in',
        'captured_at': patient_data.get('captured_at') or datetime.now().isoformat()
    }
    
    # Remove empty strings and convert to None for optional fields
    api_payload = {k: v if v else None for k, v in api_payload.items()}
    
    print(f"\n{'='*60}")
    print(f"🚀 TEST: Sending Patient Data to API")
    print(f"{'='*60}")
    print(f"   URL: {api_url}")
    print(f"   Method: POST")
    print(f"   Payload:")
    print(json.dumps(api_payload, indent=2, default=str))
    print(f"   Headers: {json.dumps(headers, indent=2)}")
    print(f"{'='*60}\n")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"   🔄 Sending HTTP request...")
            response = await client.post(api_url, json=api_payload, headers=headers)
            print(f"   📥 Response received: {response.status_code}")
            
            if response.status_code in [200, 201]:
                result = response.json()
                print(f"   ✅ Patient data sent to API successfully!")
                print(f"   Response: {json.dumps(result, indent=2)}")
                return True
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get('detail', error_detail)
                except:
                    pass
                print(f"   ❌ API returned error {response.status_code}: {error_detail}")
                return False
                
    except httpx.TimeoutException:
        print(f"   ❌ API request timed out after 30 seconds")
        return False
    except httpx.RequestError as e:
        print(f"   ❌ API request error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error sending to API: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_emr_flow():
    """Test the complete EMR ID flow."""
    print("\n" + "="*60)
    print("🧪 TESTING EMR ID FLOW")
    print("="*60)
    
    # Simulate patient data with EMR ID (like what would be extracted from API response)
    test_patient_data = {
        'emr_id': 'TEST_EMR_12345',
        'booking_id': 'test_booking_123',
        'booking_number': 'BK-12345',
        'patient_number': 'PN-67890',
        'location_id': 'AXjwbE',
        'location_name': 'Test Location',
        'legalFirstName': 'John',
        'legalLastName': 'Doe',
        'dob': '1990-01-01',
        'mobilePhone': '+1234567890',
        'sexAtBirth': 'M',
        'reasonForVisit': 'Test visit',
        'status': 'checked_in',
        'captured_at': datetime.now().isoformat()
    }
    
    print(f"\n📋 Test Patient Data:")
    print(json.dumps(test_patient_data, indent=2, default=str))
    
    # Check API availability
    api_host = os.getenv('API_HOST', 'localhost')
    api_port = os.getenv('API_PORT', '8000')
    api_url = f"http://{api_host}:{api_port}"
    
    print(f"\n🔍 Checking API availability at {api_url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{api_url}/patients")
            if response.status_code == 200:
                print(f"   ✅ API is available and responding")
            else:
                print(f"   ⚠️  API responded with status {response.status_code}")
    except Exception as e:
        print(f"   ❌ API is not available: {e}")
        print(f"   💡 Make sure the API server is running on {api_url}")
        return False
    
    # Test sending patient data
    print(f"\n🚀 Testing send_patient_to_api()...")
    success = await send_patient_to_api(test_patient_data)
    
    if success:
        print(f"\n✅ TEST PASSED: Patient data successfully sent to API!")
    else:
        print(f"\n❌ TEST FAILED: Could not send patient data to API")
    
    return success


if __name__ == "__main__":
    asyncio.run(test_emr_flow())

