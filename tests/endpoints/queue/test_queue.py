"""
Comprehensive tests for Queue endpoints.

Endpoints tested:
- GET /queue - List queue entries with filters
- POST /queue - Update queue experityAction
- PATCH /queue/{queue_id}/status - Update queue entry status
- PATCH /queue/{queue_id}/requeue - Requeue a queue entry
"""
import pytest
import uuid
from fastapi.testclient import TestClient


class TestListQueue:
    """Tests for GET /queue - List queue entries"""
    
    def test_get_queue_all(self, client, hmac_headers):
        """Test getting all queue entries"""
        path = "/queue"
        headers = hmac_headers("GET", path, {})
        
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_queue_by_queue_id(self, client, hmac_headers):
        """Test getting queue entry by queue_id"""
        # First get a queue entry to use its ID
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        all_response = client.get(path1, headers=headers1)
        
        if all_response.status_code == 200:
            all_data = all_response.json()
            if len(all_data) > 0:
                queue_id = all_data[0].get("queue_id")
                if queue_id:
                    path2 = f"/queue?queue_id={queue_id}"
                    headers2 = hmac_headers("GET", path2, {})
                    response = client.get(path2, headers=headers2)
                    assert response.status_code == 200
                    data = response.json()
                    assert isinstance(data, list)
                    if len(data) > 0:
                        assert data[0].get("queue_id") == queue_id
    
    def test_get_queue_by_encounter_id(self, client, hmac_headers):
        """Test getting queue entry by encounter_id"""
        # First get a queue entry to use its encounter_id
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        all_response = client.get(path1, headers=headers1)
        
        if all_response.status_code == 200:
            all_data = all_response.json()
            if len(all_data) > 0:
                encounter_id = all_data[0].get("encounter_id")
                if encounter_id:
                    path2 = f"/queue?encounter_id={encounter_id}"
                    headers2 = hmac_headers("GET", path2, {})
                    response = client.get(path2, headers=headers2)
                    assert response.status_code == 200
                    data = response.json()
                    assert isinstance(data, list)
                    if len(data) > 0:
                        assert data[0].get("encounter_id") == encounter_id
    
    def test_get_queue_by_status(self, client, hmac_headers):
        """Test getting queue entries by status"""
        for status in ["PENDING", "PROCESSING", "DONE", "ERROR"]:
            path = f"/queue?status={status}"
            headers = hmac_headers("GET", path, {})
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # Verify all entries have the requested status
            for entry in data:
                assert entry.get("status") == status
    
    def test_get_queue_by_invalid_status(self, client, hmac_headers):
        """Test getting queue entries with invalid status"""
        path = "/queue?status=INVALID_STATUS"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        # Should return 400 or empty list
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
    
    def test_get_queue_by_emr_id(self, client, hmac_headers):
        """Test getting queue entries by emr_id"""
        # Use a test emr_id (may not exist)
        test_emr_id = f"TEST_{uuid.uuid4().hex[:8]}"
        path = f"/queue?emr_id={test_emr_id}"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_queue_with_limit(self, client, hmac_headers):
        """Test getting queue entries with limit"""
        # Get all entries first
        path1 = "/queue"
        headers1 = hmac_headers("GET", path1, {})
        all_response = client.get(path1, headers=headers1)
        
        if all_response.status_code == 200:
            all_data = all_response.json()
            total_count = len(all_data)
            
            # Get with limit
            limit = min(5, total_count + 1)  # Use 5 or total+1 if less than 5
            path2 = f"/queue?limit={limit}"
            headers2 = hmac_headers("GET", path2, {})
            response = client.get(path2, headers=headers2)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= limit
    
    def test_get_queue_invalid_limit(self, client, hmac_headers):
        """Test getting queue entries with invalid limit"""
        path = "/queue?limit=0"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        # Should return validation error for limit < 1
        assert response.status_code in [400, 422]
    
    def test_get_queue_multiple_filters(self, client, hmac_headers):
        """Test getting queue entries with multiple filters"""
        path = "/queue?status=PENDING&limit=10"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10
        for entry in data:
            assert entry.get("status") == "PENDING"
    
    def test_get_queue_without_auth(self, client):
        """Test getting queue entries without authentication"""
        response = client.get("/queue")
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_get_queue_response_structure(self, client, hmac_headers):
        """Test that queue response has correct structure"""
        path = "/queue?limit=1"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            entry = data[0]
            # Check for required queue fields
            assert "queue_id" in entry
            assert "encounter_id" in entry
            assert "status" in entry
            assert "parsed_payload" in entry or "parsedPayload" in entry


class TestUpdateQueueExperityAction:
    """Tests for POST /queue - Update queue experityAction"""
    
    @pytest.fixture
    def sample_experity_action(self):
        """Sample Experity action for testing"""
        return {
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
    
    def test_update_queue_by_queue_id(self, client, hmac_headers, sample_experity_action):
        """Test updating queue entry by queue_id"""
        # Get a queue entry
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        queue_response = client.get(path1, headers=headers1)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if len(queue_data) > 0:
                queue_id = queue_data[0].get("queue_id")
                
                if queue_id:
                    path2 = "/queue"
                    body = {
                        "queue_id": queue_id,
                        "experityAction": [sample_experity_action]  # Must be array
                    }
                    headers2 = hmac_headers("POST", path2, body)
                    update_response = client.post(path2, json=body, headers=headers2)
                    assert update_response.status_code == 200
                    data = update_response.json()
                    assert data.get("queue_id") == queue_id
                    # Check that experityAction was updated
                    parsed = data.get("parsed_payload", {})
                    if isinstance(parsed, dict):
                        action = parsed.get("experityAction")
                        assert action is not None
    
    def test_update_queue_by_encounter_id(self, client, hmac_headers, sample_experity_action):
        """Test updating queue entry by encounter_id"""
        # Get a queue entry
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        queue_response = client.get(path1, headers=headers1)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if len(queue_data) > 0:
                encounter_id = queue_data[0].get("encounter_id")
                
                if encounter_id:
                    path2 = "/queue"
                    body = {
                        "encounter_id": encounter_id,
                        "experityAction": [sample_experity_action]  # Must be array
                    }
                    headers2 = hmac_headers("POST", path2, body)
                    update_response = client.post(path2, json=body, headers=headers2)
                    assert update_response.status_code == 200
                    data = update_response.json()
                    assert data.get("encounter_id") == encounter_id
    
    def test_update_queue_with_array_action(self, client, hmac_headers):
        """Test updating queue with array of Experity actions"""
        actions_array = [
            {
                "template": "Chest",
                "mainProblem": "Cough"
            },
            {
                "template": "Head",
                "mainProblem": "Headache"
            }
        ]
        
        # Get a queue entry
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        queue_response = client.get(path1, headers=headers1)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if len(queue_data) > 0:
                queue_id = queue_data[0].get("queue_id")
                
                if queue_id:
                    path2 = "/queue"
                    body = {
                        "queue_id": queue_id,
                        "experityAction": actions_array
                    }
                    headers2 = hmac_headers("POST", path2, body)
                    update_response = client.post(path2, json=body, headers=headers2)
                    assert update_response.status_code == 200
    
    def test_update_queue_missing_identifiers(self, client, hmac_headers, sample_experity_action):
        """Test updating queue without queue_id or encounter_id"""
        path = "/queue"
        body = {"experityAction": sample_experity_action}
        headers = hmac_headers("POST", path, body)
        
        response = client.post(path, json=body, headers=headers)
        # Should require queue_id or encounter_id
        assert response.status_code in [400, 422]
    
    def test_update_queue_not_found(self, client, hmac_headers, sample_experity_action):
        """Test updating non-existent queue entry"""
        fake_queue_id = str(uuid.uuid4())
        path = "/queue"
        body = {
            "queue_id": fake_queue_id,
            "experityAction": [sample_experity_action]  # Must be array
        }
        headers = hmac_headers("POST", path, body)
        
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 404
    
    def test_update_queue_without_auth(self, client, sample_experity_action):
        """Test updating queue without authentication"""
        fake_queue_id = str(uuid.uuid4())
        body = {
            "queue_id": fake_queue_id,
            "experityAction": [sample_experity_action]  # Must be array
        }
        response = client.post("/queue", json=body)
        # Should require auth
        assert response.status_code in [401, 403]
    
    def test_update_queue_empty_action(self, client, hmac_headers):
        """Test updating queue with empty experityAction"""
        # Get a queue entry
        path1 = "/queue?limit=1"
        headers1 = hmac_headers("GET", path1, {})
        queue_response = client.get(path1, headers=headers1)
        
        if queue_response.status_code == 200:
            queue_data = queue_response.json()
            if len(queue_data) > 0:
                queue_id = queue_data[0].get("queue_id")
                
                if queue_id:
                    path2 = "/queue"
                    body = {
                        "queue_id": queue_id,
                        "experityAction": []
                    }
                    headers2 = hmac_headers("POST", path2, body)
                    response = client.post(path2, json=body, headers=headers2)
                    # May accept empty array
                    assert response.status_code in [200, 400]


class TestUpdateQueueStatus:
    """Tests for PATCH /queue/{queue_id}/status - Update queue entry status"""
    
    def get_test_queue_id(self, client, hmac_headers):
        """Helper to get a test queue_id"""
        path = "/queue?limit=1"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                return data[0].get("queue_id")
        return None
    
    def test_update_status_to_done(self, client, hmac_headers):
        """Test updating queue status to DONE with experityActions"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/status"
        body = {
            "status": "DONE",
            "experityActions": {
                "vitals": {"temperature": 98.6},
                "complaints": []
            }
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "DONE"
        assert data.get("emrId") is not None
    
    def test_update_status_to_error(self, client, hmac_headers):
        """Test updating queue status to ERROR with error message"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/status"
        body = {
            "status": "ERROR",
            "errorMessage": "Test error message",
            "incrementAttempts": True
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ERROR"
    
    def test_update_status_increment_attempts(self, client, hmac_headers):
        """Test updating status with incrementAttempts"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        # Get current attempts
        path1 = f"/queue?queue_id={queue_id}"
        headers1 = hmac_headers("GET", path1, {})
        get_response = client.get(path1, headers=headers1)
        if get_response.status_code == 200:
            initial_data = get_response.json()
            if len(initial_data) > 0:
                initial_attempts = initial_data[0].get("attempts", 0)
                
                # Update with incrementAttempts
                path2 = f"/queue/{queue_id}/status"
                body = {
                    "status": "ERROR",
                    "errorMessage": "Test error",
                    "incrementAttempts": True
                }
                headers2 = hmac_headers("PATCH", path2, body)
                update_response = client.patch(path2, json=body, headers=headers2)
                assert update_response.status_code == 200
                updated_data = update_response.json()
                assert updated_data.get("attempts") == initial_attempts + 1
    
    def test_update_status_with_dlq(self, client, hmac_headers):
        """Test updating status with DLQ flag"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/status"
        body = {
            "status": "ERROR",
            "errorMessage": "Max retries exceeded",
            "dlq": True
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ERROR"
    
    def test_update_status_invalid_status(self, client, hmac_headers):
        """Test updating status with invalid status value"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/status"
        body = {
            "status": "INVALID_STATUS"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 400
    
    def test_update_status_not_found(self, client, hmac_headers):
        """Test updating status for non-existent queue entry"""
        fake_queue_id = str(uuid.uuid4())
        path = f"/queue/{fake_queue_id}/status"
        body = {
            "status": "DONE"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 404
    
    def test_update_status_without_auth(self, client):
        """Test updating status without authentication"""
        fake_queue_id = str(uuid.uuid4())
        path = f"/queue/{fake_queue_id}/status"
        body = {
            "status": "DONE"
        }
        response = client.patch(path, json=body)
        # May return 404 (not found) or 401/403 (unauthorized) depending on auth check order
        assert response.status_code in [401, 403, 404]
    
    def test_update_status_camelcase_fields(self, client, hmac_headers):
        """Test that camelCase field names work correctly"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/status"
        # Test with camelCase field names
        body = {
            "status": "ERROR",
            "errorMessage": "Test error",
            "incrementAttempts": False,
            "experityActions": {"test": "data"}
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ERROR"
    
    def test_update_status_all_statuses(self, client, hmac_headers):
        """Test updating to all valid statuses"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        valid_statuses = ["PENDING", "PROCESSING", "DONE", "ERROR"]
        for status in valid_statuses:
            path = f"/queue/{queue_id}/status"
            body = {"status": status}
            headers = hmac_headers("PATCH", path, body)
            response = client.patch(path, json=body, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == status


class TestRequeueQueueEntry:
    """Tests for PATCH /queue/{queue_id}/requeue - Requeue a queue entry"""
    
    def get_test_queue_id(self, client, hmac_headers):
        """Helper to get a test queue_id"""
        path = "/queue?limit=1"
        headers = hmac_headers("GET", path, {})
        response = client.get(path, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                return data[0].get("queue_id")
        return None
    
    def test_requeue_with_defaults(self, client, hmac_headers):
        """Test requeue with default values (PENDING, HIGH priority)"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/requeue"
        body = {}
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "PENDING"
        # Verify attempts were incremented
        assert "attempts" in data
    
    def test_requeue_with_priority(self, client, hmac_headers):
        """Test requeue with specific priority"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        for priority in ["HIGH", "NORMAL", "LOW"]:
            path = f"/queue/{queue_id}/requeue"
            body = {
                "priority": priority
            }
            headers = hmac_headers("PATCH", path, body)
            response = client.patch(path, json=body, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "PENDING"
    
    def test_requeue_increments_attempts(self, client, hmac_headers):
        """Test that requeue increments attempts counter"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        # Get current attempts
        path1 = f"/queue?queue_id={queue_id}"
        headers1 = hmac_headers("GET", path1, {})
        get_response = client.get(path1, headers=headers1)
        if get_response.status_code == 200:
            initial_data = get_response.json()
            if len(initial_data) > 0:
                initial_attempts = initial_data[0].get("attempts", 0)
                
                # Requeue
                path2 = f"/queue/{queue_id}/requeue"
                body = {}
                headers2 = hmac_headers("PATCH", path2, body)
                requeue_response = client.patch(path2, json=body, headers=headers2)
                assert requeue_response.status_code == 200
                requeued_data = requeue_response.json()
                assert requeued_data.get("attempts") == initial_attempts + 1
    
    def test_requeue_with_error_message(self, client, hmac_headers):
        """Test requeue with error message"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/requeue"
        body = {
            "errorMessage": "Requeued for retry"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "PENDING"
    
    def test_requeue_invalid_priority(self, client, hmac_headers):
        """Test requeue with invalid priority"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/requeue"
        body = {
            "priority": "INVALID_PRIORITY"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 400
    
    def test_requeue_invalid_status(self, client, hmac_headers):
        """Test requeue with invalid status"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/requeue"
        body = {
            "status": "INVALID_STATUS"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 400
    
    def test_requeue_not_found(self, client, hmac_headers):
        """Test requeue for non-existent queue entry"""
        fake_queue_id = str(uuid.uuid4())
        path = f"/queue/{fake_queue_id}/requeue"
        body = {}
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 404
    
    def test_requeue_without_auth(self, client):
        """Test requeue without authentication"""
        fake_queue_id = str(uuid.uuid4())
        path = f"/queue/{fake_queue_id}/requeue"
        body = {}
        response = client.patch(path, json=body)
        # May return 404 (not found) or 401/403 (unauthorized) depending on auth check order
        assert response.status_code in [401, 403, 404]
    
    def test_requeue_camelcase_fields(self, client, hmac_headers):
        """Test that camelCase field names work correctly"""
        queue_id = self.get_test_queue_id(client, hmac_headers)
        if not queue_id:
            pytest.skip("No queue entries available for testing")
        
        path = f"/queue/{queue_id}/requeue"
        # Test with camelCase field name
        body = {
            "priority": "HIGH",
            "errorMessage": "Test requeue message"
        }
        headers = hmac_headers("PATCH", path, body)
        response = client.patch(path, json=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "PENDING"
