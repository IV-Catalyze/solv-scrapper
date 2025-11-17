#!/usr/bin/env python3
"""
Authentication module for API access tokens.

This module provides JWT-based authentication following production best practices:
- Secure token generation with expiration
- Token validation middleware
- Support for API key-based authentication
- Environment-based secret management
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from passlib.context import CryptContext

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("API_SECRET_KEY"))
if not SECRET_KEY:
    # Generate a random secret if not set (for development only)
    import secrets
    SECRET_KEY = secrets.token_urlsafe(32)
    print("WARNING: JWT_SECRET_KEY not set. Using generated secret. Set JWT_SECRET_KEY in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours default

# API Key configuration (alternative authentication method)
API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY")  # Static API key for simple integrations

# Password hashing context (for future use if needed)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token security scheme
security = HTTPBearer()
# API Key security scheme
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


class TokenData:
    """Token payload structure."""
    def __init__(self, client_id: str, scopes: Optional[list] = None):
        self.client_id = client_id
        self.scopes = scopes or []


def create_access_token(
    client_id: str,
    expires_delta: Optional[timedelta] = None,
    scopes: Optional[list] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        client_id: Identifier for the client/service requesting access
        expires_delta: Custom expiration time (defaults to ACCESS_TOKEN_EXPIRE_MINUTES)
        scopes: Optional list of permission scopes
        
    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode: Dict[str, Any] = {
        "sub": client_id,  # Subject (client identifier)
        "exp": expire,  # Expiration time
        "iat": datetime.utcnow(),  # Issued at
        "type": "access_token"
    }
    
    if scopes:
        to_encode["scopes"] = scopes
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string to verify
        
    Returns:
        TokenData object with client_id and scopes
        
    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        client_id: str = payload.get("sub")
        if client_id is None:
            raise credentials_exception
        
        scopes = payload.get("scopes", [])
        token_data = TokenData(client_id=client_id, scopes=scopes)
        return token_data
    except JWTError:
        raise credentials_exception


def verify_api_key(api_key: Optional[str]) -> bool:
    """
    Verify API key authentication.
    
    Args:
        api_key: API key string from request header
        
    Returns:
        True if API key is valid, False otherwise
    """
    if not API_KEY:
        return False
    return api_key == API_KEY


async def get_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key: Optional[str] = Security(api_key_header)
) -> TokenData:
    """
    Dependency function to validate authentication for protected endpoints.
    
    Supports both JWT Bearer tokens and API key authentication.
    JWT tokens take precedence if both are provided.
    
    Args:
        credentials: HTTP Bearer token credentials
        api_key: API key from X-API-Key header
        
    Returns:
        TokenData object with client information
        
    Raises:
        HTTPException: If authentication fails
    """
    # Try JWT Bearer token first
    if credentials:
        try:
            token_data = verify_token(credentials.credentials)
            return token_data
        except HTTPException:
            # If JWT fails, fall through to API key check
            pass
    
    # Fall back to API key authentication
    if api_key:
        if verify_api_key(api_key):
            # Return a TokenData object for API key auth
            return TokenData(client_id="api_key_client", scopes=["read", "write"])
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide a Bearer token or API key.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_token_for_client(client_id: str, expires_hours: Optional[int] = None) -> Dict[str, Any]:
    """
    Helper function to create a token with metadata for API responses.
    
    Args:
        client_id: Client identifier
        expires_hours: Optional custom expiration in hours
        
    Returns:
        Dictionary with token and metadata
    """
    expires_delta = None
    if expires_hours:
        expires_delta = timedelta(hours=expires_hours)
    
    access_token = create_access_token(client_id=client_id, expires_delta=expires_delta)
    
    expire_time = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expire_time.isoformat(),
        "expires_in": int((expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).total_seconds()),
        "client_id": client_id
    }

