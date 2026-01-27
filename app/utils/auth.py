#!/usr/bin/env python3
"""
Authentication module for HMAC signature authentication and API key authentication.

This module provides:
- HMAC-SHA256 signature verification
- API key authentication (simpler alternative for monitoring systems)
- Request-level security with timestamp validation
- Environment-based secret management
"""

import os
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Request, status

# Client configuration
try:
    from app.config.intellivisit_clients import get_client_config_by_id
except ImportError:  # pragma: no cover - optional during partial installs
    def get_client_config_by_id(_: Optional[str]) -> Optional[Dict[str, Any]]:
        return None


class TokenData:
    """Client authentication data structure."""

    def __init__(
        self,
        client_id: str,
        scopes: Optional[List[str]] = None,
        *,
        allowed_location_ids: Optional[List[str]] = None,
        environment: Optional[str] = None,
    ):
        self.client_id = client_id
        self.scopes = scopes or []
        self.allowed_location_ids = allowed_location_ids
        self.environment = environment


async def get_current_client(request: Request) -> TokenData:
    """
    Dependency function to validate HMAC authentication for protected endpoints.
    
    This is the ONLY authentication method - HMAC signature verification.
    Each request must include:
    - X-Timestamp: ISO 8601 UTC timestamp
    - X-Signature: Base64-encoded HMAC-SHA256 signature
    
    Args:
        request: FastAPI request object (injected by FastAPI)
        
    Returns:
        TokenData object with client information
        
    Raises:
        HTTPException: If HMAC authentication fails
    """
    from app.utils.hmac_auth import verify_hmac_request
    
    # Verify HMAC request
    client_cfg = await verify_hmac_request(request)
    
    if not client_cfg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="HMAC authentication required. Provide X-Timestamp and X-Signature headers.",
            headers={"WWW-Authenticate": "HMAC"},
        )

    # Return TokenData with client configuration
    return TokenData(
        client_id=client_cfg.get("client_id", "hmac_client"),  # type: ignore[arg-type]
        scopes=client_cfg.get("scopes", []),  # type: ignore[arg-type]
        allowed_location_ids=client_cfg.get("allowed_location_ids"),  # type: ignore[arg-type]
        environment=client_cfg.get("environment"),  # type: ignore[arg-type]
    )


async def verify_api_key_auth(
    request: Request,
    endpoint_name: str = "endpoint",
    env_key_name: Optional[str] = None
) -> TokenData:
    """
    Reusable API key authentication function for endpoints.
    
    This is simpler than HMAC for monitoring systems that need to quickly
    send requests without complex signature generation. Uses the same secret
    keys as HMAC authentication for consistency.
    
    Args:
        request: FastAPI request object
        endpoint_name: Name of the endpoint (for error messages)
        env_key_name: Optional environment variable name to check (e.g., "API_KEY")
                      If not provided, falls back to "API_KEY"
        
    Returns:
        TokenData object with client information
        
    Raises:
        HTTPException: If API key authentication fails
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"X-API-Key header required for {endpoint_name}",
            headers={"WWW-Authenticate": "API-Key"}
        )
    
    # Verify against configured HMAC secrets (reuse existing secrets)
    try:
        from app.config.intellivisit_clients import INTELLIVISIT_CLIENTS
        
        for client_name, client_cfg in INTELLIVISIT_CLIENTS.items():
            secret = client_cfg.get("hmac_secret_key")
            if secret and api_key == secret:
                # Return TokenData with client configuration
                return TokenData(
                    client_id=client_cfg.get("client_id", client_name),
                    scopes=client_cfg.get("scopes", []),
                    allowed_location_ids=client_cfg.get("allowed_location_ids"),
                    environment=client_cfg.get("environment"),
                )
    except ImportError:
        # Fallback: check environment variable if INTELLIVISIT_CLIENTS not available
        pass
    
    # Fallback: check environment variable
    env_key = env_key_name or "API_KEY"
    env_api_key = os.getenv(env_key) or os.getenv("API_KEY")
    if env_api_key and api_key == env_api_key:
        return TokenData(
            client_id="api_key_client",
            scopes=[],
            environment=os.getenv("ENVIRONMENT", "production")
        )
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "API-Key"}
    )

