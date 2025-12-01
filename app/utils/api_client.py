import json
import logging
import os
import threading
import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("⚠️  httpx not installed. API saving will be disabled. Install with: pip install httpx")

from app.database.utils import DB_AVAILABLE, get_db_connection
from app.utils.patient import normalize_status_value

try:
    from app.config.intellivisit_clients import get_client_config_by_name, INTELLIVISIT_CLIENTS
except ImportError:  # pragma: no cover - optional dependency for certain scripts
    INTELLIVISIT_CLIENTS = {}

    def get_client_config_by_name(_: Optional[str]):
        return None

logger = logging.getLogger(__name__)

_recently_sent_emr_ids: Set[str] = set()
_recently_sent_lock = threading.Lock()

_cached_token: Optional[str] = None
_token_expires_at: Optional[datetime] = None
_token_lock = threading.Lock()
_patch_endpoint_available = True


def _get_hmac_secret() -> Optional[str]:
    """
    Get HMAC secret key from environment variables.
    Prefers explicit HMAC_SECRET, then checks staging/production based on API_URL.
    
    Returns:
        HMAC secret key string or None if not found
    """
    # Check for explicit HMAC secret
    explicit_secret = os.getenv("HMAC_SECRET") or os.getenv("SOLV_HMAC_SECRET")
    if explicit_secret:
        return explicit_secret
    
    # Check for staging/production specific secrets
    staging_secret = os.getenv("INTELLIVISIT_STAGING_HMAC_SECRET")
    production_secret = os.getenv("INTELLIVISIT_PRODUCTION_HMAC_SECRET")
    
    # Determine which one to use based on API_URL or default to staging
    api_url = os.getenv("API_URL", "")
    if "staging" in api_url.lower() or not production_secret:
        return staging_secret
    else:
        return production_secret or staging_secret


def _generate_hmac_headers(method: str, path: str, body: Any, secret_key: str) -> Dict[str, str]:
    """
    Generate HMAC authentication headers for a request.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path (with query string if applicable)
        body: Request body (dict, str, or bytes). For GET requests, use None or empty dict.
        secret_key: HMAC secret key
        
    Returns:
        Dictionary with X-Timestamp and X-Signature headers
    """
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Convert body to bytes
    if method.upper() == "GET":
        body_bytes = b''
    elif isinstance(body, dict):
        body_str = json.dumps(body)
        body_bytes = body_str.encode('utf-8')
    elif isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif isinstance(body, bytes):
        body_bytes = body
    elif body is None:
        body_bytes = b''
    else:
        body_bytes = b''
    
    # Calculate body hash
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    
    # Create canonical string
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    
    # Generate HMAC signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    headers = {
        "X-Timestamp": timestamp,
        "X-Signature": signature_b64
    }
    
    # Only add Content-Type for requests with body
    if method.upper() in ["POST", "PUT", "PATCH"] and body_bytes:
        headers["Content-Type"] = "application/json"
    
    return headers


def _resolve_default_client_id() -> str:
    """
    Determine which client_id should be used when requesting API tokens.
    Prefers explicit API_CLIENT_ID, otherwise falls back to configured environments.
    """
    explicit = os.getenv("API_CLIENT_ID")
    if explicit:
        return explicit

    env_name = os.getenv("INTELLIVISIT_CLIENT_ENV") or os.getenv("API_CLIENT_NAME") or "staging"
    env_name = env_name.lower()

    cfg = get_client_config_by_name(env_name)
    if cfg and cfg.get("client_id"):
        return str(cfg["client_id"])

    # As a final fallback, pick the first configured client if available.
    for cfg in INTELLIVISIT_CLIENTS.values():
        client_id = cfg.get("client_id")
        if client_id:
            return str(client_id)

    # Last resort for environments without config import.
    return "Stage-1c3dca8d-730f-4a32-9221-4e4277903505"


def check_if_patient_recently_sent(emr_id: str, minutes_threshold: int = 5) -> bool:
    """
    Check if a patient with this EMR ID was recently sent to the API.
    Checks both in-memory cache and database.
    """
    if not emr_id:
        return False

    with _recently_sent_lock:
        if emr_id in _recently_sent_emr_ids:
            return True

    if not DB_AVAILABLE:
        return False

    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, created_at, updated_at
            FROM patients
            WHERE emr_id = %s
            AND (created_at > NOW() - INTERVAL '{minutes_threshold} minutes' 
                 OR updated_at > NOW() - INTERVAL '{minutes_threshold} minutes')
            ORDER BY created_at DESC
            LIMIT 1
        """,
            (emr_id,),
        )

        result = cursor.fetchone()
        cursor.close()

        if result:
            with _recently_sent_lock:
                _recently_sent_emr_ids.add(emr_id)
            return True

        return False
    except Exception as e:
        logger.warning("Error checking for duplicate EMR ID %s: %s", emr_id, e)
        return False
    finally:
        conn.close()


async def get_api_token(api_base_url: str, force_refresh: bool = False) -> Optional[str]:
    """
    Get an API token, using cache if available and not expired.
    Automatically fetches a new token if needed.
    """
    global _cached_token, _token_expires_at

    if not force_refresh and _cached_token and _token_expires_at:
        time_until_expiry = (_token_expires_at - datetime.now()).total_seconds()
        if time_until_expiry > 300:
            return _cached_token

    if not HTTPX_AVAILABLE:
        logger.warning("httpx not available. Cannot get API token.")
        return None

    client_id = _resolve_default_client_id()
    expires_hours_env = os.getenv("API_TOKEN_EXPIRES_HOURS")
    expires_hours = int(expires_hours_env) if expires_hours_env else None

    token_url = api_base_url.rstrip("/") + "/auth/token"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:  # type: ignore[attr-defined]
            logger.info("Requesting API token from: %s", token_url)
            # Only include expires_hours if explicitly set (defaults to 24 hours on server)
            token_request = {"client_id": client_id}
            if expires_hours is not None:
                token_request["expires_hours"] = expires_hours
            response = await client.post(
                token_url,
                json=token_request,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get("access_token")
                expires_at_str = token_data.get("expires_at")

                if access_token:
                    if expires_at_str:
                        try:
                            if expires_at_str.endswith("Z"):
                                expires_at_str = expires_at_str[:-1] + "+00:00"
                            _token_expires_at = datetime.fromisoformat(expires_at_str)
                        except Exception:
                            # Default to 24 hours if expires_hours not set
                            _token_expires_at = datetime.now() + timedelta(hours=expires_hours or 24)
                    else:
                        # Default to 24 hours if expires_hours not set
                        _token_expires_at = datetime.now() + timedelta(hours=expires_hours or 24)

                    with _token_lock:
                        _cached_token = access_token

                    logger.info("API token obtained successfully (expires: %s)", _token_expires_at)
                    return access_token
                else:
                    logger.warning("Token response missing access_token")
                    return None
            else:
                error_detail: Any = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                logger.warning("Failed to get API token: %s - %s", response.status_code, error_detail)
                return None

    except httpx.TimeoutException:  # type: ignore[attr-defined]
        logger.warning("Token request timed out")
        return None
    except httpx.RequestError as e:  # type: ignore[attr-defined]
        logger.warning("Token request error: %s", e)
        return None
    except Exception as e:
        logger.warning("Error getting API token: %s", e)
        return None


async def send_patient_to_api(patient_data: Dict[str, Any]) -> bool:
    """
    Send patient data to the API endpoint when EMR ID is available.
    Prevents duplicate sends by checking if patient was recently sent.
    """
    if not HTTPX_AVAILABLE:
        return False

    emr_id = patient_data.get("emr_id")
    if not emr_id:
        return False

    if check_if_patient_recently_sent(emr_id):
        api_url_env = os.getenv("API_URL")
        if api_url_env and api_url_env.strip():
            target_api = api_url_env.strip().rstrip("/") + "/patients/create"
            logger.info(
                "Skipping duplicate EMR %s; would send to production API: %s",
                emr_id,
                target_api,
            )
        else:
            logger.info("Skipping duplicate EMR %s; API_URL not set", emr_id)
        return True

    if not HTTPX_AVAILABLE:
        print("   ⚠️  httpx not available. Cannot send to API.")
        return False

    api_url_env = os.getenv("API_URL")

    if not api_url_env or not api_url_env.strip():
        logger.error("API_URL environment variable is required but not set")
        return False

    api_base_url = api_url_env.strip().rstrip("/")
    api_url = api_base_url + "/patients/create"
    logger.info("Sending to production API: %s", api_url)

    # Use HMAC authentication
    hmac_secret = _get_hmac_secret()
    if not hmac_secret:
        logger.error("HMAC secret key not found. Set HMAC_SECRET, INTELLIVISIT_STAGING_HMAC_SECRET, or INTELLIVISIT_PRODUCTION_HMAC_SECRET")
        return False
    
    # Extract path from URL for HMAC signature
    parsed_url = urlparse(api_url)
    path = parsed_url.path
    if parsed_url.query:
        path += f"?{parsed_url.query}"
    
    api_payload = {
        "emr_id": patient_data.get("emr_id") or "",
        "booking_id": patient_data.get("booking_id") or "",
        "booking_number": patient_data.get("booking_number") or "",
        "patient_number": patient_data.get("patient_number") or "",
        "location_id": patient_data.get("location_id") or "",
        "location_name": patient_data.get("location_name") or "",
        "legalFirstName": patient_data.get("legalFirstName") or patient_data.get("legal_first_name") or "",
        "legalLastName": patient_data.get("legalLastName") or patient_data.get("legal_last_name") or "",
        "dob": patient_data.get("dob") or "",
        "mobilePhone": patient_data.get("mobilePhone") or patient_data.get("mobile_phone") or "",
        "sexAtBirth": patient_data.get("sexAtBirth") or patient_data.get("sex_at_birth") or "",
        "reasonForVisit": patient_data.get("reasonForVisit") or patient_data.get("reason_for_visit") or "",
        "status": patient_data.get("status") or "checked_in",
        "captured_at": patient_data.get("captured_at") or datetime.now().isoformat(),
    }

    api_payload = {k: v if v else None for k, v in api_payload.items()}

    # Generate HMAC headers for authentication
    headers = _generate_hmac_headers("POST", path, api_payload, hmac_secret)
    logger.info("Using HMAC authentication")

    logger.debug("API Request URL: %s", api_url)
    logger.debug("API Request payload: %s", json.dumps(api_payload, default=str))
    logger.debug("API Request headers: %s", json.dumps(headers))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:  # type: ignore[attr-defined]
            logger.info("Sending HTTP request to patient API...")
            response = await client.post(api_url, json=api_payload, headers=headers)
            logger.info("Response received from patient API: %s", response.status_code)

            if response.status_code == 401:
                error_detail: Any = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                logger.error("API returned 401: %s", error_detail)
                return False

            if response.status_code in [200, 201]:
                result = response.json()
                emr_id_sent = api_payload.get("emr_id")
                print(f"   ✅ Patient data sent to API successfully (EMR ID: {emr_id_sent})")
                if emr_id_sent:
                    with _recently_sent_lock:
                        _recently_sent_emr_ids.add(emr_id_sent)  # type: ignore[arg-type]
                return True
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                logger.warning("API returned error %s: %s", response.status_code, error_detail)
                return False

    except httpx.TimeoutException:  # type: ignore[attr-defined]
        logger.warning("API request timed out after 30 seconds")
        return False
    except httpx.RequestError as e:  # type: ignore[attr-defined]
        logger.warning("API request error: %s", e)
        return False
    except Exception as e:
        logger.warning("Error sending to API: %s", e)
        return False


async def send_status_update_to_api(
    emr_id: str,
    status: str,
    patient_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send status update to API by matching EMR ID.
    Works without database - uses provided patient_data or creates minimal update payload.
    """
    if not HTTPX_AVAILABLE:
        return False

    emr_id_clean = str(emr_id).strip() if emr_id else None
    if not emr_id_clean:
        return False

    normalized_status = normalize_status_value(status)
    if not normalized_status:
        return False

    if patient_data:
        patient_to_update = patient_data.copy()
        patient_to_update["status"] = normalized_status
        patient_to_update["emr_id"] = emr_id_clean
    else:
        patient_to_update = {"emr_id": emr_id_clean, "status": normalized_status}

    logger.info("Sending status update to API (EMR ID: %s, status: %s)", emr_id_clean, normalized_status)
    return await send_patient_to_api(patient_to_update)


async def send_patch_status_update(emr_id: str, status: str) -> bool:
    """
    Send a PATCH request to update patient status via the /patients/{emr_id} endpoint.
    
    This is more efficient than POST /patients/create for status-only updates.
    """
    global _patch_endpoint_available

    if not HTTPX_AVAILABLE:
        logger.warning("httpx not available. Cannot send PATCH status update.")
        return False

    if not _patch_endpoint_available:
        # Remote API doesn't support PATCH; skip trying until process restarts
        return False

    emr_id_clean = str(emr_id).strip() if emr_id else None
    if not emr_id_clean:
        logger.warning("Cannot send PATCH status update: emr_id is required")
        return False

    normalized_status = normalize_status_value(status)
    if not normalized_status:
        logger.warning("Cannot send PATCH status update: invalid status value: %s", status)
        return False

    api_url_env = os.getenv("API_URL")
    if not api_url_env or not api_url_env.strip():
        logger.error("API_URL environment variable is required but not set")
        return False

    api_base_url = api_url_env.strip().rstrip("/")
    api_url = f"{api_base_url}/patients/{emr_id_clean}"
    logger.info("Sending PATCH status update to: %s", api_url)

    # Use HMAC authentication
    hmac_secret = _get_hmac_secret()
    if not hmac_secret:
        logger.error("HMAC secret key not found. Set HMAC_SECRET, INTELLIVISIT_STAGING_HMAC_SECRET, or INTELLIVISIT_PRODUCTION_HMAC_SECRET")
        return False
    
    # Extract path from URL for HMAC signature
    parsed_url = urlparse(api_url)
    path = parsed_url.path
    if parsed_url.query:
        path += f"?{parsed_url.query}"

    patch_payload = {"status": normalized_status}

    # Generate HMAC headers for authentication
    headers = _generate_hmac_headers("PATCH", path, patch_payload, hmac_secret)
    logger.info("Using HMAC authentication for PATCH request")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:  # type: ignore[attr-defined]
            logger.debug("Sending PATCH request: %s", json.dumps(patch_payload))
            response = await client.patch(api_url, json=patch_payload, headers=headers)
            logger.info("PATCH response status: %s", response.status_code)

            if response.status_code == 401:
                error_detail: Any = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                logger.error("PATCH request returned 401: %s", error_detail)

            if response.status_code == 404:
                # Endpoint not deployed on remote API. Disable future attempts to avoid noise.
                _patch_endpoint_available = False
                logger.info(
                    "PATCH endpoint %s not available (404). Disabling PATCH attempts and falling back to POST.",
                    api_url,
                )
                return False

            if response.status_code in [200, 204]:
                logger.info("✅ PATCH status update successful (EMR ID: %s, status: %s)", emr_id_clean, normalized_status)
                return True
            else:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", error_detail)
                except Exception:
                    pass
                logger.warning("PATCH request failed with status %s: %s", response.status_code, error_detail)
                return False

    except httpx.TimeoutException:  # type: ignore[attr-defined]
        logger.warning("PATCH request timed out after 30 seconds")
        return False
    except httpx.RequestError as e:  # type: ignore[attr-defined]
        logger.warning("PATCH request error: %s", e)
        return False
    except Exception as e:
        logger.warning("Error sending PATCH request: %s", e)
        return False


