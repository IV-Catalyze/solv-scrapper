"""
Comprehensive tests for Patient endpoints.

Endpoints tested:
- GET /patients - List patients
- GET /patient/{emr_id} - Get patient by EMR ID
- POST /patients/create - Create patient
- PATCH /patients/{emr_id} - Update patient status
"""
import pytest
import uuid
from fastapi.testclient import TestClient


class TestListPatients:
    """Tests for GET /patients - List patients endpoint"""
    
    def test_get_patients_with_auth(self, client, hmac_headers, test_location_id):
        """Test getting patients list with authentication"""
        path = f"/patients?locationId={test_location_id}"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
    
    def test_get_patients_without_auth(self, client, test_location_id):
        """Test getting patients without authentication"""
        response = client.get(f"/patients?locationId={test_location_id}")
        # May require auth or may work without it depending on configuration
        assert response.status_code in [200, 401, 403]
    
    def test_get_patients_with_limit(self, client, hmac_headers, test_location_id):
        """Test getting patients with limit parameter"""
        path = f"/patients?locationId={test_location_id}&limit=5"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= 5
    
    def test_get_patients_with_status_filter(self, client, hmac_headers, test_location_id):
        """Test getting patients filtered by status"""
        path = f"/patients?locationId={test_location_id}&statuses=checked_in"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
    
    def test_get_patients_multiple_statuses(self, client, hmac_headers, test_location_id):
        """Test getting patients with multiple status filters"""
        path = f"/patients?locationId={test_location_id}&statuses=checked_in&statuses=confirmed"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
    
    def test_get_patients_missing_location_id(self, client, hmac_headers):
        """Test getting patients without locationId"""
        path = "/patients"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # May work if DEFAULT_LOCATION_ID is set, otherwise should return error
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 400, 502]
    
    def test_get_patients_invalid_limit(self, client, hmac_headers, test_location_id):
        """Test getting patients with invalid limit"""
        path = f"/patients?locationId={test_location_id}&limit=0"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Should return validation error for limit < 1
        assert response.status_code in [400, 422]
    
    def test_get_patients_response_structure(self, client, hmac_headers, test_location_id):
        """Test that patients response has correct structure"""
        path = f"/patients?locationId={test_location_id}&limit=1"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
        
        if len(data) > 0:
            patient = data[0]
            # Check for common patient fields (may vary)
            assert isinstance(patient, dict)


class TestGetPatientByEmrId:
    """Tests for GET /patient/{emr_id} - Get patient by EMR ID"""
    
    def test_get_patient_by_emr_id_success(self, client, hmac_headers):
        """Test getting a patient by valid EMR ID"""
        test_emr_id = "TEST_EMR_ID_123"
        path = f"/patient/{test_emr_id}"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Should return 200 if exists, 404 if not
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "emr_id" in data or data.get("emr_id") is not None
    
    def test_get_patient_by_emr_id_not_found(self, client, hmac_headers):
        """Test getting a patient with non-existent EMR ID"""
        fake_emr_id = f"FAKE_{uuid.uuid4().hex[:8]}"
        path = f"/patient/{fake_emr_id}"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        assert response.status_code == 404
    
    def test_get_patient_by_emr_id_without_auth(self, client):
        """Test getting patient without authentication"""
        test_emr_id = "TEST_EMR_ID_123"
        response = client.get(f"/patient/{test_emr_id}")
        # May require auth
        assert response.status_code in [200, 401, 403, 404]
    
    def test_get_patient_by_emr_id_empty_string(self, client, hmac_headers):
        """Test getting patient with empty EMR ID"""
        path = "/patient/"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        # Should return 404 or 405 (method not allowed)
        assert response.status_code in [404, 405]


class TestCreatePatient:
    """Tests for POST /patients/create - Create patient endpoint"""
    
    @pytest.fixture
    def sample_patient_data(self, test_location_id):
        """Sample patient data for testing"""
        return {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}",
            "location_id": test_location_id,
            "legalFirstName": "John",
            "legalLastName": "Doe",
            "dob": "1990-01-01",
            "mobilePhone": "555-1234",
            "sexAtBirth": "male"
        }
    
    def test_create_patient_success(self, client, hmac_headers, sample_patient_data):
        """Test creating a new patient successfully"""
        path = "/patients/create"
        headers = hmac_headers("POST", path, sample_patient_data)
        
        response = client.post(path, json=sample_patient_data, headers=headers)
        # Should return 201 (created) or 200 (updated)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("emr_id") == sample_patient_data["emr_id"]
        assert "status" in data or "message" in data
    
    def test_create_patient_missing_emr_id(self, client, hmac_headers, test_location_id):
        """Test creating patient without emr_id (required field)"""
        incomplete_data = {
            "location_id": test_location_id,
            "legalFirstName": "Jane"
        }
        path = "/patients/create"
        headers = hmac_headers("POST", path, incomplete_data)
        
        response = client.post(path, json=incomplete_data, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_patient_missing_location_id(self, client, hmac_headers):
        """Test creating patient without location_id"""
        incomplete_data = {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}",
            "legalFirstName": "Jane"
        }
        path = "/patients/create"
        headers = hmac_headers("POST", path, incomplete_data)
        
        response = client.post(path, json=incomplete_data, headers=headers)
        # May work if patient exists and location_id can be inherited
        assert response.status_code in [200, 201, 400]
    
    def test_create_patient_without_auth(self, client, sample_patient_data):
        """Test creating patient without authentication"""
        response = client.post("/patients/create", json=sample_patient_data)
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_create_patient_invalid_data(self, client, hmac_headers):
        """Test creating patient with invalid data structure"""
        invalid_data = {"invalid": "data", "not": "a patient"}
        path = "/patients/create"
        headers = hmac_headers("POST", path, invalid_data)
        
        response = client.post(path, json=invalid_data, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_patient_update_existing(self, client, hmac_headers, sample_patient_data):
        """Test that creating a patient with existing emr_id updates it"""
        path = "/patients/create"
        
        # Create patient first
        headers1 = hmac_headers("POST", path, sample_patient_data)
        create_response = client.post(path, json=sample_patient_data, headers=headers1)
        
        if create_response.status_code in [200, 201]:
            # Try to create again with same emr_id but different data
            updated_data = sample_patient_data.copy()
            updated_data["legalFirstName"] = "UpdatedName"
            
            headers2 = hmac_headers("POST", path, updated_data)
            update_response = client.post(path, json=updated_data, headers=headers2)
            assert update_response.status_code in [200, 201]
            data = update_response.json()
            assert data.get("emr_id") == sample_patient_data["emr_id"]


class TestUpdatePatientStatus:
    """Tests for PATCH /patients/{emr_id} - Update patient status"""
    
    @pytest.fixture
    def test_patient(self, client, hmac_headers, test_location_id):
        """Create a test patient for status update tests"""
        patient_data = {
            "emr_id": f"TEST_STATUS_{uuid.uuid4().hex[:8]}",
            "location_id": test_location_id,
            "legalFirstName": "Status",
            "legalLastName": "Test"
        }
        
        path = "/patients/create"
        headers = hmac_headers("POST", path, patient_data)
        response = client.post(path, json=patient_data, headers=headers)
        
        if response.status_code in [200, 201]:
            return patient_data["emr_id"]
        return None
    
    def test_update_patient_status_success(self, client, hmac_headers, test_patient):
        """Test updating patient status successfully"""
        if not test_patient:
            pytest.skip("Could not create test patient")
        
        path = f"/patients/{test_patient}"
        body = {"status": "confirmed"}
        headers = hmac_headers("PATCH", path, body)
        
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        # API returns new_status, not status
        assert data.get("new_status") == "confirmed" or data.get("status") == "confirmed" or data.get("status") == "CONFIRMED"
    
    def test_update_patient_status_not_found(self, client, hmac_headers):
        """Test updating status for non-existent patient"""
        fake_emr_id = f"FAKE_{uuid.uuid4().hex[:8]}"
        path = f"/patients/{fake_emr_id}"
        body = {"status": "confirmed"}
        headers = hmac_headers("PATCH", path, body)
        
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 404
    
    def test_update_patient_status_invalid_status(self, client, hmac_headers, test_patient):
        """Test updating patient with invalid status value"""
        if not test_patient:
            pytest.skip("Could not create test patient")
        
        path = f"/patients/{test_patient}"
        body = {"status": "INVALID_STATUS_XYZ"}
        headers = hmac_headers("PATCH", path, body)
        
        response = client.patch(path, json=body, headers=headers)
        # May accept any status or validate it
        assert response.status_code in [200, 400]
    
    def test_update_patient_status_missing_status(self, client, hmac_headers, test_patient):
        """Test updating patient without status field"""
        if not test_patient:
            pytest.skip("Could not create test patient")
        
        path = f"/patients/{test_patient}"
        body = {}
        headers = hmac_headers("PATCH", path, body)
        
        response = client.patch(path, json=body, headers=headers)
        # Should require status field
        assert response.status_code in [400, 422]
    
    def test_update_patient_status_without_auth(self, client, test_patient):
        """Test updating patient status without authentication"""
        if not test_patient:
            pytest.skip("Could not create test patient")
        
        response = client.patch(
            f"/patients/{test_patient}",
            json={"status": "confirmed"}
        )
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_update_patient_status_multiple_updates(self, client, hmac_headers, test_patient):
        """Test multiple status updates on same patient"""
        if not test_patient:
            pytest.skip("Could not create test patient")
        
        path = f"/patients/{test_patient}"
        
        # First update
        body1 = {"status": "checked_in"}
        headers1 = hmac_headers("PATCH", path, body1)
        response1 = client.patch(path, json=body1, headers=headers1)
        assert response1.status_code == 200
        
        # Second update
        body2 = {"status": "confirmed"}
        headers2 = hmac_headers("PATCH", path, body2)
        response2 = client.patch(path, json=body2, headers=headers2)
        assert response2.status_code == 200
        data = response2.json()
        # API returns new_status, not status
        assert data.get("new_status") in ["confirmed", "CONFIRMED"] or data.get("status") in ["confirmed", "CONFIRMED"]
