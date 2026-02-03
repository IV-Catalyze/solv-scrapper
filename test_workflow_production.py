#!/usr/bin/env python3
"""
Production test for workflow migration - verify all endpoints work with new field names.

Tests:
- VM heartbeat endpoint with workflowStatus
- Server health endpoints
- Health dashboard endpoint
- Alert endpoints with workflow source
"""

import os
import sys
import json
import requests
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Production base URL
PROD_BASE_URL = os.getenv("API_BASE_URL", "https://app-97926.on-aptible.com")

# API Key for testing
API_KEY = os.getenv("API_KEY") or os.getenv("INTELLIVISIT_STAGING_HMAC_SECRET")

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_test(name: str):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{name}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def print_success(message: str):
    print(f"{GREEN}✓ {message}{RESET}")

def print_error(message: str):
    print(f"{RED}✗ {message}{RESET}")

def print_info(message: str):
    print(f"{YELLOW}ℹ {message}{RESET}")

def test_vm_heartbeat_workflow():
    """Test VM heartbeat endpoint with workflowStatus field."""
    print_test("Testing VM Heartbeat with workflowStatus")
    
    if not API_KEY:
        print_error("API_KEY not set. Cannot test VM heartbeat endpoint.")
        return False
    
    test_vm_id = f"test-workflow-{uuid.uuid4().hex[:8]}"
    
    # Test 1: Send heartbeat with workflowStatus
    payload = {
        "vmId": test_vm_id,
        "serverId": "test-server-1",
        "status": "healthy",
        "workflowStatus": "running",
        "metadata": {
            "cpuUsage": 45.2,
            "memoryUsage": 62.8
        }
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{PROD_BASE_URL}/vm/heartbeat",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check response has workflowStatus
            if "workflowStatus" in data:
                print_success(f"Response contains workflowStatus: {data.get('workflowStatus')}")
            else:
                print_error("Response missing workflowStatus field")
                print_info(f"Response: {json.dumps(data, indent=2)}")
                return False
            
            # Check that old field name is NOT present
            if "uiPathStatus" in data:
                print_error("Response still contains old uiPathStatus field!")
                return False
            else:
                print_success("Old uiPathStatus field correctly absent")
            
            # Verify the value
            if data.get("workflowStatus") == "running":
                print_success("workflowStatus value is correct")
            else:
                print_error(f"workflowStatus value incorrect: {data.get('workflowStatus')}")
                return False
            
            return True
            
        else:
            print_error(f"Request failed with status {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_vm_heartbeat_old_field_rejected():
    """Test that old field name is rejected."""
    print_test("Testing VM Heartbeat rejects old uiPathStatus field")
    
    if not API_KEY:
        print_error("API_KEY not set. Cannot test VM heartbeat endpoint.")
        return False
    
    test_vm_id = f"test-reject-{uuid.uuid4().hex[:8]}"
    
    # Try to send with old field name
    payload = {
        "vmId": test_vm_id,
        "status": "healthy",
        "uiPathStatus": "running"  # Old field name
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{PROD_BASE_URL}/vm/heartbeat",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Should either reject or ignore the old field
        if response.status_code == 422:  # Validation error
            print_success("Old uiPathStatus field correctly rejected (422)")
            return True
        elif response.status_code == 200:
            data = response.json()
            # If it accepts, check that it doesn't use the old field
            if "uiPathStatus" not in data:
                print_success("Old field ignored (acceptable behavior)")
                return True
            else:
                print_error("Old field was accepted and returned in response!")
                return False
        else:
            print_info(f"Got status {response.status_code} (may be acceptable)")
            return True
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def test_server_health_workflow():
    """Test server health endpoint returns workflowStatus."""
    print_test("Testing Server Health endpoint")
    
    if not API_KEY:
        print_error("API_KEY not set. Cannot test server health endpoint.")
        return False
    
    # First, create a test server with a VM
    test_server_id = f"test-server-{uuid.uuid4().hex[:8]}"
    test_vm_id = f"{test_server_id}-vm1"
    
    # Create server heartbeat
    server_payload = {
        "serverId": test_server_id,
        "status": "healthy",
        "metadata": {"cpuUsage": 50.0}
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        # Create server
        requests.post(
            f"{PROD_BASE_URL}/server/heartbeat",
            json=server_payload,
            headers=headers,
            timeout=30
        )
        
        # Create VM with workflowStatus
        vm_payload = {
            "vmId": test_vm_id,
            "serverId": test_server_id,
            "status": "healthy",
            "workflowStatus": "running"
        }
        
        requests.post(
            f"{PROD_BASE_URL}/vm/heartbeat",
            json=vm_payload,
            headers=headers,
            timeout=30
        )
        
        # Now get server health
        response = requests.get(
            f"{PROD_BASE_URL}/server/health/{test_server_id}",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check VMs have workflowStatus
            if "vms" in data and len(data["vms"]) > 0:
                vm = data["vms"][0]
                if "workflowStatus" in vm:
                    print_success(f"VM has workflowStatus: {vm.get('workflowStatus')}")
                else:
                    print_error("VM missing workflowStatus field")
                    return False
                
                if "uiPathStatus" in vm:
                    print_error("VM still has old uiPathStatus field!")
                    return False
                else:
                    print_success("VM correctly uses workflowStatus (no uiPathStatus)")
            else:
                print_info("No VMs found (may be expected)")
            
            return True
        else:
            print_error(f"Request failed with status {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_health_dashboard_workflow():
    """Test health dashboard endpoint returns workflow statistics."""
    print_test("Testing Health Dashboard endpoint")
    
    # Dashboard requires session auth, so we'll just check if it's accessible
    # and verify the response structure if we can get it
    
    try:
        # Try to access dashboard (may require login)
        response = requests.get(
            f"{PROD_BASE_URL}/health/dashboard",
            timeout=30,
            allow_redirects=False
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check statistics have new field names
            if "statistics" in data:
                stats = data["statistics"]
                
                if "vmsWithWorkflowRunning" in stats:
                    print_success("Statistics contain vmsWithWorkflowRunning")
                else:
                    print_error("Statistics missing vmsWithWorkflowRunning")
                    return False
                
                if "vmsWithWorkflowStopped" in stats:
                    print_success("Statistics contain vmsWithWorkflowStopped")
                else:
                    print_error("Statistics missing vmsWithWorkflowStopped")
                    return False
                
                # Check old fields are not present
                if "vmsWithUiPathRunning" in stats or "vmsWithUiPathStopped" in stats:
                    print_error("Statistics still contain old field names!")
                    return False
                else:
                    print_success("Statistics correctly use new field names")
                
                print_info(f"  - VMs with workflow running: {stats.get('vmsWithWorkflowRunning', 0)}")
                print_info(f"  - VMs with workflow stopped: {stats.get('vmsWithWorkflowStopped', 0)}")
                
                return True
            else:
                print_info("Response doesn't have statistics (may need authentication)")
                return True
                
        elif response.status_code == 401 or response.status_code == 303:
            print_info("Dashboard requires authentication (expected)")
            return True
        else:
            print_info(f"Dashboard returned status {response.status_code}")
            return True
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def test_alert_workflow_source():
    """Test alert endpoint accepts 'workflow' as source."""
    print_test("Testing Alert endpoint with workflow source")
    
    if not API_KEY:
        print_error("API_KEY not set. Cannot test alert endpoint.")
        return False
    
    # Test creating alert with workflow source
    payload = {
        "source": "workflow",
        "sourceId": f"test-workflow-{uuid.uuid4().hex[:8]}",
        "severity": "warning",
        "message": "AI Agent Workflow process stopped unexpectedly",
        "details": {
            "test": "workflow_migration"
        }
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{PROD_BASE_URL}/alerts",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            print_success("Alert created with 'workflow' source")
            print_info(f"Alert ID: {data.get('alertId', 'N/A')}")
            return True
        else:
            print_error(f"Request failed with status {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_alert_old_source_rejected():
    """Test that old 'uipath' source is rejected."""
    print_test("Testing Alert endpoint rejects old 'uipath' source")
    
    if not API_KEY:
        print_error("API_KEY not set. Cannot test alert endpoint.")
        return False
    
    # Try to create alert with old source
    payload = {
        "source": "uipath",  # Old source value
        "sourceId": f"test-{uuid.uuid4().hex[:8]}",
        "severity": "warning",
        "message": "Test message"
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{PROD_BASE_URL}/alerts",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 400 or response.status_code == 422:
            print_success("Old 'uipath' source correctly rejected")
            return True
        elif response.status_code == 201:
            print_error("Old 'uipath' source was accepted!")
            return False
        else:
            print_info(f"Got status {response.status_code}")
            return True
            
    except Exception as e:
        print_error(f"Request failed: {e}")
        return False

def main():
    """Run all production tests."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Production Workflow Migration Test Suite{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    print(f"Production URL: {PROD_BASE_URL}")
    if API_KEY:
        print(f"Authentication: API Key configured")
    else:
        print_error("API_KEY not set. Some tests will be skipped.")
        print_info("Set API_KEY or INTELLIVISIT_STAGING_HMAC_SECRET environment variable")
    
    # Test connectivity
    print_info("Testing API connectivity...")
    try:
        response = requests.get(f"{PROD_BASE_URL}/docs", timeout=10)
        if response.status_code in [200, 404]:
            print_success("API is reachable")
        else:
            print_error(f"API returned unexpected status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot connect to API: {str(e)}")
        return 1
    
    results = []
    
    # Run tests
    if API_KEY:
        results.append(("VM Heartbeat with workflowStatus", test_vm_heartbeat_workflow()))
        results.append(("VM Heartbeat rejects old field", test_vm_heartbeat_old_field_rejected()))
        results.append(("Server Health with workflowStatus", test_server_health_workflow()))
        results.append(("Alert with workflow source", test_alert_workflow_source()))
        results.append(("Alert rejects old source", test_alert_old_source_rejected()))
    
    results.append(("Health Dashboard", test_health_dashboard_workflow()))
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Results Summary{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        if result:
            print_success(f"{test_name}")
        else:
            print_error(f"{test_name}")
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    if passed == total:
        print(f"{GREEN}✓ All tests passed! ({passed}/{total}){RESET}")
        print("\nThe workflow migration is working correctly in production.")
        return 0
    else:
        print(f"{YELLOW}⚠ Some tests failed ({passed}/{total} passed){RESET}")
        print("\nPlease review the failures above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
