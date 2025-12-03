#!/usr/bin/env python3
"""
Authentication routes for session-based login/logout.
"""

import os
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pathlib import Path

from app.utils.user_auth import authenticate_user

# Initialize router
router = APIRouter()

# Templates directory
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Session secret key (should be in environment variable)
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "change-this-secret-key-in-production-minimum-32-characters")
SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400  # 24 hours in seconds

# Create serializer for session cookies
serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY)


def create_session_token(user_data: dict) -> str:
    """Create a signed session token from user data."""
    return serializer.dumps(user_data)


def verify_session_token(token: str) -> Optional[dict]:
    """Verify and decode a session token. Returns user data or None if invalid."""
    try:
        max_age = SESSION_MAX_AGE
        user_data = serializer.loads(token, max_age=max_age)
        return user_data
    except BadSignature:
        # Invalid signature - token was tampered with or wrong secret key
        return None
    except SignatureExpired:
        # Token expired - session is too old
        return None
    except Exception:
        # Any other error (malformed token, etc.)
        return None


async def get_current_user(request: Request) -> Optional[dict]:
    """
    Dependency to get current authenticated user from session.
    Returns None if not authenticated.
    """
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None
    
    user_data = verify_session_token(session_token)
    return user_data


async def require_auth(request: Request) -> dict:
    """
    Dependency that requires authentication.
    Raises HTTPException if not authenticated.
    """
    user = await get_current_user(request)
    if not user:
        # Redirect to login page using RedirectResponse
        # We can't use RedirectResponse directly in a dependency, so we raise HTTPException
        # FastAPI will handle the 303 redirect properly
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user


@router.get("/login", response_class=HTMLResponse, tags=["Authentication"])
async def login_page(request: Request):
    """Render the login page."""
    # Check if user is authenticated
    user = await get_current_user(request)
    
    # If valid session exists, redirect to dashboard
    if user:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return response
    
    # If session cookie exists but is invalid/expired, clear it
    # This prevents redirect loops with invalid cookies
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    response = templates.TemplateResponse("login.html", {"request": request})
    
    # Clear invalid/expired session cookie if it exists
    if session_token:
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            samesite="lax",
        )
    
    # Add cache-control headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.post("/login", tags=["Authentication"])
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """
    Handle login form submission.
    Creates session cookie on successful authentication.
    """
    # Authenticate user
    user = authenticate_user(username, password)
    
    if not user:
        # Return login page with error message
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password"
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    # Create session token
    session_token = create_session_token({
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
    })
    
    # Create response with redirect to dashboard
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # Set secure session cookie
    # In production, SESSION_SECURE should be "true" when using HTTPS
    # For Aptible/cloud deployments, detect HTTPS from environment or default to secure
    is_production = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
    use_https = os.getenv("SESSION_SECURE", "true" if is_production else "false").lower() == "true"
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=use_https,
        samesite="lax",
        path="/",
    )
    
    return response


@router.post("/logout", tags=["Authentication"])
async def logout(request: Request):
    """Handle logout. Clears session cookie."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
    )
    # Add cache-control headers to prevent browser caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/auth/me", tags=["Authentication"])
async def get_current_user_info(current_user: dict = Depends(require_auth)):
    """Get current authenticated user information."""
    return current_user

