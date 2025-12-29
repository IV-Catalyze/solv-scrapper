#!/usr/bin/env python3
"""
Utility functions for API operations.

This module contains pure utility functions that don't depend on database
or business logic, such as:
- Status normalization and parsing
- Datetime parsing
- Location ID resolution
- Client access control
"""

import os
from typing import Optional, Any, List, Dict
from datetime import datetime
from fastapi import HTTPException

# Import TokenData for type hints
try:
    from app.utils.auth import TokenData
except ImportError:
    TokenData = None  # type: ignore

# Try to import httpx for remote API calls
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


def normalize_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized or None
    return None


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.min
        # Handle trailing Z (Zulu time) which datetime.fromisoformat can't parse directly
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.min


DEFAULT_STATUSES = ["checked_in", "confirmed"]

# Active statuses shortcut - only checked_in and confirmed
ACTIVE_STATUSES = ["checked_in", "confirmed"]

# Status shortcuts that expand to multiple statuses
STATUS_SHORTCUTS = {
    "active": ACTIVE_STATUSES,
}


def expand_status_shortcuts(statuses: List[str]) -> List[str]:
    """Expand status shortcuts like 'active' to their constituent statuses."""
    expanded = []
    for status in statuses:
        normalized = status.strip().lower() if isinstance(status, str) else None
        if normalized and normalized in STATUS_SHORTCUTS:
            expanded.extend(STATUS_SHORTCUTS[normalized])
        elif normalized:
            expanded.append(normalized)
    return list(dict.fromkeys(expanded))  # Remove duplicates while preserving order


def ensure_client_location_access(
    location_id: Optional[str],
    current_client: Optional[TokenData],
) -> Optional[str]:
    """
    Ensure the authenticated client is permitted to access the requested location.

    Returns the effective location ID (may inject the client's sole allowed ID)
    or raises HTTPException when the access rules would be violated.
    """
    if not current_client or current_client.allowed_location_ids is None:
        return location_id

    allowed = current_client.allowed_location_ids
    if not allowed:
        raise HTTPException(status_code=403, detail="No locations are enabled for this client.")

    if location_id:
        if location_id not in allowed:
            raise HTTPException(status_code=403, detail="This client is not permitted to access the requested location.")
        return location_id

    if len(allowed) == 1:
        # Auto-select the only available location for convenience.
        return allowed[0]

    raise HTTPException(
        status_code=403,
        detail="locationId is required for this client. Provide a permitted location ID explicitly.",
    )


def resolve_location_id(location_id: Optional[str], *, required: bool = True) -> Optional[str]:
    """
    Normalize `locationId` from the query string with support for a default
    value defined via the DEFAULT_LOCATION_ID environment variable.
    """
    normalized = location_id.strip() if location_id else None
    if normalized:
        return normalized

    env_location_id = os.getenv("DEFAULT_LOCATION_ID", "").strip()
    if env_location_id:
        return env_location_id

    if required:
        raise HTTPException(
            status_code=400,
            detail=(
                "locationId query parameter is required. "
                "Provide ?locationId=<ID> or configure DEFAULT_LOCATION_ID."
            ),
        )

    return None


def use_remote_api_for_reads() -> bool:
    """
    Determine whether to read queue data from the remote production API
    instead of the local database.

    Controlled by USE_REMOTE_API_FOR_READS env var (default: false).
    """
    return os.getenv("USE_REMOTE_API_FOR_READS", "false").strip().lower() in {"1", "true", "yes", "on"}


def fetch_locations(cursor) -> List[Dict[str, Optional[str]]]:
    """
    Fetch locations from database.
    Merges entries with the same location_id (prefers the one with a name).
    Shows all locations (no restrictions).
    """
    cursor.execute(
        """
        SELECT DISTINCT
            location_id,
            location_name
        FROM (
            SELECT location_id, location_name FROM pending_patients WHERE location_id IS NOT NULL
            UNION
            SELECT location_id, location_name FROM patients WHERE location_id IS NOT NULL
        ) AS combined
        ORDER BY location_name NULLS LAST, location_id
        """
    )
    rows = cursor.fetchall()
    
    # Merge entries with the same location_id (prefer the one with a name)
    location_map: Dict[str, Optional[str]] = {}
    for row in rows:
        loc_id = row.get("location_id")
        if not loc_id:
            continue
        
        loc_name = row.get("location_name")
        
        # If we haven't seen this location_id, or if current row has a name and stored one doesn't
        if loc_id not in location_map or (loc_name and not location_map[loc_id]):
            location_map[loc_id] = loc_name
    
    # Convert to list format
    locations: List[Dict[str, Optional[str]]] = []
    for loc_id, loc_name in sorted(location_map.items()):
        locations.append(
            {
                "location_id": loc_id,
                "location_name": loc_name,
            }
        )
    
    return locations


async def fetch_remote_patients(
    location_id: str,
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Fetch patient queue data from the remote production API instead of the local DB.

    Uses API_URL /patients endpoint with the same query parameters that this API exposes.
    """
    if not HTTPX_AVAILABLE:
        raise HTTPException(status_code=500, detail="httpx is required for remote API reads")

    api_url_env = os.getenv("API_URL")
    if not api_url_env or not api_url_env.strip():
        raise HTTPException(status_code=500, detail="API_URL must be set for remote API reads")

    api_base_url = api_url_env.strip().rstrip("/")
    url = f"{api_base_url}/patients"

    params: Dict[str, Any] = {"locationId": location_id}
    if statuses:
        # Repeat statuses param for each value to match existing API contract
        params["statuses"] = statuses
    if limit is not None:
        params["limit"] = limit

    api_key = os.getenv("API_KEY")
    api_token = os.getenv("API_TOKEN")

    headers: Dict[str, str] = {"Content-Type": "application/json"}

    # Prefer API key if present; otherwise use token / auto-token
    if api_key:
        headers["X-API-Key"] = api_key
    else:
        if not api_token:
            # Auto-fetch token using same helper as monitor/api_client
            from app.utils.api_client import get_api_token
            token = await get_api_token(api_base_url)
            api_token = token or ""
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:  # type: ignore[attr-defined]
            response = await client.get(url, params=params, headers=headers)

        if response.status_code != 200:
            detail = None
            try:
                data = response.json()
                detail = data.get("detail")
            except Exception:
                pass
            msg = detail or f"Remote API returned {response.status_code}"
            raise HTTPException(status_code=502, detail=msg)

        data = response.json()
        if not isinstance(data, list):
            raise HTTPException(status_code=502, detail="Remote API /patients response is not a list")

        # Data should already be in PatientPayload shape; normalize minimally
        return data

    except httpx.TimeoutException:  # type: ignore[attr-defined]
        raise HTTPException(status_code=504, detail="Remote API request timed out")
    except httpx.RequestError as e:  # type: ignore[attr-defined]
        raise HTTPException(status_code=502, detail=f"Error calling remote API: {e}")

