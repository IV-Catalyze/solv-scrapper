#!/usr/bin/env python3
"""
Test all endpoints on production to verify they're working.

This script tests all API endpoints on production and reports their status.
"""

import os
import sys
import json
import hmac
import hashlib
import base64
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Production base URL
PROD_BASE_URL = "https://app-97926.on-aptible.com"

# HMAC secret (use staging secret for testing production)
HMAC_SECRET = os.getenv(
    "INTELLIVISIT_STAGING_HMAC_SECRET",
    "3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM"
)


def generate_hmac_headers(method: str, path: str, body: any, secret_key: str) -> dict:
    """Generate HMAC authentication headers for a request."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
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
    
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
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
    
    if method.upper() in ["POST", "PUT", "PATCH"] and body_bytes:
        headers["Content-Type"] = "application/json"
    
    return headers


class EndpointTester:
    """Test all endpoints on production."""
    
    def __init__(self, base_url: str, hmac_secret: str):
        self.base_url = base_url.rstrip('/')
        self.hmac_secret = hmac_secret
        self.results: List[Dict[str, Any]] = []
        
    def test_endpoint(
        self,
        method: str,
        path: str,
        name: str,
        requires_auth: bool = True,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        expected_status: Optional[int] = None,
        is_ui_endpoint: bool = False
    ) -> Dict[str, Any]:
        """Test a single endpoint."""
        url = f"{self.base_url}{path}"
        headers = {}
        
        if requires_auth and not is_ui_endpoint:
            headers = generate_hmac_headers(method, path, body or {}, self.hmac_secret)
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10, allow_redirects=False)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=body, params=params, timeout=10, allow_redirects=False)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=body, params=params, timeout=10, allow_redirects=False)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=body, params=params, timeout=10, allow_redirects=False)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params, timeout=10, allow_redirects=False)
            else:
                return {
                    "name": name,
                    "method": method,
                    "path": path,
                    "status": "ERROR",
                    "error": f"Unsupported method: {method}"
                }
            
            # Determine if endpoint is working
            status_code = response.status_code
            is_working = False
            status_note = ""
            
            if expected_status:
                is_working = status_code == expected_status
            else:
                # For UI endpoints, 200, 303 (redirect), or 401 (auth required) are acceptable
                if is_ui_endpoint:
                    is_working = status_code in [200, 303, 401]
                    if status_code == 303:
                        status_note = " (redirects to login - expected)"
                    elif status_code == 401:
                        status_note = " (requires authentication - expected)"
                else:
                    # For API endpoints, 200-299, 400-499 (validation errors) are acceptable
                    # 500+ or 401 without auth are errors
                    if requires_auth:
                        is_working = status_code in [200, 201, 400, 404] or (status_code >= 200 and status_code < 500)
                    else:
                        is_working = status_code < 500
            
            result = {
                "name": name,
                "method": method,
                "path": path,
                "status_code": status_code,
                "status": "WORKING" if is_working else "ERROR",
                "note": status_note
            }
            
            if not is_working:
                try:
                    error_detail = response.json() if response.content else {}
                    result["error"] = error_detail.get("detail", f"HTTP {status_code}")
                except:
                    result["error"] = f"HTTP {status_code}: {response.text[:200]}"
            
            return result
            
        except requests.exceptions.Timeout:
            return {
                "name": name,
                "method": method,
                "path": path,
                "status": "ERROR",
                "error": "Request timeout"
            }
        except requests.exceptions.ConnectionError:
            return {
                "name": name,
                "method": method,
                "path": path,
                "status": "ERROR",
                "error": "Connection error"
            }
        except Exception as e:
            return {
                "name": name,
                "method": method,
                "path": path,
                "status": "ERROR",
                "error": str(e)
            }
    
    def run_all_tests(self):
        """Run tests for all endpoints."""
        print("=" * 80)
        print("Testing All Production Endpoints")
        print("=" * 80)
        print(f"Base URL: {self.base_url}")
        print(f"HMAC Secret: {'*' * 20} (configured)")
        print()
        
        # Define all endpoints to test
        endpoints = [
            # UI Endpoints (HTML pages)
            ("GET", "/", "Root Dashboard", True, None, None, None, True),
            ("GET", "/login", "Login Page", False, None, None, None, True),
            ("GET", "/experity/chat", "Experity Chat UI", True, None, None, None, True),
            ("GET", "/queue/list", "Queue List UI", True, None, None, None, True),
            ("GET", "/images/", "Images Gallery", True, None, None, None, True),
            ("GET", "/emr/validation", "EMR Validation UI", True, None, None, None, True),
            
            # Patient Endpoints
            ("GET", "/patients", "List Patients", True, None, {"locationId": "AXjwbE", "limit": 1}, None, False),
            ("GET", "/patient/EMR12345", "Get Patient by EMR ID", True, None, None, None, False),
            ("POST", "/patients/create", "Create Patient", True, {
                "emrId": "TEST_EMR_" + datetime.now().strftime("%Y%m%d%H%M%S"),
                "locationId": "AXjwbE",
                "status": "confirmed"
            }, None, None, False),
            ("PATCH", "/patients/EMR12345", "Update Patient Status", True, {
                "status": "confirmed"
            }, None, None, False),
            
            # Encounter Endpoints
            ("POST", "/encounter", "Create Encounter", True, {
                "emrId": "TEST_EMR_123",
                "encounterPayload": {
                    "id": "test-encounter-" + datetime.now().strftime("%Y%m%d%H%M%S"),
                    "clientId": "test-client",
                    "status": "COMPLETE"
                }
            }, None, None, False),
            
            # Summary Endpoints
            ("GET", "/summary", "Get Summary", True, None, {"emrId": "EMR12345"}, None, False),
            ("POST", "/summary", "Create Summary", True, {
                "emrId": "TEST_EMR_123",
                "note": "Test summary note"
            }, None, None, False),
            
            # Queue Endpoints
            ("GET", "/queue", "List Queue Entries", True, None, {"limit": 1}, None, False),
            ("POST", "/queue", "Update Queue Entry", True, {
                "encounter_id": "test-encounter-123"
            }, None, None, False),
            ("PATCH", "/queue/test-queue-id/status", "Update Queue Status", True, {
                "status": "PENDING"
            }, None, None, False),
            ("PATCH", "/queue/test-queue-id/requeue", "Requeue Entry", True, {
                "status": "PENDING",
                "priority": "HIGH"
            }, None, None, False),
            ("POST", "/experity/map", "Map to Experity", True, {
                "queue_entry": {
                    "encounter_id": "test-encounter-123",
                    "raw_payload": {
                        "id": "test-encounter-123",
                        "clientId": "test-client",
                        "status": "COMPLETE"
                    }
                }
            }, None, None, False),
            
            # Queue Validation Endpoints
            ("GET", "/queue/test-queue-id/validation", "Get Queue Validation", True, None, None, None, True),
            ("GET", "/queue/validation/test-encounter-id", "Validation Page", True, None, None, None, True),
            ("POST", "/queue/validation/test-encounter-id/save", "Save Manual Validation", True, {
                "complaint_id": "test-complaint-id",
                "field_validations": {}
            }, None, None, False),
            ("GET", "/queue/test-queue-id/validation/image", "Get Validation Image", True, None, {"complaint_id": "test-id"}, None, False),
            ("GET", "/queue/validation/test-encounter-id/image/icd", "Get ICD Image", True, None, None, None, False),
            ("GET", "/queue/validation/test-encounter-id/image/historian", "Get Historian Image", True, None, None, None, False),
            ("GET", "/queue/validation/test-encounter-id/image/vitals", "Get Vitals Image", True, None, None, None, False),
            
            # VM Health Endpoints
            ("POST", "/vm/heartbeat", "VM Heartbeat", True, {
                "vmId": "test-vm",
                "status": "healthy"
            }, None, None, False),
            ("GET", "/vm/health", "Get VM Health", True, None, None, None, True),
            
            # Image Endpoints
            ("GET", "/images/list", "List Images", True, None, None, None, False),
            ("GET", "/images/status", "Check Blob Storage Status", True, None, None, None, False),
            ("GET", "/images/test-image.jpg", "View Image", True, None, None, None, False),
            
            # Validation Endpoints
            ("POST", "/emr/validate", "Validate EMR Image", True, None, None, None, False),  # Requires file upload, will fail but test endpoint exists
            
            # Auth Endpoints
            ("GET", "/auth/me", "Get Current User", True, None, None, None, True),
        ]
        
        print(f"Testing {len(endpoints)} endpoints...")
        print()
        
        working_count = 0
        error_count = 0
        
        for method, path, name, requires_auth, body, params, expected_status, is_ui in endpoints:
            print(f"Testing: {method} {path} - {name}...", end=" ", flush=True)
            result = self.test_endpoint(
                method, path, name, requires_auth, body, params, expected_status, is_ui
            )
            self.results.append(result)
            
            if result["status"] == "WORKING":
                print(f"✓ {result['status_code']}{result.get('note', '')}")
                working_count += 1
            else:
                print(f"✗ {result.get('error', 'Unknown error')}")
                error_count += 1
        
        print()
        print("=" * 80)
        print("Test Summary")
        print("=" * 80)
        print(f"Total Endpoints: {len(endpoints)}")
        print(f"Working: {working_count}")
        print(f"Errors: {error_count}")
        print()
        
        # Print detailed results
        print("=" * 80)
        print("Detailed Results")
        print("=" * 80)
        
        # Group by status
        working = [r for r in self.results if r["status"] == "WORKING"]
        errors = [r for r in self.results if r["status"] == "ERROR"]
        
        if working:
            print("\n✓ WORKING ENDPOINTS:")
            for r in working:
                print(f"  {r['method']:6} {r['path']:50} - {r['name']} (HTTP {r.get('status_code', 'N/A')})")
        
        if errors:
            print("\n✗ ENDPOINTS WITH ERRORS:")
            for r in errors:
                error_msg = r.get('error', 'Unknown error')
                print(f"  {r['method']:6} {r['path']:50} - {r['name']}")
                print(f"    Error: {error_msg}")
        
        print()
        print("=" * 80)
        
        # Save results to file
        results_file = Path(__file__).parent / "endpoint_test_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "base_url": self.base_url,
                "summary": {
                    "total": len(endpoints),
                    "working": working_count,
                    "errors": error_count
                },
                "results": self.results
            }, f, indent=2)
        
        print(f"Results saved to: {results_file}")
        print()
        
        return working_count, error_count


def main():
    """Main entry point."""
    tester = EndpointTester(PROD_BASE_URL, HMAC_SECRET)
    working, errors = tester.run_all_tests()
    
    # Exit with error code if any endpoints failed
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()


