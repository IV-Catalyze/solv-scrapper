#!/usr/bin/env python3
"""
Comprehensive test script for the queue endpoints
Tests:
- Automatic queue creation when encounter is created
- GET /queue with various filters
- POST /queue to update experityAction
- Error handling and edge cases
"""

import os
import sys
import json
import requests
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
CLIENT_ID = os.getenv('API_CLIENT_ID', 'Stage-1c3dca8d-730f-4a32-9221-4e4277903505')

# Test results tracking
test_results = {
    'passed': 0,
    'failed': 0,
    'tests': []
}

def log_test(name, passed, message=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if message:
        print(f"   {message}")
    test_results['tests'].append({
        'name': name,
        'passed': passed,
        'message': message
    })
    if passed:
        test_results['passed'] += 1
    else:
        test_results['failed'] += 1

def get_auth_token():
    """Get authentication token"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/token",
            json={"client_id": CLIENT_ID, "expires_hours": 24},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        return None
    except Exception as e:
        print(f"⚠️  Could not get auth token: {e}")
        return None

def check_api_running():
    """Check if API server is running"""
    try:
        response = requests.get(f"{API_BASE_URL}/docs", timeout=5)
        return response.status_code == 200
    except:
        return False

def test_create_encounter_with_queue(access_token):
    """Test creating an encounter and verify queue is auto-created"""
    print("\n" + "=" * 60)
    print("Test 1: Create Encounter (should auto-create queue entry)")
    print("=" * 60)
    
    # Generate unique IDs for this test
    encounter_id = str(uuid.uuid4())
    
    test_encounter = {
        "id": encounter_id,
        "clientId": CLIENT_ID,
        "encounterId": encounter_id,
        "traumaType": "BURN",
        "chiefComplaints": [
            {
                "id": str(uuid.uuid4()),
                "description": "Test Injury Head",
                "type": "trauma",
                "part": "head",
                "bodyParts": []
            },
            {
                "id": str(uuid.uuid4()),
                "description": "Test Chemical burn",
                "type": "trauma",
                "part": "head",
                "bodyParts": []
            }
        ],
        "status": "COMPLETE",
        "createdBy": "test@example.com",
        "startedAt": "2025-01-15T10:00:00.000Z"
    }
    
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        # Create encounter
        response = requests.post(
            f"{API_BASE_URL}/encounter",
            json=test_encounter,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 201:
            log_test("Create encounter", True, f"Encounter {encounter_id} created")
            
            # Verify queue was created
            queue_response = requests.get(
                f"{API_BASE_URL}/queue?encounter_id={encounter_id}",
                headers=headers,
                timeout=10
            )
            
            if queue_response.status_code == 200:
                queue_data = queue_response.json()
                if queue_data and len(queue_data) > 0:
                    queue_entry = queue_data[0]
                    log_test("Queue auto-created", True, f"Queue ID: {queue_entry.get('queue_id')}")
                    
                    # Verify queue structure
                    required_fields = ['queue_id', 'encounter_id', 'status', 'parsed_payload']
                    missing = [f for f in required_fields if f not in queue_entry]
                    if missing:
                        log_test("Queue structure", False, f"Missing fields: {missing}")
                    else:
                        log_test("Queue structure", True, "All required fields present")
                    
                    # Verify parsed_payload has experityAction = null
                    parsed = queue_entry.get('parsed_payload', {})
                    if parsed.get('experityAction') is None:
                        log_test("experityAction initialized", True, "experityAction is null as expected")
                    else:
                        log_test("experityAction initialized", False, f"experityAction is {parsed.get('experityAction')}")
                    
                    # Verify status is PENDING
                    if queue_entry.get('status') == 'PENDING':
                        log_test("Initial status", True, "Status is PENDING")
                    else:
                        log_test("Initial status", False, f"Status is {queue_entry.get('status')}")
                    
                    # Verify attempts is 0
                    if queue_entry.get('attempts') == 0:
                        log_test("Initial attempts", True, "Attempts is 0")
                    else:
                        log_test("Initial attempts", False, f"Attempts is {queue_entry.get('attempts')}")
                    
                    return encounter_id, queue_entry.get('queue_id')
                else:
                    log_test("Queue auto-created", False, "Queue entry not found after encounter creation")
                    return encounter_id, None
            else:
                log_test("Queue auto-created", False, f"Failed to fetch queue: {queue_response.status_code}")
                return encounter_id, None
        else:
            log_test("Create encounter", False, f"Status {response.status_code}: {response.text}")
            return None, None
            
    except Exception as e:
        log_test("Create encounter", False, f"Exception: {str(e)}")
        return None, None

def test_get_queue_by_id(access_token, queue_id):
    """Test GET /queue?queue_id=..."""
    print("\n" + "=" * 60)
    print("Test 2: GET /queue by queue_id")
    print("=" * 60)
    
    if not queue_id:
        log_test("GET queue by queue_id", False, "No queue_id available (skipped)")
        return
    
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/queue?queue_id={queue_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and data[0].get('queue_id') == queue_id:
                log_test("GET queue by queue_id", True, f"Found queue entry: {queue_id}")
            else:
                log_test("GET queue by queue_id", False, "Queue entry not found or wrong ID")
        else:
            log_test("GET queue by queue_id", False, f"Status {response.status_code}: {response.text}")
    except Exception as e:
        log_test("GET queue by queue_id", False, f"Exception: {str(e)}")

def test_get_queue_by_encounter_id(access_token, encounter_id):
    """Test GET /queue?encounter_id=..."""
    print("\n" + "=" * 60)
    print("Test 3: GET /queue by encounter_id")
    print("=" * 60)
    
    if not encounter_id:
        log_test("GET queue by encounter_id", False, "No encounter_id available (skipped)")
        return
    
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/queue?encounter_id={encounter_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and data[0].get('encounter_id') == encounter_id:
                log_test("GET queue by encounter_id", True, f"Found queue entry for encounter: {encounter_id}")
            else:
                log_test("GET queue by encounter_id", False, "Queue entry not found or wrong encounter_id")
        else:
            log_test("GET queue by encounter_id", False, f"Status {response.status_code}: {response.text}")
    except Exception as e:
        log_test("GET queue by encounter_id", False, f"Exception: {str(e)}")

def test_get_queue_by_status(access_token):
    """Test GET /queue?status=PENDING"""
    print("\n" + "=" * 60)
    print("Test 4: GET /queue by status")
    print("=" * 60)
    
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        # Test PENDING status
        response = requests.get(
            f"{API_BASE_URL}/queue?status=PENDING",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            all_pending = all(item.get('status') == 'PENDING' for item in data)
            if all_pending:
                log_test("GET queue by status=PENDING", True, f"Found {len(data)} PENDING entries")
            else:
                log_test("GET queue by status=PENDING", False, "Some entries don't have PENDING status")
        else:
            log_test("GET queue by status=PENDING", False, f"Status {response.status_code}: {response.text}")
        
        # Test invalid status
        response = requests.get(
            f"{API_BASE_URL}/queue?status=INVALID",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 400:
            log_test("GET queue invalid status", True, "Correctly rejected invalid status")
        else:
            log_test("GET queue invalid status", False, f"Expected 400, got {response.status_code}")
            
    except Exception as e:
        log_test("GET queue by status", False, f"Exception: {str(e)}")

def test_get_queue_with_limit(access_token):
    """Test GET /queue with limit parameter"""
    print("\n" + "=" * 60)
    print("Test 5: GET /queue with limit")
    print("=" * 60)
    
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        # Get all entries
        response_all = requests.get(
            f"{API_BASE_URL}/queue",
            headers=headers,
            timeout=10
        )
        
        if response_all.status_code == 200:
            all_data = response_all.json()
            total_count = len(all_data)
            
            # Get with limit
            response_limited = requests.get(
                f"{API_BASE_URL}/queue?limit=2",
                headers=headers,
                timeout=10
            )
            
            if response_limited.status_code == 200:
                limited_data = response_limited.json()
                if len(limited_data) <= 2:
                    log_test("GET queue with limit", True, f"Limit works: {len(limited_data)} <= 2 (total: {total_count})")
                else:
                    log_test("GET queue with limit", False, f"Limit not working: {len(limited_data)} > 2")
            else:
                log_test("GET queue with limit", False, f"Status {response_limited.status_code}")
        else:
            log_test("GET queue with limit", False, f"Failed to get all entries: {response_all.status_code}")
            
    except Exception as e:
        log_test("GET queue with limit", False, f"Exception: {str(e)}")

def test_update_experity_action(access_token, queue_id, encounter_id):
    """Test POST /queue to update experityAction"""
    print("\n" + "=" * 60)
    print("Test 6: POST /queue to update experityAction")
    print("=" * 60)
    
    if not queue_id and not encounter_id:
        log_test("Update experityAction", False, "No queue_id or encounter_id available (skipped)")
        return
    
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    experity_action = {
        "template": "Chest",
        "bodyAreaKey": "Chest",
        "coordKey": "CHEST_PARENT",
        "bodyMapSide": "front",
        "ui": {
            "bodyMapClick": {
                "x": 183,
                "y": 556
            },
            "bodyPartId": 3
        },
        "mainProblem": "Cough",
        "notesTemplateKey": "CHEST_TEMPLATE_B",
        "notesPayload": {
            "quality": ["Chest tightness"],
            "severity": 3
        }
    }
    
    # Test with queue_id
    if queue_id:
        try:
            update_data = {
                "queue_id": queue_id,
                "experityAction": experity_action
            }
            
            response = requests.post(
                f"{API_BASE_URL}/queue",
                json=update_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                parsed = result.get('parsed_payload', {})
                if parsed.get('experityAction') == experity_action:
                    log_test("Update experityAction by queue_id", True, "experityAction updated successfully")
                else:
                    log_test("Update experityAction by queue_id", False, "experityAction not updated correctly")
            else:
                log_test("Update experityAction by queue_id", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            log_test("Update experityAction by queue_id", False, f"Exception: {str(e)}")
    
    # Test with encounter_id
    if encounter_id:
        try:
            update_data = {
                "encounter_id": encounter_id,
                "experityAction": experity_action
            }
            
            response = requests.post(
                f"{API_BASE_URL}/queue",
                json=update_data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                parsed = result.get('parsed_payload', {})
                if parsed.get('experityAction') == experity_action:
                    log_test("Update experityAction by encounter_id", True, "experityAction updated successfully")
                else:
                    log_test("Update experityAction by encounter_id", False, "experityAction not updated correctly")
            else:
                log_test("Update experityAction by encounter_id", False, f"Status {response.status_code}: {response.text}")
        except Exception as e:
            log_test("Update experityAction by encounter_id", False, f"Exception: {str(e)}")

def test_error_cases(access_token):
    """Test error handling"""
    print("\n" + "=" * 60)
    print("Test 7: Error Handling")
    print("=" * 60)
    
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    # Test POST /queue without queue_id or encounter_id
    try:
        response = requests.post(
            f"{API_BASE_URL}/queue",
            json={"experityAction": {}},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 400 or response.status_code == 422:
            log_test("POST /queue without identifiers", True, "Correctly rejected missing identifiers")
        else:
            log_test("POST /queue without identifiers", False, f"Expected 400/422, got {response.status_code}")
    except Exception as e:
        log_test("POST /queue without identifiers", False, f"Exception: {str(e)}")
    
    # Test POST /queue with non-existent queue_id
    try:
        fake_id = str(uuid.uuid4())
        response = requests.post(
            f"{API_BASE_URL}/queue",
            json={"queue_id": fake_id, "experityAction": {}},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 404:
            log_test("POST /queue with non-existent ID", True, "Correctly returned 404")
        else:
            log_test("POST /queue with non-existent ID", False, f"Expected 404, got {response.status_code}")
    except Exception as e:
        log_test("POST /queue with non-existent ID", False, f"Exception: {str(e)}")
    
    # Test GET /queue with non-existent queue_id
    try:
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{API_BASE_URL}/queue?queue_id={fake_id}",
            headers=headers if access_token else {},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if len(data) == 0:
                log_test("GET /queue with non-existent ID", True, "Correctly returned empty list")
            else:
                log_test("GET /queue with non-existent ID", False, "Should return empty list")
        else:
            log_test("GET /queue with non-existent ID", False, f"Expected 200, got {response.status_code}")
    except Exception as e:
        log_test("GET /queue with non-existent ID", False, f"Exception: {str(e)}")

def test_get_queue_all(access_token):
    """Test GET /queue without filters (get all)"""
    print("\n" + "=" * 60)
    print("Test 8: GET /queue (all entries)")
    print("=" * 60)
    
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/queue",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            log_test("GET /queue (all)", True, f"Retrieved {len(data)} queue entries")
            
            # Verify structure of first entry if any
            if data and len(data) > 0:
                entry = data[0]
                required_fields = ['queue_id', 'encounter_id', 'status', 'parsed_payload', 'attempts']
                missing = [f for f in required_fields if f not in entry]
                if missing:
                    log_test("Queue entry structure", False, f"Missing fields: {missing}")
                else:
                    log_test("Queue entry structure", True, "All required fields present")
        else:
            log_test("GET /queue (all)", False, f"Status {response.status_code}: {response.text}")
    except Exception as e:
        log_test("GET /queue (all)", False, f"Exception: {str(e)}")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Queue Endpoints Test Suite")
    print("=" * 60)
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Client ID: {CLIENT_ID}")
    print()
    
    # Check if API is running
    if not check_api_running():
        print("❌ API server is not running!")
        print(f"   Make sure the server is running on {API_BASE_URL}")
        print("   Start it with: python -m app.api.routes")
        sys.exit(1)
    
    print("✅ API server is running")
    print()
    
    # Get auth token
    access_token = get_auth_token()
    if access_token:
        print("✅ Authentication token obtained")
    else:
        print("⚠️  No authentication token (testing without auth)")
    print()
    
    # Run tests
    encounter_id, queue_id = test_create_encounter_with_queue(access_token)
    
    test_get_queue_by_id(access_token, queue_id)
    test_get_queue_by_encounter_id(access_token, encounter_id)
    test_get_queue_by_status(access_token)
    test_get_queue_with_limit(access_token)
    test_update_experity_action(access_token, queue_id, encounter_id)
    test_error_cases(access_token)
    test_get_queue_all(access_token)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total Tests: {test_results['passed'] + test_results['failed']}")
    print(f"✅ Passed: {test_results['passed']}")
    print(f"❌ Failed: {test_results['failed']}")
    print()
    
    if test_results['failed'] > 0:
        print("Failed Tests:")
        for test in test_results['tests']:
            if not test['passed']:
                print(f"  - {test['name']}: {test['message']}")
    
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if test_results['failed'] == 0 else 1)

if __name__ == "__main__":
    main()

