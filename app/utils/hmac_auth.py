#!/usr/bin/env python3
"""
HMAC Signature Authentication Module.

Provides HMAC-SHA256 signature verification for API requests.
Each request must include X-Timestamp and X-Signature headers.
The signature is computed over a canonical string containing:
METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH
"""

import hmac
import hashlib
import base64
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request

from app.config.intellivisit_clients import INTELLIVISIT_CLIENTS


def validate_timestamp(timestamp: str, window_seconds: int = 300) -> bool:
    """
    Validate that the timestamp is within the allowed window.
    
    Args:
        timestamp: ISO 8601 UTC timestamp string
        window_seconds: Allowed time difference in seconds (default: 5 minutes)
        
    Returns:
        True if timestamp is valid, False otherwise
    """
    try:
        # Handle both Z and +00:00 formats
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        
        req_time = datetime.fromisoformat(timestamp)
        if req_time.tzinfo is None:
            # Assume UTC if no timezone info
            req_time = req_time.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        time_diff = abs((now - req_time).total_seconds())
        
        return time_diff <= window_seconds
    except (ValueError, AttributeError, TypeError):
        return False


def extract_hmac_headers(request: Request) -> tuple:
    """
    Extract HMAC authentication headers from request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tuple of (timestamp, signature) or (None, None) if not present
    """
    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")
    return timestamp, signature


def canonicalize_request(
    method: str,
    path: str,
    timestamp: str,
    body: bytes
) -> str:
    """
    Create canonical string for HMAC signature.
    
    Format: METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH
    
    Args:
        method: HTTP method (e.g., "POST", "GET")
        path: Request path including query string
        timestamp: ISO 8601 UTC timestamp
        body: Request body as bytes
        
    Returns:
        Canonical string for signing
    """
    # Hash the body
    body_hash = hashlib.sha256(body).hexdigest()
    
    # Create canonical string
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
    return canonical


async def get_request_body(request: Request) -> bytes:
    """
    Get request body as bytes.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Request body as bytes
    """
    # Try to get body from request
    if hasattr(request, "_body"):
        return request._body or b""
    
    # For FastAPI, read the body
    try:
        body = await request.body()
        return body
    except Exception:
        return b""


def verify_hmac_signature(
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    signature: str,
    secret_key: str
) -> bool:
    """
    Verify HMAC signature against expected value.
    
    Args:
        method: HTTP method
        path: Request path with query string
        timestamp: ISO 8601 UTC timestamp
        body: Request body as bytes
        signature: Base64-encoded HMAC signature from header
        secret_key: Secret key for HMAC computation
        
    Returns:
        True if signature is valid
        
    Raises:
        HTTPException: If signature is invalid
    """
    # Create canonical string
    canonical = canonicalize_request(method, path, timestamp, body)
    
    # Compute expected signature
    expected = hmac.new(
        secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    expected_b64 = base64.b64encode(expected).decode('utf-8')
    
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_b64):
        raise HTTPException(
            status_code=401,
            detail="Invalid HMAC signature",
            headers={"WWW-Authenticate": "HMAC"}
        )
    
    return True


async def verify_hmac_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Verify HMAC request and return matching client configuration.
    
    This function:
    1. Extracts HMAC headers (X-Timestamp, X-Signature)
    2. Validates timestamp is within ±5 minutes
    3. Tries each configured HMAC secret until one matches
    4. Returns the client config for the matching secret
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client configuration dictionary if valid, None if no HMAC headers present
        
    Raises:
        HTTPException: If HMAC headers are present but invalid
    """
    # Extract headers
    timestamp, signature = extract_hmac_headers(request)
    
    # If no HMAC headers, return None (not an error - might use other auth)
    if not timestamp or not signature:
        return None
    
    # Validate timestamp
    if not validate_timestamp(timestamp):
        raise HTTPException(
            status_code=401,
            detail="Timestamp expired or invalid. Request must be within ±5 minutes of server time.",
            headers={"WWW-Authenticate": "HMAC"}
        )
    
    # Get request body
    body = await get_request_body(request)
    
    # Build path with query string
    path = str(request.url.path)
    if request.url.query:
        path += f"?{request.url.query}"
    
    # Try each client's secret key until we find a match
    for client_name, client_cfg in INTELLIVISIT_CLIENTS.items():
        secret_key = client_cfg.get("hmac_secret_key")
        if not secret_key:
            continue
        
        try:
            # Try to verify with this secret
            verify_hmac_signature(
                method=request.method,
                path=path,
                timestamp=timestamp,
                body=body,
                signature=signature,
                secret_key=secret_key
            )
            # If successful, return this client's config
            return client_cfg
        except HTTPException:
            # Wrong secret, try next one
            continue
    
    # No matching secret found
    raise HTTPException(
        status_code=401,
        detail="Invalid HMAC signature",
        headers={"WWW-Authenticate": "HMAC"}
    )

