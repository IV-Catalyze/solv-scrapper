#!/usr/bin/env python3
"""
Test alert resolution on production to verify resolution email notifications.

This script creates a test alert and then resolves it to verify that resolution
email notifications are working correctly.
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Production configuration
PROD_BASE_URL = "https://app-97926.on-aptible.com"
API_KEY = os.getenv("API_KEY", "")

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


def create_test_alert():
    """Create a test alert on production."""
    if not API_KEY:
        print_error("API_KEY not configured. Set API_KEY in .env file")
        return None
    
    url = f"{PROD_BASE_URL}/alerts"
    
    # Test alert data
    alert_data = {
        "source": "monitor",
        "sourceId": "test-resolution-email",
        "severity": "warning",
        "message": "Test alert for resolution email notification",
        "details": {
            "test": True,
            "purpose": "Resolution email notification testing",
            "timestamp": "2025-01-28"
        }
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    print_info(f"Creating alert...")
    
    try:
        response = requests.post(url, headers=headers, json=alert_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            alert_id = result.get('alertId')
            print_success(f"Alert created: {alert_id}")
            return alert_id
        else:
            print_error(f"Failed to create alert. Status: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error creating alert: {str(e)}")
        return None


def resolve_alert(alert_id: str):
    """Resolve an alert on production using API key authentication."""
    if not API_KEY:
        print_error("API_KEY not configured")
        return False
    
    url = f"{PROD_BASE_URL}/alerts/{alert_id}/resolve"
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    print_info(f"Resolving alert: {alert_id}")
    print_info("Using API key authentication...")
    
    try:
        response = requests.patch(url, headers=headers, timeout=30)
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print_success("Alert resolved successfully!")
            print_info(f"Alert ID: {result.get('alertId', 'N/A')}")
            print_success(f"Resolved At: {result.get('resolvedAt', 'N/A')}")
            print_success("✓ Resolution email should have been sent!")
            print_info("Check your email at kleyessa@catalyzelabs.com for the resolution email")
            return True
        else:
            print_error(f"Failed to resolve alert. Status: {response.status_code}")
            print_error(f"Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print_error(f"Error resolving alert: {str(e)}")
        return False


def resolve_alert_with_hmac(alert_id: str):
    """Resolve alert using HMAC authentication."""
    import hmac
    import hashlib
    import base64
    from datetime import datetime, timezone
    
    HMAC_SECRET = os.getenv("INTELLIVISIT_PRODUCTION_HMAC_SECRET", "")
    
    if not HMAC_SECRET:
        print_error("HMAC_SECRET not configured")
        return False
    
    url = f"{PROD_BASE_URL}/alerts/{alert_id}/resolve"
    path = f"/alerts/{alert_id}/resolve"
    
    # Generate HMAC headers
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body_bytes = b''
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"PATCH\n{path}\n{timestamp}\n{body_hash}"
    
    signature = hmac.new(
        HMAC_SECRET.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    headers = {
        "X-Timestamp": timestamp,
        "X-Signature": signature_b64,
        "Content-Type": "application/json"
    }
    
    print_info("Resolving with HMAC authentication...")
    
    try:
        response = requests.patch(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print_success("Alert resolved successfully with HMAC!")
            print_info(f"Alert ID: {result.get('alertId', 'N/A')}")
            print_success(f"Resolved At: {result.get('resolvedAt', 'N/A')}")
            print_success("✓ Resolution email should have been sent!")
            print_info("Check your email at kleyessa@catalyzelabs.com for the resolution email")
            return True
        else:
            print_error(f"Failed to resolve alert. Status: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Error resolving alert: {str(e)}")
        return False


def main():
    """Main test function."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Production Alert Resolution Email Notification Test{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    # Step 1: Create an alert
    print_test("Step 1: Create Test Alert")
    alert_id = create_test_alert()
    
    if not alert_id:
        print_error("Failed to create alert. Cannot proceed with resolution test.")
        return 1
    
    # Step 2: Resolve the alert
    print_test("Step 2: Resolve Alert")
    success = resolve_alert(alert_id)
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    if success:
        print_success("Test completed!")
        print_info("Check your email at kleyessa@catalyzelabs.com for the resolution email")
        print_info("The email should indicate that the alert has been resolved")
    else:
        print_error("Test failed!")
        print_info("Alert was created but resolution failed")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
