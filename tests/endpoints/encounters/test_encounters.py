"""
Comprehensive tests for Encounter endpoints.

Endpoints tested:
- POST /encounter - Create or update encounter record
"""
import pytest
import uuid
from fastapi.testclient import TestClient


class TestCreateEncounter:
    """Tests for POST /encounter - Create encounter endpoint"""
    
    @pytest.fixture
    def sample_encounter(self, staging_client_id):
        """Sample encounter data for testing"""
        encounter_id = str(uuid.uuid4())
        return {
            "id": encounter_id,
            "clientId": staging_client_id,
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
                    "description": "Chemical burn",
                    "type": "trauma",
                    "part": "head",
                    "bodyParts": []
                }
            ],
            "status": "COMPLETE",
            "createdBy": "test@example.com",
            "startedAt": "2025-01-15T10:00:00.000Z",
            "updatedAt": "2025-01-15T10:00:00.000Z",
            "createdAt": "2025-01-15T10:00:00.000Z"
        }
    
    def test_create_encounter_success(self, client, hmac_headers, sample_encounter):
        """Test creating an encounter successfully"""
        path = "/encounter"
        headers = hmac_headers("POST", path, sample_encounter)
        
        response = client.post(path, json=sample_encounter, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data.get("encounter_id") == sample_encounter["id"]
        assert "created_at" in data or "message" in data
    
    def test_create_encounter_missing_chief_complaints(self, client, hmac_headers, staging_client_id):
        """Test creating encounter without chiefComplaints (required)"""
        encounter_id = str(uuid.uuid4())
        incomplete_encounter = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "encounterId": encounter_id,
            "status": "COMPLETE"
            # Missing chiefComplaints
        }
        
        path = "/encounter"
        headers = hmac_headers("POST", path, incomplete_encounter)
        response = client.post(path, json=incomplete_encounter, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_encounter_empty_chief_complaints(self, client, hmac_headers, staging_client_id):
        """Test creating encounter with empty chiefComplaints array"""
        encounter_id = str(uuid.uuid4())
        encounter_with_empty_complaints = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "encounterId": encounter_id,
            "chiefComplaints": [],
            "status": "COMPLETE"
        }
        
        path = "/encounter"
        headers = hmac_headers("POST", path, encounter_with_empty_complaints)
        response = client.post(path, json=encounter_with_empty_complaints, headers=headers)
        # May reject empty array or accept it
        assert response.status_code in [201, 400, 422]
    
    def test_create_encounter_missing_encounter_id(self, client, hmac_headers, staging_client_id):
        """Test creating encounter without encounterId"""
        encounter_id = str(uuid.uuid4())
        encounter_missing_id = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "chiefComplaints": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Test",
                    "type": "trauma",
                    "part": "head"
                }
            ]
            # Missing encounterId
        }
        
        path = "/encounter"
        headers = hmac_headers("POST", path, encounter_missing_id)
        response = client.post(path, json=encounter_missing_id, headers=headers)
        # May use 'id' field or require encounterId
        assert response.status_code in [201, 400, 422]
    
    def test_create_encounter_without_auth(self, client, sample_encounter):
        """Test creating encounter without authentication"""
        response = client.post("/encounter", json=sample_encounter)
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_create_encounter_invalid_data(self, client, hmac_headers):
        """Test creating encounter with invalid data structure"""
        invalid_data = {"invalid": "data", "not": "an encounter"}
        path = "/encounter"
        headers = hmac_headers("POST", path, invalid_data)
        
        response = client.post(path, json=invalid_data, headers=headers)
        assert response.status_code in [400, 422]
    
    def test_create_encounter_with_trauma_questions(self, client, hmac_headers, staging_client_id):
        """Test creating encounter with traumaQuestions"""
        encounter_id = str(uuid.uuid4())
        encounter_with_questions = {
            "id": encounter_id,
            "clientId": staging_client_id,
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
            "traumaQuestions": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "burned",
                    "question": "What burned you?",
                    "answer": "Chemicals",
                    "clientId": staging_client_id,
                    "encounterId": encounter_id
                }
            ],
            "status": "COMPLETE"
        }
        
        path = "/encounter"
        headers = hmac_headers("POST", path, encounter_with_questions)
        response = client.post(path, json=encounter_with_questions, headers=headers)
        assert response.status_code == 201
    
    def test_create_encounter_with_attributes(self, client, hmac_headers, staging_client_id):
        """Test creating encounter with patient attributes"""
        encounter_id = str(uuid.uuid4())
        encounter_with_attributes = {
            "id": encounter_id,
            "clientId": staging_client_id,
            "encounterId": encounter_id,
            "chiefComplaints": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Test",
                    "type": "trauma",
                    "part": "head"
                }
            ],
            "attributes": {
                "gender": "male",
                "ageYears": 30,
                "heightCm": 175,
                "weightKg": 70
            },
            "status": "COMPLETE"
        }
        
        path = "/encounter"
        headers = hmac_headers("POST", path, encounter_with_attributes)
        response = client.post(path, json=encounter_with_attributes, headers=headers)
        assert response.status_code == 201
    
    def test_create_encounter_update_existing(self, client, hmac_headers, sample_encounter):
        """Test that creating encounter with existing ID updates it"""
        path = "/encounter"
        
        # Create encounter first
        headers1 = hmac_headers("POST", path, sample_encounter)
        create_response = client.post(path, json=sample_encounter, headers=headers1)
        
        if create_response.status_code == 201:
            # Update the encounter
            updated_encounter = sample_encounter.copy()
            updated_encounter["status"] = "UPDATED"
            
            headers2 = hmac_headers("POST", path, updated_encounter)
            update_response = client.post(path, json=updated_encounter, headers=headers2)
            assert update_response.status_code == 201
            data = update_response.json()
            assert data.get("encounter_id") == sample_encounter["id"]
    
    def test_create_encounter_with_emr_id(self, client, hmac_headers, staging_client_id, test_location_id):
        """Test creating encounter with emr_id linking to patient"""
        # First create a patient
        patient_data = {
            "emr_id": f"TEST_EMR_{uuid.uuid4().hex[:8]}",
            "location_id": test_location_id,
            "legalFirstName": "Test",
            "legalLastName": "Patient"
        }
        
        patient_path = "/patients/create"
        patient_headers = hmac_headers("POST", patient_path, patient_data)
        patient_response = client.post(patient_path, json=patient_data, headers=patient_headers)
        
        if patient_response.status_code in [200, 201]:
            # Create encounter linked to patient
            encounter_id = str(uuid.uuid4())
            encounter_with_emr = {
                "id": encounter_id,
                "clientId": staging_client_id,
                "encounterId": encounter_id,
                "emrId": patient_data["emr_id"],
                "chiefComplaints": [
                    {
                        "id": str(uuid.uuid4()),
                        "description": "Test",
                        "type": "trauma",
                        "part": "head"
                    }
                ],
                "status": "COMPLETE"
            }
            
            encounter_path = "/encounter"
            encounter_headers = hmac_headers("POST", encounter_path, encounter_with_emr)
            response = client.post(encounter_path, json=encounter_with_emr, headers=encounter_headers)
            assert response.status_code == 201
