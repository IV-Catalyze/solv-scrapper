#!/usr/bin/env python3
"""
Intellivisit client configuration.

Defines per-environment client identifiers plus the locations each client
is permitted to access. Now uses HMAC secret keys for authentication.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from app.utils.locations import LOCATION_MAP


def _demo_location_id() -> str:
    """Return the location ID for the demo clinic."""
    try:
        return LOCATION_MAP["Exer Urgent Care - Demo"]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("Demo location missing from LOCATION_MAP") from exc


_STAGING_CLIENT_ID = "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"
_PRODUCTION_CLIENT_ID = "Prod-1f190fe5-d799-4786-bce2-37c3ad2c1561"


INTELLIVISIT_CLIENTS: Dict[str, Dict[str, object]] = {
    "staging": {
        "label": "Intellivisit Staging",
        "client_id": _STAGING_CLIENT_ID,
        "environment": "staging",
        "allowed_location_ids": [_demo_location_id()],  # Demo location only
        "scopes": ["patients:read", "patients:write", "encounters:write"],
        "hmac_secret_key": os.getenv("INTELLIVISIT_STAGING_HMAC_SECRET"),
    },
    "production": {
        "label": "Intellivisit Production",
        "client_id": _PRODUCTION_CLIENT_ID,
        "environment": "production",
        "allowed_location_ids": sorted(LOCATION_MAP.values()),  # All locations
        "scopes": ["patients:read", "patients:write", "encounters:write"],
        "hmac_secret_key": os.getenv("INTELLIVISIT_PRODUCTION_HMAC_SECRET"),
    },
}


CLIENTS_BY_ID: Dict[str, Dict[str, object]] = {
    cfg["client_id"]: {**cfg, "name": name} for name, cfg in INTELLIVISIT_CLIENTS.items()
}

# Map HMAC secret keys to client configurations
CLIENTS_BY_HMAC_SECRET: Dict[str, Dict[str, object]] = {
    cfg["hmac_secret_key"]: {**cfg, "name": name}
    for name, cfg in INTELLIVISIT_CLIENTS.items()
    if cfg.get("hmac_secret_key")
}


def get_client_config_by_id(client_id: Optional[str]) -> Optional[Dict[str, object]]:
    """Return the client configuration for the supplied identifier."""
    if not client_id:
        return None
    return CLIENTS_BY_ID.get(client_id)


def get_client_config_by_hmac_secret(secret_key: Optional[str]) -> Optional[Dict[str, object]]:
    """Return the client configuration for the supplied HMAC secret key."""
    if not secret_key:
        return None
    return CLIENTS_BY_HMAC_SECRET.get(secret_key)


def get_client_config_by_name(name: Optional[str]) -> Optional[Dict[str, object]]:
    """Return the client configuration for the supplied environment key."""
    if not name:
        return None
    return INTELLIVISIT_CLIENTS.get(name)


