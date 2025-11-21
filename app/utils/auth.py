#!/usr/bin/env python3
"""
Authentication module for HMAC signature authentication.

This module provides HMAC-based authentication:
- HMAC-SHA256 signature verification
- Request-level security with timestamp validation
- Environment-based secret management
"""

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

