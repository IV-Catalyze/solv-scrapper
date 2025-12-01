"""
Shared pytest fixtures for all tests.

Tests are configured to hit PRODUCTION endpoints (https://app-97926.on-aptible.com)
but use STAGING HMAC secret for authentication.
"""
import pytest
import os
import json
import hmac
import hashlib
import base64
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, Any, Optional

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


def generate_hmac_headers(method: str, path: str, body: any, secret_key: str) -> dict:
    """
    Generate HMAC authentication headers for a request.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path (with query string if applicable)
        body: Request body (dict, str, or bytes). For GET requests, use None or empty dict.
        secret_key: HMAC secret key
        
    Returns:
        Dictionary with X-Timestamp and X-Signature headers
    """
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Convert body to bytes
    # For GET requests, body should be empty bytes
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        # Use default JSON serialization to match requests library
        # requests uses json.dumps() with default settings (includes spaces)
        # Note: Python 3.7+ preserves dict insertion order, so we don't sort keys
        body_str = json.dumps(body)
        body_bytes = body_str.encode('utf-8')
    elif isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif isinstance(body, bytes):
        body_bytes = body
    elif body is None:
        body_bytes = b''
    else:
        body_bytes = b''
    
    # Calculate body hash
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    
    # Create canonical string
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
    # Generate HMAC signature
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
    
    # Only add Content-Type for requests with body
    if method.upper() in ["POST", "PUT", "PATCH"] and body_bytes:
        headers["Content-Type"] = "application/json"
    
    return headers


@pytest.fixture
def api_base_url():
    """Production API base URL for testing"""
    return os.getenv(
        "API_BASE_URL",
        "https://app-97926.on-aptible.com"
    )


@pytest.fixture
def client(api_base_url):
    """
    HTTP client for making requests to production API.
    Uses requests library to hit actual production endpoints.
    """
    class ProductionAPIClient:
        """Client wrapper for production API requests"""
        
        def __init__(self, base_url: str):
            self.base_url = base_url.rstrip('/')
        
        def _make_request(
            self,
            method: str,
            path: str,
            headers: Optional[Dict[str, str]] = None,
            json_data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
        ) -> requests.Response:
            """Make HTTP request to production API"""
            url = f"{self.base_url}{path}"
            return requests.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                json=json_data,
                params=params,
                timeout=30
            )
        
        def get(self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
            """GET request"""
            return self._make_request("GET", path, headers=headers, params=kwargs.get('params'))
        
        def post(self, path: str, json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
            """POST request"""
            return self._make_request("POST", path, headers=headers, json_data=json)
        
        def patch(self, path: str, json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
            """PATCH request"""
            return self._make_request("PATCH", path, headers=headers, json_data=json)
        
        def put(self, path: str, json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
            """PUT request"""
            return self._make_request("PUT", path, headers=headers, json_data=json)
        
        def delete(self, path: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
            """DELETE request"""
            return self._make_request("DELETE", path, headers=headers)
    
    return ProductionAPIClient(api_base_url)


@pytest.fixture
def hmac_secret():
    """
    HMAC secret for testing - uses STAGING secret.
    
    Tests hit PRODUCTION endpoints but authenticate with STAGING HMAC secret.
    """
    return os.getenv(
        "INTELLIVISIT_STAGING_HMAC_SECRET",
        "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM"
    )


@pytest.fixture
def hmac_headers(hmac_secret):
    """
    Generate HMAC headers for authenticated requests.
    This is a factory fixture - call it with method, path, and body.
    
    Uses STAGING HMAC secret to authenticate against PRODUCTION endpoints.
    
    Usage:
        headers = hmac_headers("GET", "/patients?locationId=AXjwbE", {})
        response = client.get("/patients?locationId=AXjwbE", headers=headers)
    """
    def _generate(method: str, path: str, body: any = None) -> dict:
        if body is None:
            body = {}
        return generate_hmac_headers(method, path, body, hmac_secret)
    return _generate


@pytest.fixture
def staging_client_id():
    """Staging client ID for testing"""
    return "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"


@pytest.fixture
def production_client_id():
    """Production client ID for testing"""
    return "Prod-1f190fe5-d799-4786-bce2-37c3ad2c1561"


@pytest.fixture
def test_location_id():
    """Default test location ID"""
    return "AXjwbE"

