#!/usr/bin/env python3
"""
Azure AI Agent Client Module.

Handles communication with the Azure AI Experity Mapper Agent endpoint.
Provides retry logic, error handling, and response parsing.
"""

import asyncio
import json
import os
import time
import logging
from typing import Dict, Any, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logging.warning("httpx not available. Azure AI client will not work.")

try:
    from azure.identity import DefaultAzureCredential
    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False
    logging.warning("azure-identity not available. Azure AI client will not work.")


logger = logging.getLogger(__name__)

# Azure AI Configuration from environment variables
PROJECT_ENDPOINT = os.getenv(
    "AZURE_AI_PROJECT_ENDPOINT",
    "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"
)
AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "experitymapper")
AGENT_VERSION = os.getenv("AZURE_AI_AGENT_VERSION", "experitymapper:2")
DEPLOYMENT_NAME = os.getenv("AZURE_AI_DEPLOYMENT_NAME") or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "experitymapper")
API_VERSION = os.getenv("AZURE_AI_API_VERSION", "2025-11-15-preview")

# Timeout configuration
REQUEST_TIMEOUT = int(os.getenv("AZURE_AI_REQUEST_TIMEOUT", "120"))
CONNECTION_TIMEOUT = int(os.getenv("AZURE_AI_CONNECTION_TIMEOUT", "10"))

# Retry configuration
MAX_RETRIES = int(os.getenv("AZURE_AI_MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = int(os.getenv("AZURE_AI_RETRY_BACKOFF_BASE", "2"))

# Azure AD scope
AZURE_SCOPE = "https://ai.azure.com/.default"

# ICD-10 code mapping for backward compatibility conversion
ICD10_MAPPING = {
    "Anxiety": "F41.9",
    "Asthma": "J45.909",
    "Cancer": "C80.1",
    "Cardiac Arrhythmia": "I49.9",
    "Congestive Heart Failure": "I50.9",
    "COPD": "J44.9",
    "Diabetes": "E11.9",
    "GERD": "K21.9",
    "Hypertension": "I10"
}

# Token cache for performance optimization
_token_cache: Optional[str] = None
_token_expiry: float = 0.0
_token_buffer_seconds = 300  # Refresh token 5 minutes before expiry


class AzureAIClientError(Exception):
    """Base exception for Azure AI client errors."""
    pass


class AzureAIAuthenticationError(AzureAIClientError):
    """Authentication error with Azure AI."""
    pass


class AzureAIRateLimitError(AzureAIClientError):
    """Rate limit error from Azure AI."""
    pass


class AzureAITimeoutError(AzureAIClientError):
    """Timeout error from Azure AI."""
    pass


class AzureAIResponseError(AzureAIClientError):
    """Error parsing or processing Azure AI response."""
    pass


def _validate_config():
    """Validate that required configuration values are set."""
    if not AGENT_NAME:
        raise ValueError("AZURE_AI_AGENT_NAME must be set")
    if not PROJECT_ENDPOINT:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT must be set")


def _build_agent_url() -> str:
    """Build the Azure AI agent endpoint URL."""
    return f"{PROJECT_ENDPOINT}/applications/{AGENT_NAME}/protocols/openai/responses?api-version={API_VERSION}"


def _calculate_backoff(attempt: int) -> int:
    """Calculate exponential backoff wait time in seconds."""
    return RETRY_BACKOFF_BASE ** attempt


def get_azure_token() -> str:
    """
    Get Azure AD token using DefaultAzureCredential with caching.
    
    Tokens are cached until 5 minutes before expiry to reduce authentication overhead.
    
    Returns:
        Bearer token string
        
    Raises:
        AzureAIAuthenticationError: If authentication fails
    """
    global _token_cache, _token_expiry
    
    # Return cached token if still valid
    if _token_cache and time.time() < _token_expiry:
        return _token_cache
    
    if not AZURE_IDENTITY_AVAILABLE:
        raise AzureAIAuthenticationError(
            "azure-identity package not installed. Install it with: pip install azure-identity"
        )
    
    try:
        credential = DefaultAzureCredential()
        token_result = credential.get_token(AZURE_SCOPE)
        
        # Cache the token with expiry time (5 min buffer)
        _token_cache = token_result.token
        _token_expiry = token_result.expires_on - _token_buffer_seconds
        
        return _token_cache
    except Exception as e:
        logger.error(f"Failed to get Azure token: {str(e)}")
        raise AzureAIAuthenticationError(f"Failed to authenticate with Azure: {str(e)}") from e


def _check_response_status(response_json: Dict[str, Any]) -> None:
    """
    Check if Azure AI response status indicates an incomplete response.
    
    Raises:
        AzureAIResponseError: If response is incomplete
    """
    status = response_json.get("status", "complete")
    if status != "incomplete":
        return
    
    output_items = response_json.get("output", [])
    file_search_calls = [
        item for item in output_items 
        if item.get("type") == "file_search_call"
    ]
    
    if file_search_calls:
        raise AzureAIResponseError(
            f"Response incomplete: agent searching for configuration files "
            f"({len(file_search_calls)} file_search_call detected). "
            f"This may indicate missing configuration files, processing delay, "
            f"or agent configuration issue. Try increasing timeout."
        )
    else:
        raise AzureAIResponseError(
            "Response incomplete: agent may still be processing. "
            "Try increasing request timeout or check agent configuration."
        )


def _extract_output_text(response_json: Dict[str, Any]) -> str:
    """
    Extract text content from Azure AI response output items.
    
    Returns:
        Extracted text content
        
    Raises:
        AzureAIResponseError: If no output text found or errors present
    """
    output_items = response_json.get("output", [])
    if not output_items:
        raise AzureAIResponseError("Response contains no output items")
    
    output_text = ""
    error_messages = []
    
    for item in output_items:
        if item.get("type") != "message":
            continue
            
        content_blocks = item.get("content", [])
        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "output_text":
                output_text += block.get("text", "")
            elif block_type == "error":
                error_messages.append(block.get("text", str(block)))
            elif "text" in block:
                output_text += block.get("text", "")
    
    if error_messages:
        error_msg = "; ".join(error_messages)
        logger.error(f"Azure AI returned errors: {error_msg}")
        raise AzureAIResponseError(f"Azure AI agent returned errors: {error_msg}")
    
    if not output_text or not output_text.strip():
        # Build diagnostic information
        response_info = []
        if "error" in response_json:
            response_info.append(f"Error: {response_json.get('error')}")
        if "status" in response_json:
            response_info.append(f"Status: {response_json.get('status')}")
        
        for item in output_items:
            item_type = item.get("type", "unknown")
            if item_type != "message":
                response_info.append(f"Non-message item type: {item_type}")
        
        error_details = ". ".join(response_info) if response_info else "No additional details"
        response_summary = json.dumps(response_json, indent=2)[:500]
        
        raise AzureAIResponseError(
            f"No output text found in response. "
            f"Agent may have failed to generate response. "
            f"Details: {error_details}. "
            f"Response preview: {response_summary}"
        )
    
    return output_text


def _clean_json_text(text: str) -> str:
    """Remove markdown code blocks from JSON text if present."""
    text = text.strip()
    
    # Remove opening markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    # Remove closing markdown code blocks
    if text.endswith("```"):
        text = text[:-3]
    
    return text.strip()


def _parse_experity_json(text: str) -> Dict[str, Any]:
    """
    Parse JSON text into Experity mapping object.
    
    Handles wrapper structures and validates format.
    
    Returns:
        Parsed Experity mapping dictionary
        
    Raises:
        AzureAIResponseError: If JSON is invalid or format is unexpected
    """
    cleaned_text = _clean_json_text(text)
    
    try:
        experity_mapping = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON. Text preview: {cleaned_text[:500]}")
        raise AzureAIResponseError(
            f"Response text is not valid JSON: {str(e)}. "
            f"Preview: {cleaned_text[:200]}"
        ) from e
    
    # Handle wrapper structure: {success, data: {experity_actions: {...}}}
    if isinstance(experity_mapping, dict) and "success" in experity_mapping:
        if experity_mapping.get("success") is True and "data" in experity_mapping:
            data = experity_mapping["data"]
            if "experity_actions" in data:
                logger.info("Extracted experity_actions from wrapper structure")
                return data["experity_actions"]
            else:
                logger.warning("Wrapper structure found but experity_actions not in data, using data directly")
                return data
        elif experity_mapping.get("success") is False:
            error_info = experity_mapping.get("error", {})
            error_msg = error_info.get("message", "Unknown error") if isinstance(error_info, dict) else str(error_info)
            raise AzureAIResponseError(f"LLM returned error structure: {error_msg}")
    
    if not isinstance(experity_mapping, dict):
        raise AzureAIResponseError(
            f"Parsed response is not a JSON object (got {type(experity_mapping).__name__}). "
            f"Expected object with emrId, vitals, complaints, etc. "
            f"Preview: {str(experity_mapping)[:200]}"
        )
    
    return experity_mapping


def _create_default_vitals(encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create default vitals structure, optionally populated from encounter data."""
    vitals = {
        "gender": "unknown",
        "ageYears": None,
        "ageMonths": None,
        "heightCm": None,
        "weightKg": None,
        "bodyMassIndex": None,
        "weightClass": "unknown",
        "pulseRateBpm": None,
        "respirationBpm": None,
        "bodyTemperatureCelsius": None,
        "bloodPressureSystolicMm": None,
        "bloodPressureDiastolicMm": None,
        "pulseOx": None
    }
    
    if encounter_data:
        attributes = encounter_data.get("attributes", {})
        if attributes:
            for key in vitals:
                if key in attributes:
                    vitals[key] = attributes[key]
    
    return vitals


def _create_default_guardian(encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create default guardian structure, optionally populated from encounter data."""
    guardian = {
        "present": False,
        "guardianName": None,
        "relationship": None,
        "notes": None
    }
    
    if encounter_data:
        guardian_info = encounter_data.get("guardianAssistedInterview") or encounter_data.get("guardian")
        if guardian_info:
            guardian["present"] = guardian_info.get("present", True)
            guardian["guardianName"] = guardian_info.get("guardianName") or guardian_info.get("name")
            guardian["relationship"] = guardian_info.get("relationship")
            guardian["notes"] = guardian_info.get("notes")
    
    return guardian


def _extract_lab_orders(encounter_data: Optional[Dict[str, Any]] = None) -> list:
    """Extract lab orders from encounter data."""
    if not encounter_data:
        return []
    
    labs = encounter_data.get("labOrders") or encounter_data.get("labs") or []
    lab_orders = []
    
    for lab in labs:
        if isinstance(lab, dict):
            lab_orders.append({
                "orderId": lab.get("id") or lab.get("orderId"),
                "name": lab.get("name", ""),
                "status": lab.get("status"),
                "priority": lab.get("priority"),
                "reason": lab.get("reason")
            })
    
    return lab_orders


def _extract_icd_updates(encounter_data: Optional[Dict[str, Any]] = None) -> list:
    """Extract ICD updates from encounter conditions using ICD10_MAPPING."""
    if not encounter_data:
        return []
    
    conditions = encounter_data.get("conditions") or encounter_data.get("chronicConditions") or []
    icd_updates = []
    
    for condition in conditions:
        condition_name = condition.get("name") if isinstance(condition, dict) else str(condition)
        if condition_name in ICD10_MAPPING:
            icd_updates.append({
                "conditionName": condition_name,
                "icd10Code": ICD10_MAPPING[condition_name],
                "presentInEncounter": True,
                "source": "conditions"
            })
    
    return icd_updates


def _convert_legacy_array_format(
    action_array: list,
    encounter_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convert legacy array format to new object format.
    
    Legacy format: [{template, bodyAreaKey, mainProblem, ...}]
    New format: {emrId, vitals, complaints: [{...}]}
    """
    logger.warning(f"Converting legacy array format ({len(action_array)} items) to new object format")
    
    emr_id = None
    if encounter_data:
        emr_id = encounter_data.get("emrId") or encounter_data.get("emr_id")
    
    converted = {
        "emrId": emr_id,
        "vitals": _create_default_vitals(encounter_data),
        "guardianAssistedInterview": _create_default_guardian(encounter_data),
        "labOrders": _extract_lab_orders(encounter_data),
        "icdUpdates": _extract_icd_updates(encounter_data),
        "complaints": []
    }
    
    # Convert each action to a complaint object
    for action in action_array:
        if not isinstance(action, dict):
            continue
        
        complaint = {
            "encounterId": action.get("encounterId"),
            "complaintId": action.get("complaintId"),
            "description": action.get("description", ""),
            "traumaType": action.get("traumaType", ""),
            "bodyPartRaw": action.get("bodyPartRaw"),
            "reviewOfSystemsCategory": action.get("reviewOfSystemsCategory"),
            "gender": action.get("gender", "unknown"),
            "bodyAreaKey": action.get("bodyAreaKey", ""),
            "subLocationLabel": action.get("subLocationLabel"),
            "experityTemplate": action.get("template", action.get("experityTemplate", "")),
            "coordKey": action.get("coordKey", ""),
            "bodyMapSide": action.get("bodyMapSide", "front"),
            "ui": action.get("ui", {}),
            "mainProblem": action.get("mainProblem", ""),
            "notesTemplateKey": action.get("notesTemplateKey", ""),
            "notesPayload": action.get("notesPayload", {}),
            "notesFreeText": action.get("notesFreeText", action.get("notes", "")),
            "reasoning": action.get("reasoning", "")
        }
        converted["complaints"].append(complaint)
    
    logger.info(f"Converted {len(converted['complaints'])} legacy actions to new format")
    return converted


def _validate_response_structure(mapping: Dict[str, Any]) -> None:
    """Validate that response contains expected fields."""
    expected_fields = ["vitals", "complaints"]
    for field in expected_fields:
        if field not in mapping:
            logger.warning(f"Response missing expected field: {field}")


def extract_experity_actions(
    response_json: Dict[str, Any],
    encounter_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extract Experity mapping response from Azure AI response format.
    
    Processes Azure AI response and converts to Experity mapping format.
    Supports both new object format and legacy array format (with conversion).
    
    Args:
        response_json: Full Azure AI response JSON with structure:
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "{...}"  # JSON object string
                            }
                        ]
                    }
                ]
            }
        encounter_data: Optional encounter data for backward compatibility conversion
        
    Returns:
        Experity mapping object (dict) with structure:
            {
                "emrId": str | None,
                "vitals": {...},
                "guardianAssistedInterview": {...},
                "labOrders": [...],
                "icdUpdates": [...],
                "complaints": [...]
            }
        
    Raises:
        AzureAIResponseError: If response format is invalid or JSON parsing fails
    """
    # Check response status
    _check_response_status(response_json)
    
    # Extract text from output
    output_text = _extract_output_text(response_json)
    
    # Parse JSON from text
    experity_mapping = _parse_experity_json(output_text)
    
    # Handle legacy array format conversion
    if isinstance(experity_mapping, list):
        experity_mapping = _convert_legacy_array_format(experity_mapping, encounter_data)
    
    # Validate structure
    _validate_response_structure(experity_mapping)
    
    return experity_mapping


async def call_azure_ai_agent(queue_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Azure AI Experity Mapper Agent with a queue entry.
    
    Handles authentication, retries, error handling, and response parsing.
    Uses exponential backoff for retries and caches authentication tokens.
    
    Args:
        queue_entry: Queue entry dictionary containing:
            - raw_payload: Encounter data (required)
            - encounter_id: Encounter ID (optional, will be added if missing)
            - emr_id: EMR ID (optional, will be added if missing)
        
    Returns:
        Full Experity mapping object (dict) containing:
            - emrId
            - vitals
            - guardianAssistedInterview
            - labOrders
            - icdUpdates
            - complaints
        
    Raises:
        AzureAIClientError: Base error for all client errors
        AzureAIAuthenticationError: Authentication failures
        AzureAIRateLimitError: Rate limit exceeded
        AzureAITimeoutError: Request timeout
        AzureAIResponseError: Response parsing errors
    """
    # Validate configuration
    _validate_config()
    
    if not HTTPX_AVAILABLE:
        raise AzureAIClientError(
            "httpx package not installed. Install it with: pip install httpx"
        )
    
    # Build endpoint URL
    url = _build_agent_url()
    logger.info(f"Azure AI Agent URL: {url} (Agent: {AGENT_NAME}, Version: {AGENT_VERSION})")
    
    # Get Azure token (with caching)
    try:
        token = get_azure_token()
    except AzureAIAuthenticationError:
        raise
    
    # Extract and prepare encounter data
    if "raw_payload" in queue_entry and queue_entry["raw_payload"]:
        encounter_data = dict(queue_entry["raw_payload"])
        if "encounterId" not in encounter_data and "encounter_id" in queue_entry:
            encounter_data["encounterId"] = queue_entry["encounter_id"]
        if "emrId" not in encounter_data and "emr_id" in queue_entry:
            encounter_data["emrId"] = queue_entry["emr_id"]
    else:
        encounter_data = queue_entry
        logger.warning("No raw_payload found in queue_entry, using queue_entry directly")
    
    # Prepare request payload (minimal format for Azure AI Agents)
    payload = {
        "input": [
            {
                "role": "user",
                "content": json.dumps(encounter_data)
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    encounter_id = queue_entry.get("encounter_id", "unknown")
    last_error: Optional[Exception] = None
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECTION_TIMEOUT)) as client:
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Calling Azure AI agent (attempt {attempt + 1}/{MAX_RETRIES}) for encounter_id: {encounter_id}")
                
                response = await client.post(url, headers=headers, json=payload)
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else _calculate_backoff(attempt)
                    
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{MAX_RETRIES}")
                    
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise AzureAIRateLimitError(
                            f"Rate limit exceeded after {MAX_RETRIES} retries. "
                            f"Azure AI is throttling requests. Wait a few minutes before retrying."
                        )
                
                # Handle authentication errors (401)
                if response.status_code == 401:
                    raise AzureAIAuthenticationError(
                        "Authentication failed. Check Azure credentials."
                    )
                
                # Handle other HTTP errors (4xx, 5xx)
                if response.status_code >= 400:
                    error_text = response.text[:500]
                    raise AzureAIClientError(
                        f"Azure AI returned error {response.status_code}: {error_text}"
                    )
                
                # Parse response JSON
                try:
                    response_json = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse response as JSON: {response.text[:500]}")
                    raise AzureAIResponseError(f"Azure AI returned invalid JSON: {str(e)}")
                
                # Log response structure on first attempt (debug level)
                if attempt == 0:
                    logger.debug(f"Azure AI response structure: {json.dumps(response_json, indent=2)[:500]}")
                
                # Extract Experity mapping
                experity_mapping = extract_experity_actions(response_json, encounter_data=encounter_data)
                
                # Log success
                complaints_count = len(experity_mapping.get("complaints", []))
                logger.info(
                    f"Successfully received Experity mapping with {complaints_count} complaints "
                    f"for encounter_id: {encounter_id}"
                )
                
                return experity_mapping
                
            except httpx.TimeoutException:
                last_error = AzureAITimeoutError(
                    f"Request to Azure AI agent timed out after {REQUEST_TIMEOUT} seconds"
                )
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_calculate_backoff(attempt))
                    continue
                raise last_error
                
            except httpx.RequestError as e:
                last_error = AzureAIClientError(f"Network error calling Azure AI: {str(e)}")
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_calculate_backoff(attempt))
                    continue
                raise last_error
                
            except (AzureAIAuthenticationError, AzureAIRateLimitError, AzureAIResponseError):
                # Don't retry these errors
                raise
                
            except Exception as e:
                last_error = AzureAIClientError(f"Unexpected error: {str(e)}")
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_calculate_backoff(attempt))
                    continue
                raise last_error
    
    # Should not reach here, but handle edge case
    if last_error:
        raise last_error
    
    raise AzureAIClientError("Failed to call Azure AI agent after all retries")
