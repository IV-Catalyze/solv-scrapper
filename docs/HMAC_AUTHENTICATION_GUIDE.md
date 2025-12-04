# HMAC Authentication Guide for Intellivisit

## Overview

This guide explains how to authenticate API requests using HMAC-SHA256 signatures. All API endpoints require HMAC authentication via `X-Timestamp` and `X-Signature` headers.

**Base URL**: `https://app-97926.on-aptible.com`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [How HMAC Authentication Works](#how-hmac-authentication-works)
3. [Step-by-Step Implementation](#step-by-step-implementation)
4. [Code Examples](#code-examples)
5. [Testing Your Implementation](#testing-your-implementation)
6. [Troubleshooting](#troubleshooting)
7. [Security Best Practices](#security-best-practices)

---

## Quick Start

### Required Headers

Every API request must include:

- **`X-Timestamp`**: ISO 8601 UTC timestamp (e.g., `2025-11-21T13:49:04Z`)
- **`X-Signature`**: Base64-encoded HMAC-SHA256 signature
- **`Content-Type`**: `application/json` (for POST/PATCH requests)

### Secret Key

Your HMAC secret key will be provided separately via secure channel. **Never commit this key to version control or share it publicly.**

---

## How HMAC Authentication Works

### The Canonical String

The signature is computed over a canonical string with this format:

```
METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH
```

Where:
- **METHOD**: HTTP method in uppercase (e.g., `GET`, `POST`)
- **PATH**: Request path including query string (e.g., `/summary?emr_id=123`)
- **TIMESTAMP**: ISO 8601 UTC timestamp (e.g., `2025-11-21T13:49:04Z`)
- **BODY_HASH**: SHA256 hash of the request body in hexadecimal format (empty string for GET requests)

### Signature Generation Process

1. **Get current UTC timestamp** in ISO 8601 format
2. **Hash the request body** using SHA256 (empty string for GET requests)
3. **Create canonical string** with newline separators
4. **Compute HMAC-SHA256** using your secret key
5. **Base64 encode** the HMAC result
6. **Include headers** in your request

---

## Step-by-Step Implementation

### Step 1: Prepare Request Components

```python
method = "POST"
path = "/summary"  # Include query string if present
timestamp = "2025-11-21T13:49:04Z"  # Current UTC time
body = '{"emr_id":"EMR12345","note":"Patient summary"}'
```

### Step 2: Hash the Request Body

```python
import hashlib

body_str = body if body else ""
body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()
# Result: "a1b2c3d4e5f6..." (64 character hex string)
```

### Step 3: Create Canonical String

```python
canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
```

**Example canonical string:**
```
POST
/summary
2025-11-21T13:49:04Z
a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

### Step 4: Generate HMAC Signature

```python
import hmac
import base64

SECRET_KEY = "YOUR_SECRET_KEY_HERE"  # Provided separately

signature = hmac.new(
    SECRET_KEY.encode('utf-8'),
    canonical.encode('utf-8'),
    hashlib.sha256
).digest()

signature_b64 = base64.b64encode(signature).decode('utf-8')
```

### Step 5: Include Headers in Request

```python
headers = {
    "Content-Type": "application/json",
    "X-Timestamp": timestamp,
    "X-Signature": signature_b64
}
```

---

## Code Examples

### Python Example

```python
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone

# Configuration
SECRET_KEY = "YOUR_SECRET_KEY_HERE"  # Provided separately
API_BASE_URL = "https://app-97926.on-aptible.com"

def generate_hmac_signature(method, path, body, secret_key):
    """
    Generate HMAC signature for a request.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path with query string
        body: Request body as string (empty for GET)
        secret_key: HMAC secret key
    
    Returns:
        Tuple of (signature, timestamp)
    """
    # Get current UTC timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Hash the body
    body_str = body if body else ""
    body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()
    
    # Create canonical string
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
    # Generate HMAC signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # Base64 encode
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    return signature_b64, timestamp

def make_hmac_request(method, endpoint, body=None, params=None):
    """
    Make an HMAC-authenticated request.
    
    Args:
        method: HTTP method
        endpoint: API endpoint path
        body: Request body as dictionary
        params: Query parameters as dictionary
    
    Returns:
        requests.Response object
    """
    # Build path with query string
    path = endpoint
    if params:
        from urllib.parse import urlencode
        query_string = urlencode(params, doseq=True)
        path = f"{endpoint}?{query_string}"
    
    # Prepare body
    body_str = json.dumps(body) if body else ""
    
    # Generate signature
    signature, timestamp = generate_hmac_signature(
        method, path, body_str, SECRET_KEY
    )
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Signature": signature
    }
    
    # Make request
    url = f"{API_BASE_URL}{endpoint}"
    if method.upper() == "GET":
        return requests.get(url, headers=headers, params=params)
    elif method.upper() == "POST":
        return requests.post(url, headers=headers, json=body)
    elif method.upper() == "PATCH":
        return requests.patch(url, headers=headers, json=body)
    else:
        raise ValueError(f"Unsupported method: {method}")

# Example: POST /summary
response = make_hmac_request(
    "POST",
    "/summary",
    body={
        "emr_id": "EMR12345",
        "note": "Patient is a 69 year old male..."
    }
)
print(response.status_code)
print(response.json())

# Example: GET /summary
response = make_hmac_request(
    "GET",
    "/summary",
    params={"emr_id": "EMR12345"}
)
print(response.status_code)
print(response.json())
```

### JavaScript/Node.js Example

```javascript
const crypto = require('crypto');
const https = require('https');

const SECRET_KEY = 'YOUR_SECRET_KEY_HERE'; // Provided separately
const API_BASE_URL = 'https://app-97926.on-aptible.com';

function generateHmacSignature(method, path, body, secretKey) {
    // Get current UTC timestamp
    const timestamp = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    
    // Hash the body
    const bodyStr = body || '';
    const bodyHash = crypto.createHash('sha256')
        .update(bodyStr)
        .digest('hex');
    
    // Create canonical string
    const canonical = `${method.toUpperCase()}\n${path}\n${timestamp}\n${bodyHash}`;
    
    // Generate HMAC signature
    const signature = crypto
        .createHmac('sha256', secretKey)
        .update(canonical)
        .digest('base64');
    
    return { signature, timestamp };
}

function makeHmacRequest(method, endpoint, body = null, params = null) {
    return new Promise((resolve, reject) => {
        // Build path with query string
        let path = endpoint;
        if (params) {
            const queryString = new URLSearchParams(params).toString();
            path = `${endpoint}?${queryString}`;
        }
        
        // Prepare body
        const bodyStr = body ? JSON.stringify(body) : '';
        
        // Generate signature
        const { signature, timestamp } = generateHmacSignature(
            method, path, bodyStr, SECRET_KEY
        );
        
        // Prepare request options
        const url = new URL(`${API_BASE_URL}${endpoint}`);
        if (params) {
            Object.keys(params).forEach(key => {
                url.searchParams.append(key, params[key]);
            });
        }
        
        const options = {
            hostname: url.hostname,
            path: url.pathname + url.search,
            method: method.toUpperCase(),
            headers: {
                'Content-Type': 'application/json',
                'X-Timestamp': timestamp,
                'X-Signature': signature
            }
        };
        
        const req = https.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                resolve({
                    statusCode: res.statusCode,
                    body: JSON.parse(data || '{}')
                });
            });
        });
        
        req.on('error', reject);
        
        if (body) {
            req.write(bodyStr);
        }
        
        req.end();
    });
}

// Example: POST /summary
makeHmacRequest('POST', '/summary', {
    emr_id: 'EMR12345',
    note: 'Patient is a 69 year old male...'
}).then(response => {
    console.log('Status:', response.statusCode);
    console.log('Body:', response.body);
});

// Example: GET /summary
makeHmacRequest('GET', '/summary', null, {
    emr_id: 'EMR12345'
}).then(response => {
    console.log('Status:', response.statusCode);
    console.log('Body:', response.body);
});
```

### cURL Example

```bash
#!/bin/bash

# Configuration
SECRET_KEY="YOUR_SECRET_KEY_HERE"
API_URL="https://app-97926.on-aptible.com/summary"

# Request data
METHOD="POST"
PATH="/summary"
BODY='{"emr_id":"EMR12345","note":"Patient summary"}'

# Generate timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Hash body
BODY_HASH=$(echo -n "$BODY" | sha256sum | cut -d' ' -f1)

# Create canonical string
CANONICAL="${METHOD}
${PATH}
${TIMESTAMP}
${BODY_HASH}"

# Generate HMAC signature
SIGNATURE=$(echo -n "$CANONICAL" | openssl dgst -sha256 -hmac "$SECRET_KEY" -binary | base64)

# Make request
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

---

## Testing Your Implementation

### Test Case 1: POST /summary

**Request:**
```json
POST /summary
{
  "emr_id": "test-emr-123",
  "note": "Test summary note"
}
```

**Expected Response:** `201 Created`

### Test Case 2: GET /summary

**Request:**
```
GET /summary?emr_id=test-emr-123
```

**Expected Response:** `200 OK` with summary data

### Test Case 3: Invalid Signature

**Request:** Same as above but with wrong signature

**Expected Response:** `401 Unauthorized` with message "Invalid HMAC signature"

### Test Case 4: Expired Timestamp

**Request:** Same as above but with timestamp from 10 minutes ago

**Expected Response:** `401 Unauthorized` with message "Timestamp expired or invalid"

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: `401 Unauthorized - Invalid HMAC signature`

**Possible causes:**
- Secret key mismatch
- Canonical string format incorrect
- Body hash doesn't match

**Debug steps:**
1. Verify secret key is correct
2. Print the canonical string and verify format:
   ```
   METHOD\nPATH\nTIMESTAMP\nBODY_HASH
   ```
3. Ensure body is hashed exactly as sent (no extra whitespace)
4. Verify Base64 encoding is correct

**Example debug code:**
```python
# Add this to your code for debugging
print("Canonical string:")
print(repr(canonical))  # Shows \n characters
print("\nSignature:", signature_b64)
print("Timestamp:", timestamp)
```

#### Issue 2: `401 Unauthorized - Timestamp expired or invalid`

**Possible causes:**
- Clock skew between client and server
- Timestamp format incorrect
- Timestamp too old (>5 minutes)

**Solutions:**
1. Ensure system clock is synchronized (use NTP)
2. Verify timestamp format: `YYYY-MM-DDTHH:MM:SSZ`
3. Generate timestamp just before making request

#### Issue 3: `400 Bad Request - Missing required fields`

**Possible causes:**
- Request body missing required fields
- Field names incorrect

**Solutions:**
1. Check endpoint documentation for required fields
2. Verify JSON structure matches expected schema

#### Issue 4: Signature works for GET but not POST

**Possible causes:**
- Body not included in hash calculation
- Body formatting differs (whitespace, ordering)

**Solutions:**
1. Ensure body is hashed exactly as sent
2. Use consistent JSON serialization (no extra spaces)
3. Verify body is included in canonical string

---

## Security Best Practices

### 1. Secret Key Management

✅ **DO:**
- Store secret key in environment variables
- Use secure secret management systems (AWS Secrets Manager, HashiCorp Vault)
- Rotate keys periodically
- Use different keys for different environments

❌ **DON'T:**
- Commit secret keys to version control
- Share keys in plain text emails
- Hardcode keys in source code
- Use production keys in development

### 2. Request Security

✅ **DO:**
- Use HTTPS for all requests
- Validate server certificates
- Implement request retry logic with exponential backoff
- Log requests without exposing sensitive data

❌ **DON'T:**
- Send requests over HTTP
- Include secret keys in request logs
- Reuse timestamps across requests
- Ignore certificate validation errors

### 3. Error Handling

✅ **DO:**
- Handle 401 errors gracefully
- Implement automatic retry for transient errors
- Log errors for debugging (without sensitive data)
- Alert on authentication failures

❌ **DON'T:**
- Expose secret keys in error messages
- Retry indefinitely on 401 errors
- Log full request bodies with sensitive data

---

## Canonical String Examples

### Example 1: GET /summary with Query

**Request:**
- Method: `GET`
- Path: `/summary?emr_id=EMR12345`
- Timestamp: `2025-11-21T14:30:15Z`
- Body: (empty)

**Body Hash (empty string):**
```
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**Canonical String:**
```
GET
/summary?emr_id=EMR12345
2025-11-21T14:30:15Z
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

### Example 2: POST /encounter

**Request:**
- Method: `POST`
- Path: `/encounter`
- Timestamp: `2025-11-21T15:45:30Z`
- Body: `{"id":"uuid","patientId":"uuid","encounterId":"uuid","chiefComplaints":[...]}`

**Canonical String:**
```
POST
/encounter
2025-11-21T15:45:30Z
[64-character SHA256 hex hash of body]
```

---

## Important Notes

### Timestamp Requirements

- **Format**: ISO 8601 UTC (e.g., `2025-11-21T13:49:04Z`)
- **Validity Window**: ±5 minutes from server time
- **Generation**: Generate timestamp just before making request
- **Timezone**: Always use UTC

### Body Hashing

- **Empty Body**: For GET requests, use empty string `""`
- **Exact Match**: Body must be hashed exactly as sent (no extra spaces)
- **JSON Formatting**: Use consistent JSON serialization
- **Encoding**: Always use UTF-8 encoding

### Path Formatting

- **Include Query String**: Query parameters must be part of the path
- **No Trailing Slash**: Don't add trailing slashes unless required
- **URL Encoding**: Use proper URL encoding for query parameters

### Signature Format

- **Algorithm**: HMAC-SHA256
- **Encoding**: Base64
- **Case Sensitivity**: Signature comparison is case-sensitive


## Appendix: Complete Python Implementation

```python
"""
Complete HMAC authentication implementation.
"""

import hmac
import hashlib
import base64
import json
import os
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

class SolvHMACClient:
    """Client for making HMAC-authenticated requests to Solv Health API."""
    
    def __init__(self, secret_key: str, base_url: str = "https://app-97926.on-aptible.com"):
        """
        Initialize HMAC client.
        
        Args:
            secret_key: HMAC secret key (provided separately)
            base_url: API base URL
        """
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
    
    def _generate_signature(self, method: str, path: str, body: str) -> tuple[str, str]:
        """
        Generate HMAC signature for a request.
        
        Returns:
            Tuple of (signature, timestamp)
        """
        # Get current UTC timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Hash the body
        body_str = body if body else ""
        body_hash = hashlib.sha256(body_str.encode('utf-8')).hexdigest()
        
        # Create canonical string
        canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
        
        # Generate HMAC signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Base64 encode
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return signature_b64, timestamp
    
    def request(
        self,
        method: str,
        endpoint: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """
        Make an HMAC-authenticated request.
        
        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint path
            body: Request body as dictionary
            params: Query parameters as dictionary
        
        Returns:
            requests.Response object
        """
        # Build path with query string
        path = endpoint
        if params:
            query_string = urlencode(params, doseq=True)
            path = f"{endpoint}?{query_string}"
        
        # Prepare body
        body_str = json.dumps(body) if body else ""
        
        # Generate signature
        signature, timestamp = self._generate_signature(method, path, body_str)
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }
        
        # Make request
        url = f"{self.base_url}{endpoint}"
        if method.upper() == "GET":
            return requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            return requests.post(url, headers=headers, json=body, timeout=30)
        elif method.upper() == "PATCH":
            return requests.patch(url, headers=headers, json=body, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")

# Usage example
if __name__ == "__main__":
    # Get secret key from environment variable
    SECRET_KEY = os.getenv("SOLV_HMAC_SECRET", "YOUR_SECRET_KEY_HERE")
    
    # Initialize client
    client = SolvHMACClient(SECRET_KEY)
    
    # Example: POST /summary
    response = client.request(
        "POST",
        "/summary",
        body={
            "emr_id": "EMR12345",
            "note": "Patient summary text"
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Example: GET /summary
    response = client.request(
        "GET",
        "/summary",
        params={"emr_id": "EMR12345"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
```

---

**Document Version**: 1.0  
**Last Updated**: November 2025  

