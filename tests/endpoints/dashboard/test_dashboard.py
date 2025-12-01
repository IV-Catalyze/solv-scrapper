"""
Comprehensive tests for Dashboard endpoints.

Endpoints tested:
- GET / - Render patient dashboard
- GET /experity/chat - Experity Mapper Chat UI
"""
import pytest
from fastapi.testclient import TestClient


class TestRootDashboard:
    """Tests for GET / - Root dashboard endpoint"""
    
    def test_get_root_dashboard(self, client):
        """Test that root dashboard endpoint returns HTML"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_get_root_with_location_id(self, client, test_location_id):
        """Test root dashboard with locationId parameter"""
        response = client.get(f"/?locationId={test_location_id}")
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")
    
    def test_get_root_with_statuses(self, client, test_location_id):
        """Test root dashboard with statuses filter"""
        response = client.get(
            f"/?locationId={test_location_id}&statuses=checked_in&statuses=confirmed"
        )
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
    
    def test_get_root_with_limit(self, client, test_location_id):
        """Test root dashboard with limit parameter"""
        response = client.get(f"/?locationId={test_location_id}&limit=10")
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
    
    def test_get_root_with_all_filters(self, client, test_location_id):
        """Test root dashboard with all query parameters"""
        response = client.get(
            f"/?locationId={test_location_id}&statuses=checked_in&limit=5"
        )
        # Accept 502 if remote API is unavailable
        assert response.status_code in [200, 502]
    
    def test_get_root_invalid_limit(self, client, test_location_id):
        """Test root dashboard with invalid limit (should be >= 1)"""
        response = client.get(f"/?locationId={test_location_id}&limit=0")
        # Should return validation error
        assert response.status_code in [400, 422]
    
    def test_get_root_without_location_id(self, client):
        """Test root dashboard without locationId (may use DEFAULT_LOCATION_ID)"""
        response = client.get("/")
        # Should work if DEFAULT_LOCATION_ID is set, otherwise may return error
        assert response.status_code in [200, 400]


class TestExperityChatUI:
    """Tests for GET /experity/chat - Experity Mapper Chat UI"""
    
    def test_get_experity_chat_ui(self, client):
        """Test that Experity chat UI endpoint returns HTML"""
        response = client.get("/experity/chat")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_experity_chat_ui_content(self, client):
        """Test that Experity chat UI contains expected content"""
        response = client.get("/experity/chat")
        assert response.status_code == 200
        # Check that it's HTML content
        content = response.text
        assert isinstance(content, str)
        assert len(content) > 0

