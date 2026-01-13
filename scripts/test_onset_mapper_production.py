#!/usr/bin/env python3
"""
Standalone production test script for onset mapper validation.

This script tests the /experity/map endpoint in production to verify:
1. Onset is correctly extracted from complaint.durationDays
2. Format is correct: "Today", "1 day ago", "2 days ago", etc.
3. Code-based onset overwrites AI-generated onset
4. null is returned when durationDays is missing (no fabrication)
5. Proper singular/plural handling

Usage:
    python scripts/test_onset_mapper_production.py

Environment Variables:
    API_BASE_URL: Production API URL (default: https://app-97926.on-aptible.com)
    INTELLIVISIT_STAGING_HMAC_SECRET: HMAC secret for authentication
"""
import os
import sys
import json
import uuid
import hmac
import hashlib
import base64
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not required


def generate_hmac_headers(method: str, path: str, body: Any, secret_key: str) -> Dict[str, str]:
    """Generate HMAC authentication headers."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        body_str = json.dumps(body)
        body_bytes = body_str.encode('utf-8')
    elif isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif body is None:
        body_bytes = b''
    else:
        body_bytes = b''
    
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
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
    
    if method.upper() in ["POST", "PUT", "PATCH"] and body_bytes:
        headers["Content-Type"] = "application/json"
    
    return headers


def validate_onset(complaint: Dict[str, Any], expected_onset: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate onset in a complaint's notesPayload.
    
    Args:
        complaint: Complaint dictionary from response
        expected_onset: Expected onset string (from source durationDays)
        
    Returns:
        Validation result dictionary
    """
    issues = []
    
    # Check notesPayload exists
    notes_payload = complaint.get("notesPayload")
    if not notes_payload:
        issues.append("Missing notesPayload")
        return {
            "valid": False,
            "issues": issues,
            "onset": None
        }
    
    # Get onset
    onset = notes_payload.get("onset")
    
    # Check if matches expected value
    if expected_onset is not None:
        if onset != expected_onset:
            issues.append(
                f"Onset mismatch: expected '{expected_onset}', got '{onset}'"
            )
    
    # Validate format if onset is present
    if onset is not None:
        if not isinstance(onset, str):
            issues.append(f"Onset is not a string: {type(onset)}")
        elif onset not in ["Today", "0 days ago"] and not onset.endswith(" day ago") and not onset.endswith(" days ago"):
            issues.append(f"Onset has invalid format: '{onset}' (should be 'Today', '1 day ago', '2 days ago', etc.)")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "onset": onset
    }


def test_onset_mapping(api_url: str, hmac_secret: str, client_id: str) -> bool:
    """Test /experity/map endpoint with various onset scenarios."""
    print("\n" + "="*80)
    print("Testing /experity/map endpoint - Onset Mapper Validation")
    print("="*80)
    
    # Create test encounter with various durationDays values
    encounter_id = str(uuid.uuid4())
    
    # Test cases: (description, durationDays, expected_onset)
    test_cases = [
        ("chest pain today", 0, "Today"),
        ("headache yesterday", 1, "1 day ago"),
        ("back pain two days", 2, "2 days ago"),
        ("leg pain week ago", 7, "7 days ago"),
        ("arm pain month ago", 30, "30 days ago"),
        ("stomach pain", None, None),  # No durationDays
    ]
    
    chief_complaints = []
    for idx, (description, duration_days, expected) in enumerate(test_cases):
        complaint = {
            "id": str(uuid.uuid4()),
            "description": description,
            "painScale": 5,  # Include painScale for severity
            "type": "symptom",
            "position": idx
        }
        if duration_days is not None:
            complaint["durationDays"] = duration_days
        chief_complaints.append(complaint)
    
    encounter_data = {
        "id": encounter_id,
        "clientId": client_id,
        "emrId": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
        "attributes": {
            "gender": "male",
            "ageYears": 35,
            "heightCm": 175,
            "weightKg": 75,
            "pulseRateBpm": 72,
            "respirationBpm": 16,
            "bodyTemperatureCelsius": 37,
            "bloodPressureSystolicMm": 120,
            "bloodPressureDiastolicMm": 80,
            "pulseOx": 98
        },
        "chiefComplaints": chief_complaints,
        "traumaType": "NONE",
        "orders": [],
        "additionalQuestions": {
            "conditions": [],
            "guardianAssistedInterview": {
                "present": False
            }
        }
    }
    
    print(f"\nTest Encounter ID: {encounter_id}")
    print(f"\nSource Complaints with durationDays:")
    for idx, (complaint, (desc, duration_days, expected)) in enumerate(zip(chief_complaints, test_cases)):
        duration_str = str(duration_days) if duration_days is not None else "None"
        print(f"  {idx+1}. '{desc}': durationDays={duration_str}, expected onset={expected}")
    
    # Make request
    path = "/experity/map"
    url = f"{api_url}{path}"
    headers = generate_hmac_headers("POST", path, encounter_data, hmac_secret)
    
    print(f"\nSending request to: {url}")
    print(f"Request headers: X-Timestamp={headers.get('X-Timestamp')}")
    
    try:
        response = requests.post(url, json=encounter_data, headers=headers, timeout=120)
        
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        data = response.json()
        
        if not data.get("success"):
            print(f"❌ Response indicates failure: {data}")
            return False
        
        # Extract complaints
        experity_actions = data.get("data", {}).get("experityActions", {})
        complaints = experity_actions.get("complaints", [])
        
        if not complaints:
            print("⚠️  No complaints in response")
            return False
        
        print(f"\nReceived {len(complaints)} complaints in response")
        
        # Validate onset for each complaint
        all_valid = True
        validation_results = []
        
        print(f"\n" + "="*80)
        print("Onset Validation Results")
        print("="*80)
        
        # Match complaints by description
        source_by_desc = {tc[0]: (tc[1], tc[2]) for tc in test_cases}
        
        for complaint in complaints:
            description = complaint.get("description", "Unknown")
            complaint_id = complaint.get("complaintId", "N/A")
            
            # Find matching test case
            duration_days, expected_onset = source_by_desc.get(description, (None, None))
            
            if expected_onset is None:
                print(f"\n⚠️  Complaint '{description}' not found in test cases")
                validation = validate_onset(complaint)
            else:
                validation = validate_onset(complaint, expected_onset)
            
            validation_results.append({
                "description": description,
                "complaint_id": complaint_id,
                "validation": validation,
                "expected": expected_onset,
                "duration_days": duration_days
            })
            
            # Print result
            status = "✅" if validation["valid"] else "❌"
            onset = validation["onset"]
            print(f"\n{status} Complaint: '{description}'")
            print(f"   Complaint ID: {complaint_id}")
            print(f"   Onset: {onset}")
            
            if expected_onset is not None:
                print(f"   Expected: {expected_onset} (from durationDays: {duration_days})")
                if onset == expected_onset:
                    print(f"   ✅ Matches expected value")
                else:
                    print(f"   ❌ Does NOT match expected value")
                    all_valid = False
            
            if validation["issues"]:
                print(f"   Issues:")
                for issue in validation["issues"]:
                    print(f"     - {issue}")
                all_valid = False
        
        # Summary
        print(f"\n" + "="*80)
        print("Summary")
        print("="*80)
        
        valid_count = sum(1 for r in validation_results if r["validation"]["valid"])
        total_count = len(validation_results)
        
        print(f"Total complaints: {total_count}")
        print(f"Valid onset: {valid_count}")
        print(f"Invalid onset: {total_count - valid_count}")
        
        # Check if all onsets match expected values
        matched_count = 0
        for result in validation_results:
            desc = result["description"]
            if desc in source_by_desc:
                expected = source_by_desc[desc][1]  # expected_onset
                actual = result["validation"]["onset"]
                if actual == expected:
                    matched_count += 1
        
        print(f"\nExpected vs Actual Onset:")
        print(f"  Matched: {matched_count}/{len(source_by_desc)}")
        print(f"  Mismatched: {len(source_by_desc) - matched_count}/{len(source_by_desc)}")
        
        if matched_count < len(source_by_desc):
            print(f"\n⚠️  Some onsets don't match expected values from source")
            print(f"   This may indicate code-based onset is not being applied correctly")
            all_valid = False
        
        # Detailed comparison
        print(f"\nDetailed Comparison:")
        for result in validation_results:
            desc = result["description"]
            if desc in source_by_desc:
                duration_days, expected_onset = source_by_desc[desc]
                actual_onset = result["validation"]["onset"]
                match = "✅" if actual_onset == expected_onset else "❌"
                duration_str = str(duration_days) if duration_days is not None else "None"
                print(f"  {match} '{desc}': durationDays={duration_str} → expected={expected_onset}, actual={actual_onset}")
        
        return all_valid
        
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_no_fabrication(api_url: str, hmac_secret: str, client_id: str) -> bool:
    """Test that onset is not fabricated when durationDays is missing."""
    print("\n" + "="*80)
    print("Testing No Fabrication Rule - Onset Mapper")
    print("="*80)
    
    encounter_id = str(uuid.uuid4())
    
    # Test case: Complaint with no durationDays
    encounter_data = {
        "id": encounter_id,
        "clientId": client_id,
        "emrId": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
        "attributes": {
            "gender": "female",
            "ageYears": 28
        },
        "chiefComplaints": [
            {
                "id": str(uuid.uuid4()),
                "description": "chest pain",
                "painScale": 5,
                "type": "symptom",
                "position": 0
                # No durationDays
            }
        ],
        "traumaType": "NONE",
        "orders": [],
        "additionalQuestions": {
            "conditions": [],
            "guardianAssistedInterview": {"present": False}
        }
    }
    
    path = "/experity/map"
    url = f"{api_url}{path}"
    headers = generate_hmac_headers("POST", path, encounter_data, hmac_secret)
    
    print(f"\nTesting no fabrication: complaint with no durationDays - should return null")
    
    try:
        response = requests.post(url, json=encounter_data, headers=headers, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            return False
        
        data = response.json()
        if not data.get("success"):
            print(f"❌ Response indicates failure")
            return False
        
        complaints = data.get("data", {}).get("experityActions", {}).get("complaints", [])
        if not complaints:
            print("⚠️  No complaints in response")
            return False
        
        complaint = complaints[0]
        onset = complaint.get("notesPayload", {}).get("onset")
        
        if onset is None:
            print(f"✅ No fabrication: onset correctly set to null")
            return True
        else:
            print(f"❌ Fabrication detected: onset={onset} (expected null)")
            print(f"   This violates the no-fabrication rule!")
            return False
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def main():
    """Main test function."""
    api_url = os.getenv(
        "API_BASE_URL",
        "https://app-97926.on-aptible.com"
    ).rstrip('/')
    
    hmac_secret = os.getenv(
        "INTELLIVISIT_STAGING_HMAC_SECRET",
        "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM"
    )
    
    client_id = os.getenv(
        "STAGING_CLIENT_ID",
        "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"
    )
    
    print("Production Onset Mapper Validation Test")
    print(f"API URL: {api_url}")
    print(f"Client ID: {client_id}")
    
    if not hmac_secret:
        print("❌ Error: INTELLIVISIT_STAGING_HMAC_SECRET not set")
        sys.exit(1)
    
    # Run main test
    success_main = test_onset_mapping(api_url, hmac_secret, client_id)
    
    # Run no-fabrication test
    success_no_fabrication = test_no_fabrication(api_url, hmac_secret, client_id)
    
    print("\n" + "="*80)
    if success_main and success_no_fabrication:
        print("✅ ALL TESTS PASSED: Onset mapper is working correctly")
        print("   - Onset correctly extracted from durationDays")
        print("   - Format is correct: 'Today', '1 day ago', '2 days ago', etc.")
        print("   - Code-based onset overwrites AI-generated onset")
        print("   - null returned when durationDays is missing (no fabrication)")
        print("   - Proper singular/plural handling")
    else:
        print("❌ SOME TESTS FAILED")
        if not success_main:
            print("   - Main onset mapping test failed")
        if not success_no_fabrication:
            print("   - No-fabrication test failed")
    print("="*80)
    
    sys.exit(0 if (success_main and success_no_fabrication) else 1)


if __name__ == "__main__":
    main()
