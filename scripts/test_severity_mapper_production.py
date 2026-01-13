#!/usr/bin/env python3
"""
Standalone production test script for severity mapper validation.

This script tests the /experity/map endpoint in production to verify:
1. Severity is correctly extracted from complaint.painScale
2. Code-based severity overwrites AI-generated severity
3. Default severity (5) is used when painScale is missing
4. Out-of-range values are clamped (0-10)
5. Severity is always numeric (never string)

Usage:
    python scripts/test_severity_mapper_production.py

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


def validate_severity(complaint: Dict[str, Any], expected_severity: Optional[int] = None) -> Dict[str, Any]:
    """
    Validate severity in a complaint's notesPayload.
    
    Args:
        complaint: Complaint dictionary from response
        expected_severity: Expected severity value (from source painScale)
        
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
            "severity": None
        }
    
    # Check severity exists
    severity = notes_payload.get("severity")
    if severity is None:
        issues.append("Missing severity in notesPayload")
        return {
            "valid": False,
            "issues": issues,
            "severity": None
        }
    
    # Check severity is numeric (not string)
    if isinstance(severity, str):
        issues.append(f"Severity is string '{severity}' instead of numeric")
        try:
            severity = int(float(severity))
        except (ValueError, TypeError):
            return {
                "valid": False,
                "issues": issues,
                "severity": severity
            }
    
    # Check severity is integer
    if not isinstance(severity, (int, float)):
        issues.append(f"Severity has unexpected type {type(severity)}")
        return {
            "valid": False,
            "issues": issues,
            "severity": severity
        }
    
    # Convert to int if float
    severity_int = int(severity)
    
    # Check range (0-10)
    if severity_int < 0:
        issues.append(f"Severity {severity_int} is below minimum (0)")
    elif severity_int > 10:
        issues.append(f"Severity {severity_int} is above maximum (10)")
    
    # Check if matches expected value
    if expected_severity is not None:
        if severity_int != expected_severity:
            issues.append(
                f"Severity mismatch: expected {expected_severity} (from painScale), "
                f"got {severity_int}"
            )
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "severity": severity_int
    }


def test_severity_mapping(api_url: str, hmac_secret: str, client_id: str) -> bool:
    """Test /experity/map endpoint with various severity scenarios."""
    print("\n" + "="*80)
    print("Testing /experity/map endpoint - Severity Mapper Validation")
    print("="*80)
    
    # Create test encounter with various painScale values
    encounter_id = str(uuid.uuid4())
    
    # Test cases: (description, painScale, expected_severity)
    test_cases = [
        ("chest pain", 7, 7),  # Normal case
        ("headache", 3, 3),  # Low severity
        ("severe pain", 10, 10),  # Maximum
        ("mild discomfort", 0, 0),  # Minimum
        ("back pain", None, 5),  # Missing painScale (should default to 5)
        ("leg pain", "8", 8),  # String painScale (should convert)
        ("arm pain", 15, 10),  # Out of range (should clamp to 10)
        ("neck pain", -5, 0),  # Out of range (should clamp to 0)
    ]
    
    chief_complaints = []
    for idx, (description, pain_scale, expected) in enumerate(test_cases):
        complaint = {
            "id": str(uuid.uuid4()),
            "description": description,
            "durationDays": idx + 1,
            "type": "symptom",
            "position": idx
        }
        if pain_scale is not None:
            complaint["painScale"] = pain_scale
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
    print(f"\nSource Complaints with painScale:")
    for idx, (complaint, (desc, pain_scale, expected)) in enumerate(zip(chief_complaints, test_cases)):
        pain_str = str(pain_scale) if pain_scale is not None else "None (default to 5)"
        print(f"  {idx+1}. '{desc}': painScale={pain_str}, expected severity={expected}")
    
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
        
        # Validate severity for each complaint
        all_valid = True
        validation_results = []
        
        print(f"\n" + "="*80)
        print("Severity Validation Results")
        print("="*80)
        
        # Match complaints by description (since order might differ)
        source_by_desc = {tc[0]: (tc[1], tc[2]) for tc in test_cases}
        
        for complaint in complaints:
            description = complaint.get("description", "Unknown")
            complaint_id = complaint.get("complaintId", "N/A")
            
            # Find matching test case
            expected_pain_scale, expected_severity = source_by_desc.get(description, (None, None))
            
            if expected_severity is None:
                print(f"\n⚠️  Complaint '{description}' not found in test cases")
                validation = validate_severity(complaint)
            else:
                validation = validate_severity(complaint, expected_severity)
            
            validation_results.append({
                "description": description,
                "complaint_id": complaint_id,
                "validation": validation
            })
            
            # Print result
            status = "✅" if validation["valid"] else "❌"
            severity = validation["severity"]
            print(f"\n{status} Complaint: '{description}'")
            print(f"   Complaint ID: {complaint_id}")
            print(f"   Severity: {severity}")
            
            if expected_severity is not None:
                print(f"   Expected: {expected_severity} (from painScale: {expected_pain_scale})")
                if severity == expected_severity:
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
        print(f"Valid severity: {valid_count}")
        print(f"Invalid severity: {total_count - valid_count}")
        
        # Check if all severities match expected values
        matched_count = 0
        for result in validation_results:
            desc = result["description"]
            if desc in source_by_desc:
                expected = source_by_desc[desc][1]
                actual = result["validation"]["severity"]
                if actual == expected:
                    matched_count += 1
        
        print(f"\nExpected vs Actual Severity:")
        print(f"  Matched: {matched_count}/{len(source_by_desc)}")
        print(f"  Mismatched: {len(source_by_desc) - matched_count}/{len(source_by_desc)}")
        
        if matched_count < len(source_by_desc):
            print(f"\n⚠️  Some severities don't match expected values from painScale")
            print(f"   This may indicate code-based severity is not being applied correctly")
            all_valid = False
        
        # Detailed comparison
        print(f"\nDetailed Comparison:")
        for result in validation_results:
            desc = result["description"]
            if desc in source_by_desc:
                expected_pain, expected_sev = source_by_desc[desc]
                actual_sev = result["validation"]["severity"]
                match = "✅" if actual_sev == expected_sev else "❌"
                print(f"  {match} '{desc}': painScale={expected_pain} → expected={expected_sev}, actual={actual_sev}")
        
        return all_valid
        
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_edge_cases(api_url: str, hmac_secret: str, client_id: str) -> bool:
    """Test edge cases for severity mapping."""
    print("\n" + "="*80)
    print("Testing Edge Cases - Severity Mapper")
    print("="*80)
    
    encounter_id = str(uuid.uuid4())
    
    # Edge case: Float painScale
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
                "description": "test float painScale",
                "painScale": 7.5,  # Float value
                "durationDays": 1,
                "type": "symptom",
                "position": 0
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
    
    print(f"\nTesting float painScale (7.5) - should convert to int (7)")
    
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
        severity = complaint.get("notesPayload", {}).get("severity")
        
        if severity == 7:
            print(f"✅ Float painScale correctly converted: 7.5 → {severity}")
            return True
        else:
            print(f"❌ Float conversion failed: expected 7, got {severity}")
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
    
    print("Production Severity Mapper Validation Test")
    print(f"API URL: {api_url}")
    print(f"Client ID: {client_id}")
    
    if not hmac_secret:
        print("❌ Error: INTELLIVISIT_STAGING_HMAC_SECRET not set")
        sys.exit(1)
    
    # Run main test
    success_main = test_severity_mapping(api_url, hmac_secret, client_id)
    
    # Run edge case test
    success_edge = test_edge_cases(api_url, hmac_secret, client_id)
    
    print("\n" + "="*80)
    if success_main and success_edge:
        print("✅ ALL TESTS PASSED: Severity mapper is working correctly")
        print("   - Severity correctly extracted from painScale")
        print("   - Code-based severity overwrites AI-generated severity")
        print("   - Default severity (5) used when painScale is missing")
        print("   - Out-of-range values are clamped (0-10)")
        print("   - Severity is always numeric")
    else:
        print("❌ SOME TESTS FAILED")
        if not success_main:
            print("   - Main severity mapping test failed")
        if not success_edge:
            print("   - Edge case test failed")
    print("="*80)
    
    sys.exit(0 if (success_main and success_edge) else 1)


if __name__ == "__main__":
    main()
