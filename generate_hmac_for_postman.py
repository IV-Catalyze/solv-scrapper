#!/usr/bin/env python3
"""
Generate HMAC signature for Postman testing.

Usage:
    python3 generate_hmac_for_postman.py

Set your HMAC_SECRET in the script or as an environment variable.
"""

import os
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Get HMAC secret from environment - prioritize staging for testing
# Staging secret: 3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM
HMAC_SECRET = os.getenv('INTELLIVISIT_STAGING_HMAC_SECRET') or os.getenv('INTELLIVISIT_PRODUCTION_HMAC_SECRET')

if not HMAC_SECRET:
    print("⚠️  HMAC_SECRET not found. Please set INTELLIVISIT_STAGING_HMAC_SECRET or INTELLIVISIT_PRODUCTION_HMAC_SECRET")
    print("   Using staging secret for testing...")
    # Default to staging secret for testing
    HMAC_SECRET = '3SaxUjALPb0Ko8Lw-_eUFvNBPjlZWpGVGqJVS7e1BbM'
    print(f"   Using staging secret: {HMAC_SECRET[:20]}...")

# Request configuration
METHOD = "POST"
PATH = "/experity/map"

# Sample request body - modify as needed
BODY = {
    "queue_entry": {
        "queue_id": "a1b2c3d4-e5f6-4789-a012-345678901234",
        "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
        "raw_payload": {
            "id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
            "encounter_id": "e170d6fc-ae47-4ecd-b648-69f074505c4d",
            "client_id": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
            "trauma_type": "BURN",
            "chief_complaints": [
                {
                    "id": "09b5349d-d7c2-4506-9705-b5cc12947b6b",
                    "description": "Chemical burn on head",
                    "type": "trauma",
                    "part": "head",
                    "bodyParts": ["head", "forehead"]
                }
            ],
            "status": "COMPLETE",
            "created_by": "provider@example.com",
            "started_at": "2025-11-12T22:19:01.432Z",
            "created_at": "2025-11-12T22:19:01.432Z",
            "updated_at": "2025-11-12T22:19:01.432Z"
        }
    }
}


def generate_hmac_signature(method: str, path: str, body: dict, secret: str) -> tuple:
    """Generate HMAC signature for a request."""
    # Convert body to compact JSON (no spaces)
    body_json = json.dumps(body, separators=(',', ':'))
    
    # Generate timestamp (ISO 8601 UTC)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Hash the body
    body_bytes = body_json.encode('utf-8')
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    
    # Create canonical string
    canonical = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    
    # Generate HMAC-SHA256
    signature_bytes = hmac.new(
        secret.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # Base64 encode
    signature = base64.b64encode(signature_bytes).decode('utf-8')
    
    return signature, timestamp, canonical, body_json


def main():
    """Generate and display HMAC signature for Postman."""
    print("=" * 70)
    print("HMAC SIGNATURE GENERATOR FOR POSTMAN")
    print("=" * 70)
    print()
    
    # Generate signature
    signature, timestamp, canonical, body_json = generate_hmac_signature(
        METHOD, PATH, BODY, HMAC_SECRET
    )
    
    # Display results
    print("📋 REQUEST DETAILS:")
    print(f"   Method: {METHOD}")
    print(f"   Path: {PATH}")
    print(f"   URL: https://app-97926.on-aptible.com{PATH}")
    
    # Show which secret is being used
    if HMAC_SECRET.startswith('3SaxUjALPb0Ko8Lw'):
        print(f"   HMAC Secret: STAGING (starts with 3SaxUjALPb0Ko8Lw...)")
    elif HMAC_SECRET.startswith('PsGktLSZFQ0U3jh'):
        print(f"   HMAC Secret: PRODUCTION (starts with PsGktLSZFQ0U3jh...)")
    else:
        print(f"   HMAC Secret: CUSTOM (starts with {HMAC_SECRET[:20]}...)")
    print()
    
    print("🔐 HEADERS TO ADD IN POSTMAN:")
    print("-" * 70)
    print(f"X-Timestamp: {timestamp}")
    print(f"X-Signature: {signature}")
    print("-" * 70)
    print()
    
    print("📦 REQUEST BODY (copy this to Postman Body tab, raw JSON):")
    print("-" * 70)
    print(json.dumps(BODY, indent=2))
    print("-" * 70)
    print()
    
    print("🔍 DEBUG INFORMATION:")
    print(f"   Body JSON (compact): {body_json[:100]}...")
    print(f"   Body Hash: {hashlib.sha256(body_json.encode('utf-8')).hexdigest()}")
    print(f"   Canonical String:")
    print(f"     {canonical}")
    print()
    
    print("=" * 70)
    print("✅ READY FOR POSTMAN")
    print("=" * 70)
    print()
    print("INSTRUCTIONS:")
    print("1. Create POST request to: https://app-97926.on-aptible.com/experity/map")
    print("2. Add headers: X-Timestamp and X-Signature (values above)")
    print("3. Set Content-Type: application/json")
    print("4. Paste the request body above in Body tab (raw JSON)")
    print("5. Send request")
    print()
    print("⚠️  IMPORTANT: Regenerate signature for each request (timestamp changes)")
    print()


if __name__ == "__main__":
    main()

