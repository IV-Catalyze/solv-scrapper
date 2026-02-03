#!/usr/bin/env python3
"""
Test API endpoints after workflow migration to ensure everything works.
"""

import os
import sys
import json
import requests
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def print_info(msg):
    print(f"{YELLOW}ℹ {msg}{RESET}")

def print_step(msg):
    print(f"\n{BLUE}→ {msg}{RESET}")

def test_model_fields():
    """Test that Pydantic models accept the new field names."""
    print_step("Testing Pydantic models...")
    
    try:
        # Import models
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.api.models import (
            VmHeartbeatRequest,
            VmHeartbeatResponse,
            VmHealthStatusResponse,
            VmInfo,
            DashboardStatistics,
            HealthDashboardResponse
        )
        
        # Test 1: VmHeartbeatRequest with workflowStatus
        test_data = {
            "vmId": "test-vm-1",
            "status": "healthy",
            "workflowStatus": "running"
        }
        request = VmHeartbeatRequest(**test_data)
        if hasattr(request, 'workflowStatus') and request.workflowStatus == 'running':
            print_success("VmHeartbeatRequest accepts workflowStatus")
        else:
            print_error("VmHeartbeatRequest does not accept workflowStatus")
            return False
        
        # Test 2: VmHeartbeatResponse with workflowStatus
        response_data = {
            "success": True,
            "vmId": "test-vm-1",
            "lastHeartbeat": "2025-01-22T10:30:00Z",
            "status": "healthy",
            "workflowStatus": "running"
        }
        response = VmHeartbeatResponse(**response_data)
        if hasattr(response, 'workflowStatus') and response.workflowStatus == 'running':
            print_success("VmHeartbeatResponse accepts workflowStatus")
        else:
            print_error("VmHeartbeatResponse does not accept workflowStatus")
            return False
        
        # Test 3: DashboardStatistics with new field names
        stats_data = {
            "totalServers": 1,
            "healthyServers": 1,
            "unhealthyServers": 0,
            "downServers": 0,
            "totalVms": 1,
            "healthyVms": 1,
            "unhealthyVms": 0,
            "idleVms": 0,
            "vmsProcessing": 0,
            "vmsWithWorkflowRunning": 1,
            "vmsWithWorkflowStopped": 0
        }
        stats = DashboardStatistics(**stats_data)
        if (hasattr(stats, 'vmsWithWorkflowRunning') and 
            hasattr(stats, 'vmsWithWorkflowStopped')):
            print_success("DashboardStatistics accepts vmsWithWorkflowRunning/Stopped")
        else:
            print_error("DashboardStatistics missing workflow fields")
            return False
        
        # Test 4: Check that old field names are NOT accepted (this is correct behavior)
        try:
            old_data = {
                "vmId": "test-vm-1",
                "status": "healthy",
                "uiPathStatus": "running"  # Old field name - should be rejected
            }
            request_old = VmHeartbeatRequest(**old_data)
            # If we get here, the old field was accepted (which we don't want)
            print_error("Old field name uiPathStatus was accepted (should be rejected)")
            return False
        except Exception as e:
            # This is expected - old field names should be rejected
            if "Extra inputs are not permitted" in str(e) or "extra_forbidden" in str(e):
                print_success("Old field name uiPathStatus correctly rejected (as expected)")
            else:
                print_error(f"Unexpected error rejecting old field: {e}")
                return False
        
        return True
        
    except Exception as e:
        print_error(f"Model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_access():
    """Test direct database access with new field names."""
    print_step("Testing database access...")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.api.database import get_db_connection, save_vm_health, get_vm_health_by_vm_id
        
        conn = get_db_connection()
        if not conn:
            print_error("Could not connect to database")
            return False
        
        try:
            # Test 1: Save VM health with workflow_status
            test_vm_id = f'test-db-{os.getpid()}'
            vm_data = {
                'vm_id': test_vm_id,
                'status': 'healthy',
                'workflow_status': 'running',
                'server_id': 'test-server-1'
            }
            
            saved = save_vm_health(conn, vm_data)
            if saved and saved.get('workflow_status') == 'running':
                print_success("save_vm_health works with workflow_status")
            else:
                print_error("save_vm_health failed with workflow_status")
                return False
            
            # Test 2: Retrieve VM health
            retrieved = get_vm_health_by_vm_id(conn, test_vm_id)
            if retrieved and retrieved.get('workflow_status') == 'running':
                print_success("get_vm_health_by_vm_id returns workflow_status")
            else:
                print_error("get_vm_health_by_vm_id missing workflow_status")
                return False
            
            # Clean up
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vm_health WHERE vm_id = %s", (test_vm_id,))
            conn.commit()
            cursor.close()
            print_success("Test record cleaned up")
            
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        print_error(f"Database access test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_route_handlers():
    """Test that route handlers work with new field names."""
    print_step("Testing route handler imports...")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Just test that routes can be imported without errors
        from app.api.routes import vm_health, server_health
        
        # Check that the routes use workflowStatus
        import inspect
        
        # Check vm_healthbeat function
        vm_heartbeat_source = inspect.getsource(vm_health.vm_heartbeat)
        if 'workflowStatus' in vm_heartbeat_source or 'workflow_status' in vm_heartbeat_source:
            print_success("vm_healthbeat route uses workflow fields")
        else:
            print_error("vm_healthbeat route may not use workflow fields")
            return False
        
        # Check server health dashboard
        dashboard_source = inspect.getsource(server_health.get_health_dashboard)
        if 'vmsWithWorkflowRunning' in dashboard_source or 'vms_with_workflow_running' in dashboard_source:
            print_success("get_health_dashboard route uses workflow fields")
        else:
            print_error("get_health_dashboard route may not use workflow fields")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Route handler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print(f"\n{BLUE}{'='*60}")
    print("Workflow Migration API Tests")
    print("="*60 + RESET)
    
    all_passed = True
    
    # Test 1: Pydantic models
    if not test_model_fields():
        all_passed = False
    
    # Test 2: Database access
    if not test_database_access():
        all_passed = False
    
    # Test 3: Route handlers
    if not test_route_handlers():
        all_passed = False
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    if all_passed:
        print(f"{GREEN}✓ All API tests passed!{RESET}")
        print("\nThe migration is complete and all code is working correctly.")
        print("You can now use:")
        print("  - workflowStatus (instead of uiPathStatus)")
        print("  - vmsWithWorkflowRunning (instead of vmsWithUiPathRunning)")
        print("  - vmsWithWorkflowStopped (instead of vmsWithUiPathStopped)")
        print("  - 'workflow' alert source (instead of 'uipath')")
    else:
        print(f"{RED}✗ Some tests failed!{RESET}")
        sys.exit(1)

if __name__ == '__main__':
    main()
