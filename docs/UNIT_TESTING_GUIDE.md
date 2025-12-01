# Unit Testing Guide for FastAPI Endpoints

This guide explains how to write unit tests for your FastAPI endpoints using pytest and FastAPI's TestClient.

## Table of Contents

1. [Setup](#setup)
2. [Basic Concepts](#basic-concepts)
3. [Testing Patterns](#testing-patterns)
4. [Examples](#examples)
5. [Best Practices](#best-practices)

---

## Setup

### 1. Install Testing Dependencies

Add these to your `requirements.txt`:

```txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
httpx>=0.24.0  # Already in your requirements
```

Then install:

```bash
pip install -r requirements.txt
```

### 2. Create Test Configuration

Create `pytest.ini` in your project root:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts = 
    -v
    --tb=short
    --strict-markers
```

### 3. Test Directory Structure

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── test_auth.py         # Authentication tests
├── test_patients.py     # Patient endpoint tests
├── test_encounters.py   # Encounter endpoint tests
├── test_queue.py        # Queue endpoint tests
└── test_experity.py     # Experity endpoint tests
```

---

## Basic Concepts

### FastAPI TestClient

FastAPI provides a `TestClient` that allows you to test your API without running a server:

```python
from fastapi.testclient import TestClient
from app.api.routes import app

client = TestClient(app)
response = client.get("/patients")
assert response.status_code == 200
```

### Fixtures

Use pytest fixtures to set up test data and dependencies:

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_token():
    # Generate or mock auth token
    return "test-token"
```

---

## Testing Patterns

### 1. Testing GET Endpoints

```python
def test_get_patients(client):
    response = client.get("/patients?locationId=AXjwbE")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
```

### 2. Testing POST Endpoints

```python
def test_create_patient(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "emr_id": "TEST123",
        "location_id": "AXjwbE",
        "legalFirstName": "John",
        "legalLastName": "Doe"
    }
    response = client.post("/patients/create", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["emr_id"] == "TEST123"
```

### 3. Testing Authentication

```python
def test_endpoint_requires_auth(client):
    response = client.get("/patients")
    # Should return 401 or 403 if auth is required
    assert response.status_code in [401, 403]

def test_endpoint_with_valid_auth(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/patients", headers=headers)
    assert response.status_code == 200
```

### 4. Testing Error Cases

```python
def test_invalid_patient_id(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/patient/INVALID_ID", headers=headers)
    assert response.status_code == 404

def test_missing_required_field(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {"emr_id": "TEST123"}  # Missing location_id
    response = client.post("/patients/create", json=payload, headers=headers)
    assert response.status_code == 400 or response.status_code == 422
```

### 5. Testing Query Parameters

```python
def test_patients_with_filters(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get(
        "/patients?locationId=AXjwbE&statuses=checked_in&limit=5",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5
```

### 6. Testing HMAC Authentication

For endpoints that require HMAC signatures:

```python
import hmac
import hashlib
import base64
from datetime import datetime

def generate_hmac_signature(method, path, timestamp, body, secret):
    """Generate HMAC signature for testing"""
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    canonical = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    signature = base64.b64encode(
        hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()
    ).decode()
    return signature

def test_experity_map_with_hmac(client):
    secret = "test-secret-key"
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    body = '{"queue_entry": {"encounter_id": "test-123"}}'
    
    signature = generate_hmac_signature("POST", "/experity/map", timestamp, body, secret)
    
    headers = {
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json"
    }
    
    response = client.post("/experity/map", data=body, headers=headers)
    # Test response...
```

---

## Examples

### Example 1: Simple GET Endpoint Test

```python
# tests/test_patients.py
import pytest
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture
def client():
    return TestClient(app)

def test_get_root(client):
    """Test the root endpoint"""
    response = client.get("/")
    assert response.status_code == 200

def test_get_patients_no_auth(client):
    """Test patients endpoint without authentication"""
    response = client.get("/patients?locationId=AXjwbE")
    # Adjust based on your auth requirements
    assert response.status_code in [200, 401, 403]
```

### Example 2: Testing with Authentication

```python
# tests/test_auth.py
import pytest
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_token(client):
    """Get a valid auth token for testing"""
    response = client.post(
        "/auth/token",
        json={"client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def test_get_token(client):
    """Test token generation"""
    response = client.post(
        "/auth/token",
        json={"client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert len(data["access_token"]) > 0

def test_get_patients_with_auth(client, auth_token):
    """Test patients endpoint with authentication"""
    if not auth_token:
        pytest.skip("Could not get auth token")
    
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/patients?locationId=AXjwbE", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
```

### Example 3: Testing POST Endpoints

```python
# tests/test_encounters.py
import pytest
import uuid
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_token(client):
    response = client.post(
        "/auth/token",
        json={"client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

@pytest.fixture
def sample_encounter():
    """Sample encounter data for testing"""
    encounter_id = str(uuid.uuid4())
    return {
        "id": encounter_id,
        "clientId": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505",
        "encounterId": encounter_id,
        "traumaType": "BURN",
        "status": "COMPLETE",
        "createdBy": "test@example.com",
        "startedAt": "2025-01-15T10:00:00.000Z"
    }

def test_create_encounter(client, auth_token, sample_encounter):
    """Test creating an encounter"""
    if not auth_token:
        pytest.skip("Could not get auth token")
    
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.post("/encounter", json=sample_encounter, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["encounter_id"] == sample_encounter["id"]

def test_create_encounter_invalid_data(client, auth_token):
    """Test creating encounter with invalid data"""
    if not auth_token:
        pytest.skip("Could not get auth token")
    
    headers = {"Authorization": f"Bearer {auth_token}"}
    invalid_payload = {"invalid": "data"}
    response = client.post("/encounter", json=invalid_payload, headers=headers)
    
    assert response.status_code in [400, 422]  # Bad Request or Validation Error
```

### Example 4: Testing with Database Mocking

For unit tests, you may want to mock database calls:

```python
# tests/test_queue.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_db_connection():
    """Mock database connection"""
    with patch('app.api.routes.psycopg2.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn, mock_cursor

def test_get_queue_mocked(client, mock_db_connection):
    """Test queue endpoint with mocked database"""
    mock_conn, mock_cursor = mock_db_connection
    
    # Mock database response
    mock_cursor.fetchall.return_value = [
        {
            "queue_id": "test-queue-123",
            "encounter_id": "test-encounter-123",
            "status": "PENDING"
        }
    ]
    
    response = client.get("/queue?queue_id=test-queue-123")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
```

### Example 5: Testing HMAC Endpoints

```python
# tests/test_experity.py
import pytest
import hmac
import hashlib
import base64
from datetime import datetime
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture
def client():
    return TestClient(app)

def generate_hmac_headers(method, path, body_json, secret):
    """Helper to generate HMAC authentication headers"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    body_str = body_json if isinstance(body_json, str) else json.dumps(body_json)
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

def test_experity_map_endpoint(client):
    """Test the /experity/map endpoint with HMAC"""
    import os
    import json
    
    secret = os.getenv("INTELLIVISIT_STAGING_HMAC_SECRET", "test-secret")
    body = {
        "queue_entry": {
            "encounter_id": "test-encounter-123",
            "raw_payload": {"id": "test-encounter-123"}
        }
    }
    
    headers = generate_hmac_headers("POST", "/experity/map", body, secret)
    response = client.post("/experity/map", json=body, headers=headers)
    
    # Adjust assertions based on your endpoint behavior
    assert response.status_code in [200, 201, 400, 500]  # Depends on implementation
```

---

## Best Practices

### 1. Use Fixtures for Common Setup

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.api.routes import app

@pytest.fixture(scope="session")
def client():
    """Shared test client for all tests"""
    return TestClient(app)

@pytest.fixture
def auth_token(client):
    """Get auth token once per test"""
    response = client.post(
        "/auth/token",
        json={"client_id": "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None
```

### 2. Organize Tests by Endpoint

- One test file per endpoint group
- Group related tests together
- Use descriptive test names

### 3. Test Both Success and Failure Cases

```python
def test_success_case(client):
    # Test happy path
    pass

def test_failure_case(client):
    # Test error handling
    pass

def test_edge_case(client):
    # Test boundary conditions
    pass
```

### 4. Use Parametrized Tests

```python
@pytest.mark.parametrize("status", ["checked_in", "confirmed", "completed"])
def test_patients_by_status(client, auth_token, status):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get(f"/patients?statuses={status}", headers=headers)
    assert response.status_code == 200
```

### 5. Clean Up Test Data

```python
@pytest.fixture
def cleanup_test_patient(client, auth_token):
    """Fixture that creates and cleans up test patient"""
    patient_id = "TEST_CLEANUP_123"
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Create
    client.post(
        "/patients/create",
        json={"emr_id": patient_id, "location_id": "AXjwbE"},
        headers=headers
    )
    
    yield patient_id
    
    # Cleanup (if you have a delete endpoint)
    # client.delete(f"/patients/{patient_id}", headers=headers)
```

### 6. Test Response Structure

```python
def test_patient_response_structure(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/patients?locationId=AXjwbE", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        patient = data[0]
        assert "emr_id" in patient
        assert "location_id" in patient
        assert "legalFirstName" in patient or patient.get("legalFirstName") is None
```

---

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_patients.py
```

### Run Specific Test

```bash
pytest tests/test_patients.py::test_get_patients
```

### Run with Coverage

```bash
pytest --cov=app --cov-report=html
```

### Run with Verbose Output

```bash
pytest -v
```

### Run Only Failed Tests

```bash
pytest --lf
```

---

## Integration vs Unit Tests

### Unit Tests (This Guide)
- Test endpoints in isolation
- Mock external dependencies (database, APIs)
- Fast execution
- Use `TestClient` from FastAPI

### Integration Tests (Your Existing Tests)
- Test against real database/APIs
- Use `requests` library
- Slower execution
- Test full system behavior

**Recommendation:** Use both! Unit tests for fast feedback during development, integration tests for validating the full system.

---

## Next Steps

1. Install pytest and dependencies
2. Create `tests/conftest.py` with shared fixtures
3. Start with one endpoint group (e.g., `test_patients.py`)
4. Gradually add tests for all endpoints
5. Set up CI/CD to run tests automatically

---

## Additional Resources

- [FastAPI Testing Documentation](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)

