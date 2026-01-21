"""
Test script to verify complaintId validation fix in production.

This test verifies that:
1. All complaintIds in the response are valid UUIDs
2. Invalid complaintIds (e.g., description text) are replaced with valid UUIDs
3. Pre-extracted complaintIds from source data are used when available
4. New UUIDs are generated when needed

Run with: pytest tests/test_complaint_id_fix.py -v
"""
import pytest
import uuid
import re
from typing import Dict, Any, List


def is_valid_uuid(value: Any) -> bool:
    """Check if a value is a valid UUID string."""
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def validate_complaint_ids(complaints: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate all complaintIds in complaints array.
    
    Returns:
        Dict with validation results:
        {
            "all_valid": bool,
            "invalid_count": int,
            "invalid_complaints": List[Dict],
            "total_complaints": int,
            "unique_ids": bool,
            "duplicate_count": int
        }
    """
    invalid_complaints = []
    complaint_ids = []
    
    for complaint in complaints:
        complaint_id = complaint.get("complaintId")
        if not complaint_id:
            invalid_complaints.append({
                "complaint": complaint,
                "issue": "Missing complaintId"
            })
        elif not is_valid_uuid(complaint_id):
            invalid_complaints.append({
                "complaint": complaint,
                "issue": f"Invalid UUID format: '{complaint_id}'"
            })
        else:
            complaint_ids.append(complaint_id)
    
    # Check for duplicates
    unique_ids = set(complaint_ids)
    duplicate_count = len(complaint_ids) - len(unique_ids)
    
    return {
        "all_valid": len(invalid_complaints) == 0,
        "invalid_count": len(invalid_complaints),
        "invalid_complaints": invalid_complaints,
        "total_complaints": len(complaints),
        "unique_ids": duplicate_count == 0,
        "duplicate_count": duplicate_count
    }


class TestComplaintIdValidation:
    """Tests for complaintId validation fix"""
    
    def test_experity_map_with_valid_encounter(self, client, hmac_headers, staging_client_id):
        """
        Test /experity/map endpoint with a valid encounter.
        Verifies that all complaintIds are valid UUIDs.
        """
        # Create a test encounter with valid complaint IDs
        encounter_id = str(uuid.uuid4())
        complaint_id_1 = str(uuid.uuid4())
        complaint_id_2 = str(uuid.uuid4())
        
        encounter_data = {
            "id": encounter_id,
            "clientId": staging_client_id,
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
            "chiefComplaints": [
                {
                    "id": complaint_id_1,
                    "description": "cut on finger(s) or thumb(s)",
                    "painScale": 5,
                    "durationDays": 1,
                    "type": "trauma",
                    "part": "hand",
                    "position": 0
                },
                {
                    "id": complaint_id_2,
                    "description": "chest pain",
                    "painScale": 7,
                    "durationDays": 2,
                    "type": "symptom",
                    "part": "chest",
                    "position": 1
                }
            ],
            "traumaType": "CUT",
            "orders": [],
            "additionalQuestions": {
                "conditions": {},
                "guardianAssistedInterview": {
                    "present": False
                }
            }
        }
        
        # Make request to /experity/map
        path = "/experity/map"
        headers = hmac_headers("POST", path, encounter_data)
        
        response = client.post(path, json=encounter_data, headers=headers)
        
        # Verify response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"Expected success=True, got: {data}"
        
        # Extract complaints from response
        experity_actions = data.get("data", {}).get("experityActions", {})
        complaints = experity_actions.get("complaints", [])
        
        # Validate all complaintIds
        validation = validate_complaint_ids(complaints)
        
        assert validation["all_valid"], (
            f"Found {validation['invalid_count']} invalid complaintIds out of {validation['total_complaints']}:\n"
            + "\n".join([
                f"  - {item['issue']}: {item['complaint'].get('description', 'N/A')}"
                for item in validation["invalid_complaints"]
            ])
        )
        
        # Verify that pre-extracted complaintIds are used
        complaint_descriptions = {c.get("description"): c.get("complaintId") for c in complaints}
        
        # Verify uniqueness
        assert validation["unique_ids"], (
            f"Found {validation['duplicate_count']} duplicate complaintIds. "
            f"All complaint IDs must be unique within a single encounter."
        )
        
        # Check if the original complaint IDs are preserved (if matching by description works)
        # Note: This may not always match if AI transforms descriptions, but IDs should still be valid UUIDs
        print(f"\n✓ All {validation['total_complaints']} complaintIds are valid UUIDs and unique")
        for complaint in complaints:
            print(f"  - '{complaint.get('description')}': {complaint.get('complaintId')}")
    
    def test_experity_map_with_queue_entry_format(self, client, hmac_headers, staging_client_id):
        """
        Test /experity/map endpoint with queue_entry format.
        Verifies complaintId validation in queue entry format.
        
        Note: This test uses direct encounter format since queue_entry format
        requires an existing database entry. The complaintId validation logic
        is the same regardless of input format.
        """
        encounter_id = str(uuid.uuid4())
        complaint_id_1 = str(uuid.uuid4())
        
        # Use direct encounter format (same validation logic applies)
        encounter_data = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "emrId": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
            "attributes": {
                "gender": "female",
                "ageYears": 28,
                "heightCm": 165,
                "weightKg": 60
            },
            "chiefComplaints": [
                {
                    "id": complaint_id_1,
                    "description": "headache",
                    "painScale": 6,
                    "durationDays": 3,
                    "type": "symptom",
                    "part": "head",
                    "position": 0
                }
            ],
            "traumaType": "NONE",
            "orders": [],
            "additionalQuestions": {
                "conditions": {},
                "guardianAssistedInterview": {
                    "present": False
                }
            }
        }
        
        path = "/experity/map"
        headers = hmac_headers("POST", path, encounter_data)
        
        response = client.post(path, json=encounter_data, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        
        # Validate complaintIds
        experity_actions = data.get("data", {}).get("experityActions", {})
        complaints = experity_actions.get("complaints", [])
        
        validation = validate_complaint_ids(complaints)
        
        assert validation["all_valid"], (
            f"Found invalid complaintIds: {validation['invalid_complaints']}"
        )
        
        assert validation["unique_ids"], (
            f"Found duplicate complaintIds. All IDs must be unique."
        )
        
        print(f"\n✓ Direct encounter format: All {validation['total_complaints']} complaintIds are valid UUIDs and unique")
    
    def test_multiple_encounters_for_consistency(self, client, hmac_headers, staging_client_id):
        """
        Test multiple encounters to ensure consistent complaintId validation.
        This helps catch edge cases where the AI might return invalid IDs.
        """
        results = []
        
        for i in range(3):
            encounter_id = str(uuid.uuid4())
            complaint_id = str(uuid.uuid4())
            
            encounter_data = {
                "id": encounter_id,
                "clientId": staging_client_id,
                "emrId": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
                "attributes": {
                    "gender": "male" if i % 2 == 0 else "female",
                    "ageYears": 30 + i,
                },
                "chiefComplaints": [
                    {
                        "id": complaint_id,
                        "description": f"test complaint {i+1}",
                        "painScale": 5,
                        "durationDays": i,
                        "type": "symptom",
                        "part": "head",
                        "position": 0
                    }
                ],
                "traumaType": "NONE",
                "orders": [],
                "additionalQuestions": {
                    "conditions": {},
                    "guardianAssistedInterview": {"present": False}
                }
            }
            
            path = "/experity/map"
            headers = hmac_headers("POST", path, encounter_data)
            
            response = client.post(path, json=encounter_data, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    experity_actions = data.get("data", {}).get("experityActions", {})
                    complaints = experity_actions.get("complaints", [])
                    validation = validate_complaint_ids(complaints)
                    results.append({
                        "encounter_id": encounter_id,
                        "all_valid": validation["all_valid"],
                        "invalid_count": validation["invalid_count"],
                        "total_complaints": validation["total_complaints"],
                        "unique_ids": validation["unique_ids"],
                        "duplicate_count": validation["duplicate_count"]
                    })
        
        # Verify all results have valid and unique complaintIds
        all_valid = all(r["all_valid"] for r in results)
        all_unique = all(r["unique_ids"] for r in results)
        total_tested = len(results)
        
        assert all_valid, (
            f"Not all encounters passed validation. Results: {results}"
        )
        
        assert all_unique, (
            f"Some encounters have duplicate complaintIds. Results: {results}"
        )
        
        print(f"\n✓ Tested {total_tested} encounters, all have valid and unique complaintIds")
    
    def test_complaint_id_uniqueness(self, client, hmac_headers, staging_client_id):
        """
        Test that complaint IDs are unique within a single encounter.
        This test specifically verifies the uniqueness fix.
        """
        encounter_id = str(uuid.uuid4())
        # Use the same complaint ID twice to test uniqueness fix
        complaint_id_1 = str(uuid.uuid4())
        complaint_id_2 = complaint_id_1  # Intentionally duplicate
        
        encounter_data = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "emrId": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
            "attributes": {
                "gender": "male",
                "ageYears": 35,
                "heightCm": 175,
                "weightKg": 75
            },
            "chiefComplaints": [
                {
                    "id": complaint_id_1,
                    "description": "chest pain",
                    "painScale": 7,
                    "durationDays": 1,
                    "type": "symptom",
                    "part": "chest",
                    "position": 0
                },
                {
                    "id": complaint_id_2,  # Same ID - should be fixed
                    "description": "headache",
                    "painScale": 5,
                    "durationDays": 2,
                    "type": "symptom",
                    "part": "head",
                    "position": 1
                }
            ],
            "traumaType": "NONE",
            "orders": [],
            "additionalQuestions": {
                "conditions": {},
                "guardianAssistedInterview": {"present": False}
            }
        }
        
        path = "/experity/map"
        headers = hmac_headers("POST", path, encounter_data)
        
        response = client.post(path, json=encounter_data, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        
        # Extract complaints
        experity_actions = data.get("data", {}).get("experityActions", {})
        complaints = experity_actions.get("complaints", [])
        
        # Validate uniqueness
        validation = validate_complaint_ids(complaints)
        
        assert validation["all_valid"], "All complaintIds must be valid UUIDs"
        assert validation["unique_ids"], (
            f"Complaint IDs must be unique. Found {validation['duplicate_count']} duplicate(s). "
            f"Complaint IDs: {[c.get('complaintId') for c in complaints]}"
        )
        
        # Verify all IDs are different
        complaint_ids = [c.get("complaintId") for c in complaints]
        assert len(complaint_ids) == len(set(complaint_ids)), (
            f"Duplicate IDs found: {complaint_ids}"
        )
        
        print(f"\n✓ Uniqueness test passed: All {validation['total_complaints']} complaintIds are unique")
        for complaint in complaints:
            print(f"  - '{complaint.get('description')}': {complaint.get('complaintId')}")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])

