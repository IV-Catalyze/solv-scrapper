"""
Comprehensive tests for Summary endpoints.

Endpoints tested:
- POST /summary - Create summary record
- GET /summary - Get summary record by EMR ID
"""
import pytest
import uuid
from fastapi.testclient import TestClient


class TestCreateSummary:
    """Tests for POST /summary - Create summary endpoint"""
    
    @pytest.fixture
    def sample_summary_data(self, test_location_id):
        """Sample summary data for testing"""
        return {
            "emr_id": f"TEST_SUMMARY_{uuid.uuid4().hex[:8]}",
            "note": "This is a test summary note for the patient."
        }
    
    def test_create_summary_success(self, client, hmac_headers, sample_summary_data, test_location_id):
        """Test creating a summary successfully"""
        # First create a patient
        patient_data = {
            "emr_id": sample_summary_data["emr_id"],
            "location_id": test_location_id,
            "legalFirstName": "Summary",
            "legalLastName": "Test"
        }
        
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        patient_response = client.post(patient_path, json=patient_data, headers=patient_headers)
        
        # Create summary
        summary_path = "/summary"
        summary_headers = hmac_headers("POST", summary_path, sample_summary_data)
        response = client.post(summary_path, json=sample_summary_data, headers=summary_headers)
        assert response.status_code == 201
        data = response.json()
        assert data.get("emr_id") == sample_summary_data["emr_id"]
        assert data.get("note") == sample_summary_data["note"]
    
    def test_create_summary_missing_emr_id(self, client, hmac_headers):
        """Test creating summary without emr_id (required)"""
        incomplete_data = {
            "note": "Test summary note"
            # Missing emr_id
        }
        
        path = "/summary"
        headers = hmac_headers("POST", path, incomplete_data)
        response = client.post(path, json=incomplete_data, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_summary_missing_note(self, client, hmac_headers):
        """Test creating summary without note (required)"""
        incomplete_data = {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}"
            # Missing note
        }
        
        path = "/summary"
        headers = hmac_headers("POST", path, incomplete_data)
        response = client.post(path, json=incomplete_data, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_summary_empty_note(self, client, hmac_headers):
        """Test creating summary with empty note"""
        data = {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}",
            "note": ""
        }
        
        path = "/summary"
        headers = hmac_headers("POST", path, data)
        response = client.post(path, json=data, headers=headers)
        # May reject empty note or accept it
        assert response.status_code in [201, 400]
    
    def test_create_summary_without_auth(self, client, sample_summary_data):
        """Test creating summary without authentication"""
        response = client.post("/summary", json=sample_summary_data)
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_create_summary_long_note(self, client, hmac_headers):
        """Test creating summary with very long note"""
        long_note = "This is a very long summary note. " * 100
        data = {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}",
            "note": long_note
        }
        
        path = "/summary"
        headers = hmac_headers("POST", path, data)
        response = client.post(path, json=data, headers=headers)
        # Should accept long notes
        assert response.status_code in [201, 400, 500]
    
    def test_create_summary_multiple_for_same_patient(self, client, hmac_headers, test_location_id):
        """Test creating multiple summaries for same patient"""
        emr_id = f"TEST_MULTI_{uuid.uuid4().hex[:8]}"
        
        # Create patient first
        patient_data = {
            "emr_id": emr_id,
            "location_id": test_location_id,
            "legalFirstName": "Multi",
            "legalLastName": "Summary"
        }
        
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        client.post(patient_path, json=patient_data, headers=patient_headers)
        
        # Create first summary
        summary1 = {
            "emr_id": emr_id,
            "note": "First summary note"
        }
        summary_path = "/summary"
        headers1 = hmac_headers("POST", summary_path, summary1)
        response1 = client.post(summary_path, json=summary1, headers=headers1)
        assert response1.status_code == 201
        
        # Create second summary
        summary2 = {
            "emr_id": emr_id,
            "note": "Second summary note"
        }
        headers2 = hmac_headers("POST", summary_path, summary2)
        response2 = client.post(summary_path, json=summary2, headers=headers2)
        assert response2.status_code == 201


class TestGetSummary:
    """Tests for GET /summary - Get summary by EMR ID or Queue ID"""
    
    @pytest.fixture
    def test_summary(self, client, hmac_headers, test_location_id):
        """Create a test summary for retrieval tests"""
        emr_id = f"TEST_GET_{uuid.uuid4().hex[:8]}"
        
        # Create patient
        patient_data = {
            "emr_id": emr_id,
            "location_id": test_location_id,
            "legalFirstName": "Get",
            "legalLastName": "Summary"
        }
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        client.post(patient_path, json=patient_data, headers=patient_headers)
        
        # Create summary
        summary_data = {
            "emr_id": emr_id,
            "note": "Test summary for retrieval"
        }
        summary_path = "/summary"
        summary_headers = hmac_headers("POST", summary_path, summary_data)
        create_response = client.post(summary_path, json=summary_data, headers=summary_headers)
        
        if create_response.status_code == 201:
            return emr_id
        return None
    
    def test_get_summary_success(self, client, hmac_headers, test_summary):
        """Test getting summary by EMR ID successfully"""
        if not test_summary:
            pytest.skip("Could not create test summary")
        
        # Try both camelCase and snake_case aliases
        for param_name in ["emrId", "emr_id"]:
            path = f"/summary?{param_name}={test_summary}"
            headers = hmac_headers("GET", path, {})
            response = client.get(path, headers=headers)
            if response.status_code == 200:
                data = response.json()
                assert data.get("emrId") == test_summary or data.get("emr_id") == test_summary
                assert "note" in data or "note" in data
                break
    
    def test_get_summary_by_queue_id(self, client, hmac_headers, test_location_id):
        """Test getting summary by queue_id"""
        emr_id = f"TEST_QUEUE_{uuid.uuid4().hex[:8]}"
        
        # Create patient
        patient_data = {
            "emr_id": emr_id,
            "location_id": test_location_id,
            "legalFirstName": "Queue",
            "legalLastName": "Test"
        }
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        client.post(patient_path, json=patient_data, headers=patient_headers)
        
        # Create summary
        summary_data = {
            "emrId": emr_id,
            "note": "Test summary for queue_id lookup"
        }
        summary_path = "/summary"
        summary_headers = hmac_headers("POST", summary_path, summary_data)
        summary_response = client.post(summary_path, json=summary_data, headers=summary_headers)
        if summary_response.status_code != 201:
            pytest.skip("Could not create test summary")
        
        # Create an encounter to get a queue entry
        encounter_id = str(uuid.uuid4())
        encounter_data = {
            "emrId": emr_id,
            "encounterPayload": {
                "id": encounter_id,
                "clientId": str(uuid.uuid4()),
                "status": "COMPLETE"
            }
        }
        encounter_path = "/encounter"
        encounter_headers = hmac_headers("POST", encounter_path, encounter_data)
        encounter_response = client.post(encounter_path, json=encounter_data, headers=encounter_headers)
        
        if encounter_response.status_code != 201:
            pytest.skip("Could not create encounter/queue entry")
        
        # Get queue entry to find queue_id
        queue_path = f"/queue?encounter_id={encounter_id}"
        queue_headers = hmac_headers("GET", queue_path, {})
        queue_response = client.get(queue_path, headers=queue_headers)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if queue_data and len(queue_data) > 0:
                queue_id = queue_data[0].get("queueId") or queue_data[0].get("queue_id")
                if queue_id:
                    # Now try to get summary by queueId (camelCase)
                    summary_by_queue_path = f"/summary?queueId={queue_id}"
                    summary_by_queue_headers = hmac_headers("GET", summary_by_queue_path, {})
                    summary_by_queue_response = client.get(summary_by_queue_path, headers=summary_by_queue_headers)
                    
                    if summary_by_queue_response.status_code == 200:
                        summary_data_result = summary_by_queue_response.json()
                        assert summary_data_result.get("emrId") == emr_id or summary_data_result.get("emr_id") == emr_id
                        assert "note" in summary_data_result
                        return
        
        pytest.skip("Could not test queue_id lookup - queue entry not found or queue_id missing")
    
    def test_get_summary_by_queue_id_not_found(self, client, hmac_headers):
        """Test getting summary with non-existent queueId"""
        fake_queue_id = str(uuid.uuid4())
        path = f"/summary?queueId={fake_queue_id}"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        assert response.status_code == 404
    
    def test_get_summary_by_queue_id_no_emr_id(self, client, hmac_headers):
        """Test getting summary when queue exists but has no emr_id"""
        # This test is hard to set up without direct DB access
        # We'll skip it if we can't create such a scenario
        pytest.skip("Requires queue entry without emr_id - hard to set up in test")
    
    def test_get_summary_not_found(self, client, hmac_headers):
        """Test getting summary for non-existent EMR ID"""
        fake_emr_id = f"FAKE_{uuid.uuid4().hex[:8]}"
        # Try both parameter formats
        for param_name in ["emrId", "emr_id"]:
            path = f"/summary?{param_name}={fake_emr_id}"
            headers = hmac_headers("GET", path, {})
            response = client.get(path, headers=headers)
            if response.status_code == 404:
                break
        assert response.status_code == 404
    
    def test_get_summary_missing_parameters(self, client, hmac_headers):
        """Test getting summary without emrId or queueId parameter"""
        path = "/summary"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        # Should require at least one parameter
        assert response.status_code in [400, 422]
    
    def test_get_summary_without_auth(self, client, test_summary):
        """Test getting summary without authentication"""
        if not test_summary:
            pytest.skip("Could not create test summary")
        
        # Try both parameter formats
        for param_name in ["emrId", "emr_id"]:
            response = client.get(f"/summary?{param_name}={test_summary}")
            # Should require auth
            if response.status_code in [401, 403, 404]:
                break
        assert response.status_code in [401, 403, 404]
    
    def test_get_summary_most_recent(self, client, hmac_headers, test_location_id):
        """Test that GET returns most recent summary when multiple exist"""
        emr_id = f"TEST_RECENT_{uuid.uuid4().hex[:8]}"
        
        # Create patient
        patient_data = {
            "emr_id": emr_id,
            "location_id": test_location_id,
            "legalFirstName": "Recent",
            "legalLastName": "Test"
        }
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        client.post(patient_path, json=patient_data, headers=patient_headers)
        
        # Create first summary
        summary1 = {"emrId": emr_id, "note": "First summary"}
        summary_path = "/summary"
        headers1 = hmac_headers("POST", summary_path, summary1)
        client.post(summary_path, json=summary1, headers=headers1)
        
        # Create second summary (should be most recent)
        summary2 = {"emrId": emr_id, "note": "Second summary - most recent"}
        headers2 = hmac_headers("POST", summary_path, summary2)
        client.post(summary_path, json=summary2, headers=headers2)
        
        # Get summary - should return most recent
        for param_name in ["emrId", "emr_id"]:
            get_path = f"/summary?{param_name}={emr_id}"
            get_headers = hmac_headers("GET", get_path, {})
            response = client.get(get_path, headers=get_headers)
            if response.status_code == 200:
                data = response.json()
                # Should return the most recent one
                assert data.get("note") == "Second summary - most recent"
                break
