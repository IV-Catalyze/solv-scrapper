#!/usr/bin/env python3
"""
Test script for alert endpoints.

This script tests all alert endpoints:
- POST /alerts - Create alert
- GET /alerts - List alerts with filters
- PATCH /alerts/{alertId}/resolve - Resolve alert
"""

import os
import sys
import json
import requests
import hmac
import hashlib
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Configuration
API_BASE_URL = os.getenv('API_URL', 'http://localhost:8000')
API_TOKEN = os.getenv('API_TOKEN', '')  # Optional, for HMAC auth
HMAC_SECRET = os.getenv('HMAC_SECRET', os.getenv('INTELLIVISIT_STAGING_HMAC_SECRET', ''))

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_test(name: str):
    """Print test name."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test: {name}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")


def print_success(message: str):
    """Print success message."""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message: str):
    """Print error message."""
    print(f"{RED}✗ {message}{RESET}")


def print_info(message: str):
    """Print info message."""
    print(f"{YELLOW}ℹ {message}{RESET}")


def generate_hmac_headers(method: str, path: str, body: Any, secret_key: str) -> Dict[str, str]:
    """Generate HMAC authentication headers for a request."""
    if not secret_key:
        return {}
    
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Convert body to bytes
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        body_str = json.dumps(body, separators=(',', ':'))  # Compact JSON
        body_bytes = body_str.encode('utf-8')
    elif isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif isinstance(body, bytes):
        body_bytes = body
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
    
    return {
        'X-Timestamp': timestamp,
        'X-Signature': signature_b64
    }


def make_request(method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    """Make HTTP request to API."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {
        'Content-Type': 'application/json',
    }
    
    # Add HMAC authentication for POST requests if secret is available
    if method == 'POST' and HMAC_SECRET:
        # Extract path from endpoint (without query params for HMAC)
        path = endpoint.split('?')[0]
        hmac_headers = generate_hmac_headers(method, path, data, HMAC_SECRET)
        headers.update(hmac_headers)
    elif API_TOKEN:
        # Fallback to Bearer token if provided
        headers['Authorization'] = f'Bearer {API_TOKEN}'
    
    if method == 'GET':
        # For GET requests, try to use session auth by getting a session cookie
        # For now, we'll just make the request and see what happens
        response = requests.get(url, headers=headers, params=params, allow_redirects=False)
        # If redirected to login, try to get session
        if response.status_code == 307 or response.status_code == 302:
            # Try with a session - for testing, we might need to login first
            # For now, let's just return the response
            pass
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    elif method == 'PATCH':
        # PATCH also needs session auth, similar to GET
        response = requests.patch(url, headers=headers, allow_redirects=False)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    return response


def test_create_alert() -> Optional[str]:
    """Test POST /alerts endpoint."""
    print_test("POST /alerts - Create Alert")
    
    # Test 1: Create a critical alert
    print_info("Creating critical alert...")
    alert_data = {
        "source": "vm",
        "sourceId": "server1-vm1",
        "severity": "critical",
        "message": "UiPath process stopped unexpectedly",
        "details": {
            "errorCode": "PROCESS_NOT_FOUND",
            "lastKnownStatus": "running",
            "timestamp": datetime.now().isoformat() + 'Z'
        }
    }
    
    response = make_request('POST', '/alerts', data=alert_data)
    
    if response.status_code == 200:
        result = response.json()
        print_success(f"Alert created successfully")
        print(f"  Alert ID: {result.get('alertId')}")
        print(f"  Success: {result.get('success')}")
        print(f"  Notification Sent: {result.get('notificationSent')}")
        print(f"  Created At: {result.get('createdAt')}")
        return result.get('alertId')
    else:
        print_error(f"Failed to create alert: {response.status_code}")
        print(f"  Response: {response.text}")
        return None
    
    # Test 2: Create a warning alert
    print_info("Creating warning alert...")
    alert_data2 = {
        "source": "server",
        "sourceId": "server1",
        "severity": "warning",
        "message": "High CPU usage detected",
        "details": {
            "cpuUsage": 85.5,
            "threshold": 80.0
        }
    }
    
    response2 = make_request('POST', '/alerts', data=alert_data2)
    
    if response2.status_code == 200:
        result2 = response2.json()
        print_success(f"Warning alert created successfully")
        print(f"  Alert ID: {result2.get('alertId')}")
        return result2.get('alertId')
    else:
        print_error(f"Failed to create warning alert: {response.status_code}")
        print(f"  Response: {response2.text}")
    
    # Test 3: Invalid source
    print_info("Testing invalid source (should fail)...")
    invalid_data = {
        "source": "invalid",
        "sourceId": "test",
        "severity": "critical",
        "message": "Test"
    }
    
    response3 = make_request('POST', '/alerts', data=invalid_data)
    
    if response3.status_code == 400:
        print_success("Invalid source correctly rejected")
    else:
        print_error(f"Expected 400 for invalid source, got {response3.status_code}")
    
    # Test 4: Missing required field
    print_info("Testing missing required field (should fail)...")
    missing_field_data = {
        "source": "vm",
        "severity": "critical",
        "message": "Test"
        # Missing sourceId
    }
    
    response4 = make_request('POST', '/alerts', data=missing_field_data)
    
    if response4.status_code in [400, 422]:
        print_success("Missing field correctly rejected")
    else:
        print_error(f"Expected 400/422 for missing field, got {response4.status_code}")
    
    return None


def test_get_alerts(alert_id: Optional[str] = None):
    """Test GET /alerts endpoint."""
    print_test("GET /alerts - List Alerts")
    
    # Test 1: Get all alerts (unresolved)
    print_info("Getting all unresolved alerts...")
    response = make_request('GET', '/alerts', params={'resolved': False})
    
    if response.status_code == 200:
        result = response.json()
        alerts = result.get('alerts', [])
        total = result.get('total', 0)
        print_success(f"Retrieved {len(alerts)} alerts (total: {total})")
        if alerts:
            print(f"  First alert: {alerts[0].get('alertId')} - {alerts[0].get('message')}")
    else:
        print_error(f"Failed to get alerts: {response.status_code}")
        print(f"  Response: {response.text}")
        return
    
    # Test 2: Filter by source
    print_info("Filtering by source=vm...")
    response2 = make_request('GET', '/alerts', params={'source': 'vm', 'resolved': False})
    
    if response2.status_code == 200:
        result2 = response2.json()
        alerts2 = result2.get('alerts', [])
        print_success(f"Retrieved {len(alerts2)} alerts from vm source")
    else:
        print_error(f"Failed to filter by source: {response2.status_code}")
    
    # Test 3: Filter by severity
    print_info("Filtering by severity=critical...")
    response3 = make_request('GET', '/alerts', params={'severity': 'critical', 'resolved': False})
    
    if response3.status_code == 200:
        result3 = response3.json()
        alerts3 = result3.get('alerts', [])
        print_success(f"Retrieved {len(alerts3)} critical alerts")
    else:
        print_error(f"Failed to filter by severity: {response3.status_code}")
    
    # Test 4: Pagination
    print_info("Testing pagination (limit=1, offset=0)...")
    response4 = make_request('GET', '/alerts', params={'limit': 1, 'offset': 0, 'resolved': False})
    
    if response4.status_code == 200:
        result4 = response4.json()
        alerts4 = result4.get('alerts', [])
        limit = result4.get('limit', 0)
        offset = result4.get('offset', 0)
        print_success(f"Pagination works: limit={limit}, offset={offset}, returned={len(alerts4)}")
    else:
        print_error(f"Failed to test pagination: {response4.status_code}")
    
    # Test 5: Include resolved alerts
    print_info("Getting all alerts including resolved...")
    response5 = make_request('GET', '/alerts', params={'resolved': True})
    
    if response5.status_code == 200:
        result5 = response5.json()
        alerts5 = result5.get('alerts', [])
        print_success(f"Retrieved {len(alerts5)} alerts (including resolved)")
    else:
        print_error(f"Failed to get all alerts: {response5.status_code}")


def test_resolve_alert(alert_id: Optional[str] = None):
    """Test PATCH /alerts/{alertId}/resolve endpoint."""
    print_test("PATCH /alerts/{alertId}/resolve - Resolve Alert")
    
    if not alert_id:
        # Get an unresolved alert first
        print_info("Getting an unresolved alert to resolve...")
        response = make_request('GET', '/alerts', params={'resolved': False, 'limit': 1})
        
        if response.status_code == 200:
            result = response.json()
            alerts = result.get('alerts', [])
            if alerts:
                alert_id = alerts[0].get('alertId')
                print_info(f"Using alert ID: {alert_id}")
            else:
                print_error("No unresolved alerts found to test resolution")
                return
        else:
            print_error(f"Failed to get alerts: {response.status_code}")
            return
    
    # Test 1: Resolve alert
    print_info(f"Resolving alert {alert_id}...")
    response = make_request('PATCH', f'/alerts/{alert_id}/resolve')
    
    if response.status_code == 200:
        result = response.json()
        print_success(f"Alert resolved successfully")
        print(f"  Alert ID: {result.get('alertId')}")
        print(f"  Success: {result.get('success')}")
        print(f"  Resolved At: {result.get('resolvedAt')}")
    else:
        print_error(f"Failed to resolve alert: {response.status_code}")
        print(f"  Response: {response.text}")
    
    # Test 2: Try to resolve non-existent alert
    print_info("Testing resolve on non-existent alert (should fail)...")
    fake_id = "00000000-0000-0000-0000-000000000000"
    response2 = make_request('PATCH', f'/alerts/{fake_id}/resolve')
    
    if response2.status_code == 404:
        print_success("Non-existent alert correctly rejected")
    else:
        print_error(f"Expected 404 for non-existent alert, got {response2.status_code}")
    
    # Test 3: Try to resolve with invalid UUID format
    print_info("Testing resolve with invalid UUID format (should fail)...")
    response3 = make_request('PATCH', '/alerts/invalid-uuid/resolve')
    
    if response3.status_code == 400:
        print_success("Invalid UUID format correctly rejected")
    else:
        print_error(f"Expected 400 for invalid UUID, got {response3.status_code}")


def main():
    """Run all tests."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Alert Endpoints Test Suite{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"\nAPI Base URL: {API_BASE_URL}")
    if HMAC_SECRET:
        print(f"Authentication: HMAC (secret configured)")
    elif API_TOKEN:
        print(f"Authentication: Bearer Token")
    else:
        print(f"Authentication: None (may fail if auth is required)")
        print_info("Set HMAC_SECRET or INTELLIVISIT_STAGING_HMAC_SECRET for POST requests")
        print_info("GET/PATCH requests require session auth (login first)")
    
    # Test connectivity
    print_info("Testing API connectivity...")
    try:
        response = requests.get(f"{API_BASE_URL}/docs", timeout=5)
        if response.status_code in [200, 404]:
            print_success("API is reachable")
        else:
            print_error(f"API returned unexpected status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot connect to API: {str(e)}")
        print(f"  Make sure the API server is running at {API_BASE_URL}")
        sys.exit(1)
    
    # Run tests
    alert_id = test_create_alert()
    test_get_alerts(alert_id)
    test_resolve_alert(alert_id)
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Suite Complete{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


if __name__ == '__main__':
    main()
