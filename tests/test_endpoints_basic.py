"""
Basic endpoint tests - examples for common patterns.
This file demonstrates how to test various endpoint types.
"""
import pytest
import uuid
import json
import hmac
import hashlib
import base64
from datetime import datetime


def generate_hmac_headers(method, path, body_json, secret):
    """Helper to generate HMAC authentication headers for testing"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    body_str = body_json if isinstance(body_json, str) else json.dumps(body_json, separators=(',', ':'))
    body_hash = hashlib.sha256(body_str.encode()).hexdigest()
    
    canonical = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    signature = base64.b64encode(
        hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()
    ).decode()
    
    return {
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json"
    }


class TestRootEndpoint:
    """Tests for the root endpoint"""
    
    def test_get_root(self, client):
        """Test that root endpoint is accessible"""
        response = client.get("/")
        assert response.status_code == 200


class TestAuthEndpoint:
    """Tests for authentication endpoints"""
    
    def test_get_token_staging(self, client, staging_client_id):
        """Test token generation with staging client ID"""
        response = client.post(
            "/auth/token",
            json={"client_id": staging_client_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 0
    
    def test_get_token_production(self, client, production_client_id):
        """Test token generation with production client ID"""
        response = client.post(
            "/auth/token",
            json={"client_id": production_client_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
    
    def test_get_token_invalid_client_id(self, client):
        """Test token generation with invalid client ID"""
        response = client.post(
            "/auth/token",
            json={"client_id": "Invalid-Client-ID"}
        )
        # Should return error (status depends on your implementation)
        assert response.status_code in [400, 401, 404]
    
    def test_get_token_missing_client_id(self, client):
        """Test token generation without client_id"""
        response = client.post("/auth/token", json={})
        assert response.status_code in [400, 422]  # Bad Request or Validation Error


class TestPatientEndpoints:
    """Tests for patient endpoints"""
    
    def test_get_patients_with_auth(self, client, auth_headers, test_location_id):
        """Test getting patients list with authentication"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get(
            f"/patients?locationId={test_location_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_patients_with_limit(self, client, auth_headers, test_location_id):
        """Test getting patients with limit parameter"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get(
            f"/patients?locationId={test_location_id}&limit=5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
    
    def test_get_patients_with_status_filter(self, client, auth_headers, test_location_id):
        """Test getting patients filtered by status"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get(
            f"/patients?locationId={test_location_id}&statuses=checked_in",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_patient_by_emr_id(self, client, auth_headers):
        """Test getting a specific patient by EMR ID"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        # First, try to get a patient (adjust based on your test data)
        # This test assumes you have test data or will get 404
        test_emr_id = "TEST_EMR_ID_123"
        response = client.get(
            f"/patient/{test_emr_id}",
            headers=auth_headers
        )
        # Should return 200 if exists, 404 if not
        assert response.status_code in [200, 404]
    
    def test_create_patient(self, client, auth_headers, test_location_id):
        """Test creating a new patient"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        patient_data = {
            "emr_id": f"TEST_{uuid.uuid4().hex[:8]}",
            "location_id": test_location_id,
            "legalFirstName": "Test",
            "legalLastName": "Patient",
            "dob": "1990-01-01",
            "mobilePhone": "555-1234"
        }
        
        response = client.post(
            "/patients/create",
            json=patient_data,
            headers=auth_headers
        )
        # Should return 201 (created) or 200 (updated)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("emr_id") == patient_data["emr_id"]
    
    def test_create_patient_missing_required_fields(self, client, auth_headers):
        """Test creating patient without required fields"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        incomplete_data = {
            "legalFirstName": "Test"
            # Missing emr_id and location_id
        }
        
        response = client.post(
            "/patients/create",
            json=incomplete_data,
            headers=auth_headers
        )
        assert response.status_code in [400, 422]  # Bad Request or Validation Error
    
    def test_update_patient_status(self, client, auth_headers, test_location_id):
        """Test updating patient status"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        # First create a patient
        emr_id = f"TEST_{uuid.uuid4().hex[:8]}"
        patient_data = {
            "emr_id": emr_id,
            "location_id": test_location_id,
            "legalFirstName": "Test",
            "legalLastName": "Patient"
        }
        
        create_response = client.post(
            "/patients/create",
            json=patient_data,
            headers=auth_headers
        )
        
        if create_response.status_code in [200, 201]:
            # Now update the status
            update_response = client.patch(
                f"/patients/{emr_id}",
                json={"status": "confirmed"},
                headers=auth_headers
            )
            assert update_response.status_code == 200
            data = update_response.json()
            assert data.get("status") == "confirmed"


class TestEncounterEndpoints:
    """Tests for encounter endpoints"""
    
    @pytest.fixture
    def sample_encounter(self):
        """Sample encounter data for testing"""
        encounter_id = str(uuid.uuid4())
        return {
            "id": encounter_id,
            "clientId": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
            "encounterId": encounter_id,
            "traumaType": "BURN",
            "chiefComplaints": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Test Injury",
                    "type": "trauma",
                    "part": "head",
                    "bodyParts": []
                }
            ],
            "status": "COMPLETE",
            "createdBy": "test@example.com",
            "startedAt": "2025-01-15T10:00:00.000Z"
        }
    
    def test_create_encounter(self, client, auth_headers, sample_encounter):
        """Test creating an encounter"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.post(
            "/encounter",
            json=sample_encounter,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data.get("encounter_id") == sample_encounter["id"]
    
    def test_create_encounter_invalid_data(self, client, auth_headers):
        """Test creating encounter with invalid data"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        invalid_payload = {"invalid": "data"}
        response = client.post(
            "/encounter",
            json=invalid_payload,
            headers=auth_headers
        )
        assert response.status_code in [400, 422]


class TestQueueEndpoints:
    """Tests for queue endpoints"""
    
    def test_get_queue_all(self, client, auth_headers):
        """Test getting all queue entries"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get("/queue", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_queue_by_status(self, client, auth_headers):
        """Test getting queue entries by status"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get(
            "/queue?status=PENDING",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verify all entries have PENDING status
        for entry in data:
            assert entry.get("status") == "PENDING"
    
    def test_get_queue_with_limit(self, client, auth_headers):
        """Test getting queue entries with limit"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        response = client.get(
            "/queue?limit=5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
    
    def test_update_queue_experity_action(self, client, auth_headers):
        """Test updating queue entry with experity action"""
        if not auth_headers:
            pytest.skip("Could not get auth token")
        
        # First, get a queue entry
        queue_response = client.get("/queue?limit=1", headers=auth_headers)
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if len(queue_data) > 0:
                queue_id = queue_data[0].get("queue_id")
                
                experity_action = {
                    "template": "Chest",
                    "bodyAreaKey": "Chest",
                    "mainProblem": "Cough"
                }
                
                update_response = client.post(
                    "/queue",
                    json={
                        "queue_id": queue_id,
                        "experityAction": experity_action
                    },
                    headers=auth_headers
                )
                assert update_response.status_code == 200
                data = update_response.json()
                assert data.get("parsed_payload", {}).get("experityAction") == experity_action


class TestExperityMapEndpoint:
    """Tests for the /experity/map endpoint with HMAC authentication"""
    
    @pytest.fixture
    def sample_queue_entry(self):
        """Sample queue entry for testing"""
        encounter_id = str(uuid.uuid4())
        return {
            "queue_entry": {
                "encounter_id": encounter_id,
                "raw_payload": {
                    "id": encounter_id,
                    "clientId": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
                    "traumaType": "BURN",
                    "status": "COMPLETE"
                }
            }
        }
    
    def test_experity_map_with_valid_hmac(
        self, client, hmac_secret, sample_queue_entry
    ):
        """Test /experity/map endpoint with valid HMAC signature"""
        headers = generate_hmac_headers(
            "POST",
            "/experity/map",
            sample_queue_entry,
            hmac_secret
        )
        
        response = client.post(
            "/experity/map",
            json=sample_queue_entry,
            headers=headers
        )
        # Status depends on your implementation
        # Could be 200 (success), 400 (validation error), or 500 (processing error)
        assert response.status_code in [200, 201, 400, 500]
    
    def test_experity_map_with_invalid_signature(
        self, client, sample_queue_entry
    ):
        """Test /experity/map endpoint with invalid HMAC signature"""
        headers = generate_hmac_headers(
            "POST",
            "/experity/map",
            sample_queue_entry,
            "wrong-secret-key"
        )
        
        response = client.post(
            "/experity/map",
            json=sample_queue_entry,
            headers=headers
        )
        # Should reject invalid signature
        assert response.status_code in [401, 403]
    
    def test_experity_map_missing_headers(self, client, sample_queue_entry):
        """Test /experity/map endpoint without HMAC headers"""
        response = client.post(
            "/experity/map",
            json=sample_queue_entry
        )
        # Should reject missing authentication
        assert response.status_code in [401, 403, 400]

