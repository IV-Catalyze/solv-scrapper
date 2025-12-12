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
from typing import Dict, Any, List, Optional
from datetime import datetime

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

def get_env_or_default(key: str, default: str) -> str:
    """
    Get environment variable, but treat empty string as not set.
    This ensures that empty strings in environment variables don't prevent defaults from being used.
    """
    value = os.getenv(key)
    return value if value and value.strip() else default

# Azure AI Configuration from environment variables
# Support both AZURE_AI_PROJECT_ENDPOINT and AZURE_EXISTING_AIPROJECT_ENDPOINT
PROJECT_ENDPOINT = os.getenv(
    "AZURE_AI_PROJECT_ENDPOINT",
    os.getenv(
        "AZURE_EXISTING_AIPROJECT_ENDPOINT",
        "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"
    )
)
AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "IV-Experity-Mapper-Agent")

# Priority order: AZURE_EXISTING_AGENT_ID > AZURE_AI_AGENT_VERSION > AZURE_AI_DEPLOYMENT_NAME > default
# This matches the original working configuration where AZURE_EXISTING_AGENT_ID was used
# Prefer agent version ID format (e.g., "IV-Experity-Mapper-Agent:34") if available
# Otherwise use deployment name (e.g., "iv-experity-mapper-gpt-4o")
AGENT_VERSION = get_env_or_default(
    "AZURE_EXISTING_AGENT_ID",  # Original working format - check this first
    get_env_or_default(
        "AZURE_AI_AGENT_VERSION",  # Alternative agent version format
        get_env_or_default(
            "AZURE_AI_DEPLOYMENT_NAME",  # Fall back to deployment name
            "IV-Experity-Mapper-Agent:34"  # Default to version 34 (from server config)
        )
    )
)

API_VERSION = os.getenv("AZURE_AI_API_VERSION", "2025-11-15-preview")

# Timeout configuration - defaults match production server settings
REQUEST_TIMEOUT = int(os.getenv("AZURE_AI_REQUEST_TIMEOUT", "300"))  # 5 minutes for Azure AI operations
CONNECTION_TIMEOUT = int(os.getenv("AZURE_AI_CONNECTION_TIMEOUT", "60"))  # 1 minute connection timeout

# Log the deployment name being used for debugging
logger.info(f"Azure AI Configuration - Using deployment/agent version: {AGENT_VERSION}")
logger.debug(f"Azure AI Configuration - AGENT_NAME: {AGENT_NAME}, REQUEST_TIMEOUT: {REQUEST_TIMEOUT}s, CONNECTION_TIMEOUT: {CONNECTION_TIMEOUT}s")

# Retry configuration
MAX_RETRIES = int(os.getenv("AZURE_AI_MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = int(os.getenv("AZURE_AI_RETRY_BACKOFF_BASE", "2"))

# Azure AD scope
AZURE_SCOPE = "https://ai.azure.com/.default"


class AzureAIClientError(Exception):
    """Base exception for Azure AI client errors."""
    pass


class AzureAIAuthenticationError(AzureAIClientError):
    """Authentication error with Azure AI."""
    pass


class AzureAIRateLimitError(AzureAIClientError):
    """Rate limit error from Azure AI."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after  # Retry-After header value in seconds


class AzureAITimeoutError(AzureAIClientError):
    """Timeout error from Azure AI."""
    pass


class AzureAIResponseError(AzureAIClientError):
    """Error parsing or processing Azure AI response."""
    pass


def get_azure_token() -> str:
    """
    Get Azure AD token using DefaultAzureCredential.
    
    Returns:
        Bearer token string
        
    Raises:
        AzureAIAuthenticationError: If authentication fails
    """
    if not AZURE_IDENTITY_AVAILABLE:
        raise AzureAIAuthenticationError(
            "azure-identity package not installed. Install it with: pip install azure-identity"
        )
    
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token(AZURE_SCOPE)
        return token.token
    except Exception as e:
        logger.error(f"Failed to get Azure token: {str(e)}")
        raise AzureAIAuthenticationError(f"Failed to authenticate with Azure: {str(e)}") from e


def extract_experity_actions(response_json: Dict[str, Any], encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract Experity mapping response from Azure AI response format.
    
    Args:
        response_json: Full Azure AI response JSON
        encounter_data: Optional encounter data for backward compatibility conversion
    
    The Azure AI response has this structure:
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
    
    The LLM returns a full JSON object with:
    - emrId
    - vitals
    - guardianAssistedInterview
    - labOrders
    - icdUpdates
    - complaints
    
    Args:
        response_json: Full Azure AI response JSON
        
    Returns:
        Full Experity mapping object (dict)
        
    Raises:
        AzureAIResponseError: If response format is invalid or JSON parsing fails
    """
    try:
        # Check if response is incomplete
        status = response_json.get("status", "complete")
        if status == "incomplete":
            # Check for file_search_call or other tool calls
            output_items = response_json.get("output", [])
            file_search_calls = []
            for item in output_items:
                if item.get("type") == "file_search_call":
                    file_search_calls.append(item)
            
            if file_search_calls:
                raise AzureAIResponseError(
                    f"Azure AI agent response is incomplete. The agent is searching for configuration files "
                    f"(file_search_call detected). This may indicate: "
                    f"1) Configuration files are missing from the vector store, "
                    f"2) The agent is still processing (may need longer timeout), "
                    f"3) Agent configuration issue. "
                    f"File search calls found: {len(file_search_calls)}"
                )
            else:
                raise AzureAIResponseError(
                    "Azure AI agent response is incomplete. The agent may still be processing. "
                    "Try increasing the request timeout or check agent configuration."
                )
        
        output_items = response_json.get("output", [])
        if not output_items:
            raise AzureAIResponseError("Response contains no output items")
        
        # Extract text from output - check all content types
        output_text = ""
        error_messages = []
        
        for item in output_items:
            if item.get("type") == "message":
                content_blocks = item.get("content", [])
                for block in content_blocks:
                    block_type = block.get("type")
                    if block_type == "output_text":
                        output_text += block.get("text", "")
                    elif block_type == "error":
                        error_messages.append(block.get("text", str(block)))
                    # Also check for other potential text fields
                    elif "text" in block:
                        output_text += block.get("text", "")
        
        # If we have error messages, include them in the error
        if error_messages:
            error_msg = "; ".join(error_messages)
            logger.error(f"Azure AI returned errors: {error_msg}")
            raise AzureAIResponseError(f"Azure AI agent returned errors: {error_msg}")
        
        # Check if output_text is empty or just whitespace
        if not output_text or not output_text.strip():
            # Log the full response structure for debugging
            response_summary = json.dumps(response_json, indent=2)[:2000]  # Increased limit
            logger.error(f"Empty output_text. Full response structure: {response_summary}")
            
            # Try to find any useful information in the response
            response_info = []
            if "error" in response_json:
                response_info.append(f"Error field: {response_json.get('error')}")
            if "message" in response_json:
                response_info.append(f"Message: {response_json.get('message')}")
            if "status" in response_json:
                response_info.append(f"Status: {response_json.get('status')}")
            
            # Check for alternative response structures
            for item in output_items:
                item_type = item.get("type", "unknown")
                if item_type != "message":
                    response_info.append(f"Found non-message item type: {item_type}")
                if "error" in item:
                    response_info.append(f"Item error: {item.get('error')}")
            
            error_details = ". ".join(response_info) if response_info else "No additional error details found"
            
            raise AzureAIResponseError(
                f"No output_text found in response or output_text is empty. "
                f"The Azure AI agent may have failed to generate a response. "
                f"Response details: {error_details}. "
                f"Full response (first 500 chars): {response_summary[:500]}"
            )
        
        # Try to extract JSON - the LLM might return JSON wrapped in markdown code blocks
        output_text_clean = output_text.strip()
        
        # Remove markdown code blocks if present
        if output_text_clean.startswith("```json"):
            output_text_clean = output_text_clean[7:]  # Remove ```json
        elif output_text_clean.startswith("```"):
            output_text_clean = output_text_clean[3:]  # Remove ```
        
        if output_text_clean.endswith("```"):
            output_text_clean = output_text_clean[:-3]  # Remove trailing ```
        
        output_text_clean = output_text_clean.strip()
        
        # Parse JSON string to object
        try:
            experity_mapping = json.loads(output_text_clean)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from output text. First 500 chars: {output_text[:500]}")
            logger.error(f"Cleaned text first 500 chars: {output_text_clean[:500]}")
            raise AzureAIResponseError(
                f"Response text is not valid JSON: {str(e)}. "
                f"Output text preview: {output_text_clean[:200]}"
            ) from e
        
        # Handle new prompt format: full wrapper structure {success, data: {experityActions: {...}, ...}, error}
        if isinstance(experity_mapping, dict) and "success" in experity_mapping:
            # LLM returned full wrapper structure from new prompt
            if experity_mapping.get("success") is True and "data" in experity_mapping:
                data = experity_mapping["data"]
                
                # Normalize snake_case to camelCase for all fields
                # Convert experity_actions to experityActions
                if "experity_actions" in data and "experityActions" not in data:
                    data["experityActions"] = data.pop("experity_actions")
                    logger.warning("Converted experity_actions to experityActions (snake_case to camelCase)")
                elif "experity_actions" in data and "experityActions" in data:
                    # Both exist - check for nested structure
                    if isinstance(data["experity_actions"], dict) and "experityActions" in data["experity_actions"]:
                        logger.warning("Found nested experity_actions.experityActions structure - using inner experityActions")
                        data["experityActions"] = data["experity_actions"]["experityActions"]
                    else:
                        logger.warning("Both experity_actions and experityActions exist - using experityActions")
                    del data["experity_actions"]
                
                # Convert encounter_id to encounterId
                if "encounter_id" in data and "encounterId" not in data:
                    data["encounterId"] = data.pop("encounter_id")
                    logger.warning("Converted encounter_id to encounterId (snake_case to camelCase)")
                elif "encounter_id" in data and "encounterId" in data:
                    logger.warning("Removing duplicate field: encounter_id (using encounterId)")
                    del data["encounter_id"]
                
                # Convert processed_at to processedAt
                if "processed_at" in data and "processedAt" not in data:
                    data["processedAt"] = data.pop("processed_at")
                    logger.warning("Converted processed_at to processedAt (snake_case to camelCase)")
                elif "processed_at" in data and "processedAt" in data:
                    logger.warning("Removing duplicate field: processed_at (using processedAt)")
                    del data["processed_at"]
                
                # Convert queue_id to queueId
                if "queue_id" in data and "queueId" not in data:
                    data["queueId"] = data.pop("queue_id")
                    logger.warning("Converted queue_id to queueId (snake_case to camelCase)")
                elif "queue_id" in data and "queueId" in data:
                    logger.warning("Removing duplicate field: queue_id (using queueId)")
                    del data["queue_id"]
                
                # Extract experityActions from data (camelCase - preferred)
                if "experityActions" in data:
                    experity_mapping = data["experityActions"]
                    logger.info("Extracted experityActions from full wrapper structure (camelCase)")
                else:
                    # If experityActions not in data, use data itself (backward compatibility)
                    logger.warning("Full wrapper structure found but experityActions not in data, using data directly")
                    experity_mapping = data
            elif experity_mapping.get("success") is False:
                # LLM returned error structure
                error_info = experity_mapping.get("error", {})
                error_msg = error_info.get("message", "Unknown error") if isinstance(error_info, dict) else str(error_info)
                raise AzureAIResponseError(f"LLM returned error structure: {error_msg}")
        
        # Handle backward compatibility: convert old array format to new object format
        if isinstance(experity_mapping, list):
            logger.warning(
                f"LLM returned old array format (legacy). Converting to new object format. "
                f"Array length: {len(experity_mapping)}"
            )
            # Convert old array format to new object format
            # Old format: [{template, bodyAreaKey, mainProblem, ...}]
            # New format: {emrId, vitals, complaints: [{...}]}
            
            # Extract emrId and vitals from encounter_data if available
            emr_id = None
            vitals_data = {
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
                # Extract emrId
                emr_id = encounter_data.get("emrId") or encounter_data.get("emr_id")
                
                # Extract vitals from attributes
                attributes = encounter_data.get("attributes", {})
                if attributes:
                    vitals_data["gender"] = attributes.get("gender", "unknown")
                    vitals_data["ageYears"] = attributes.get("ageYears")
                    vitals_data["ageMonths"] = attributes.get("ageMonths")
                    vitals_data["heightCm"] = attributes.get("heightCm")
                    vitals_data["weightKg"] = attributes.get("weightKg")
                    vitals_data["bodyMassIndex"] = attributes.get("bodyMassIndex")
                    vitals_data["weightClass"] = attributes.get("weightClass", "unknown")
                    vitals_data["pulseRateBpm"] = attributes.get("pulseRateBpm")
                    vitals_data["respirationBpm"] = attributes.get("respirationBpm")
                    vitals_data["bodyTemperatureCelsius"] = attributes.get("bodyTemperatureCelsius")
                    vitals_data["bloodPressureSystolicMm"] = attributes.get("bloodPressureSystolicMm")
                    vitals_data["bloodPressureDiastolicMm"] = attributes.get("bloodPressureDiastolicMm")
                    vitals_data["pulseOx"] = attributes.get("pulseOx")
            
            # Extract guardianAssistedInterview
            guardian_data = {
                "present": False,
                "guardianName": None,
                "relationship": None,
                "notes": None
            }
            if encounter_data:
                guardian_info = encounter_data.get("guardianAssistedInterview") or encounter_data.get("guardian")
                if guardian_info:
                    guardian_data["present"] = guardian_info.get("present", True)
                    guardian_data["guardianName"] = guardian_info.get("guardianName") or guardian_info.get("name")
                    guardian_data["relationship"] = guardian_info.get("relationship")
                    guardian_data["notes"] = guardian_info.get("notes")
            
            # Extract labOrders
            lab_orders = []
            if encounter_data:
                labs = encounter_data.get("labOrders") or encounter_data.get("labs") or []
                for lab in labs:
                    if isinstance(lab, dict):
                        lab_orders.append({
                            "orderId": lab.get("id") or lab.get("orderId"),
                            "name": lab.get("name", ""),
                            "status": lab.get("status"),
                            "priority": lab.get("priority"),
                            "reason": lab.get("reason")
                        })
            
            # Extract icdUpdates from conditions
            icd_updates = []
            if encounter_data:
                conditions = encounter_data.get("conditions") or encounter_data.get("chronicConditions") or []
                icd_mapping = {
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
                for condition in conditions:
                    condition_name = condition.get("name") if isinstance(condition, dict) else str(condition)
                    if condition_name in icd_mapping:
                        icd_updates.append({
                            "conditionName": condition_name,
                            "icd10Code": icd_mapping[condition_name],
                            "presentInEncounter": True,
                            "source": "conditions"
                        })
            
            converted_response = {
                "emrId": emr_id,
                "vitals": vitals_data,
                "guardianAssistedInterview": guardian_data,
                "labOrders": lab_orders,
                "icdUpdates": icd_updates,
                "complaints": []
            }
            
            # Convert each action in the array to a complaint object
            for action in experity_mapping:
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
                converted_response["complaints"].append(complaint)
            
            experity_mapping = converted_response
            logger.info(f"Converted {len(converted_response['complaints'])} legacy actions to new format")
        elif not isinstance(experity_mapping, dict):
            logger.error(f"LLM returned unexpected type: {type(experity_mapping)}. Value: {str(experity_mapping)[:200]}")
            raise AzureAIResponseError(
                f"Parsed response is not a JSON object (got {type(experity_mapping).__name__}). "
                f"The LLM should return a JSON object with emrId, vitals, complaints, etc. "
                f"Response preview: {str(experity_mapping)[:200]}"
            )
        
        # Basic validation - check for expected top-level fields
        expected_fields = ["vitals", "complaints"]
        for field in expected_fields:
            if field not in experity_mapping:
                logger.warning(f"Response missing expected field: {field}")
        
        # Safety check: Ensure emrId is null if it was missing from input and LLM used clientId
        if encounter_data:
            input_emr_id = encounter_data.get("emrId") or encounter_data.get("emr_id")
            input_client_id = encounter_data.get("clientId") or encounter_data.get("client_id")
            output_emr_id = experity_mapping.get("emrId")
            
            # Check if input_emr_id is actually the clientId (incorrectly set)
            # This can happen if the endpoint set emr_id to clientId in queue_entry
            input_emr_is_client_id = input_emr_id and input_client_id and input_emr_id == input_client_id
            
            # If emrId was missing from input OR if input_emr_id equals clientId (incorrectly set)
            # and LLM returned clientId value, set to null
            if (not input_emr_id or input_emr_is_client_id) and input_client_id and output_emr_id == input_client_id:
                logger.warning(
                    f"LLM incorrectly used clientId '{input_client_id}' as emrId. "
                    f"Setting emrId to null since emrId was missing from original input."
                )
                experity_mapping["emrId"] = None
            # If emrId was missing from input (or equals clientId) and output is not null, set to null
            elif (not input_emr_id or input_emr_is_client_id) and output_emr_id is not None:
                logger.warning(
                    f"emrId was missing from original input but LLM returned '{output_emr_id}'. "
                    f"Setting emrId to null to match original input."
                )
                experity_mapping["emrId"] = None
        
        return experity_mapping
        
    except AzureAIResponseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error extracting Experity mapping: {str(e)}")
        raise AzureAIResponseError(f"Failed to extract Experity mapping: {str(e)}") from e


async def call_azure_ai_agent(queue_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Azure AI Experity Mapper Agent with a queue entry.
    
    Args:
        queue_entry: Queue entry dictionary containing raw_payload
        
    Returns:
        Full Experity mapping object (dict) containing emrId, vitals, 
        guardianAssistedInterview, labOrders, icdUpdates, and complaints
        
    Raises:
        AzureAIClientError: Various error types for different failure modes
    """
    import time
    start_time = time.perf_counter()
    
    if not HTTPX_AVAILABLE:
        raise AzureAIClientError(
            "httpx package not installed. Install it with: pip install httpx"
        )
    
    # Build URL
    url = f"{PROJECT_ENDPOINT}/applications/{AGENT_NAME}/protocols/openai/responses?api-version={API_VERSION}"
    
    # Get Azure token
    token_start = time.perf_counter()
    try:
        token = get_azure_token()
        token_time = time.perf_counter() - token_start
        logger.info(f"⏱️  Azure token acquisition: {token_time:.3f}s")
    except AzureAIAuthenticationError:
        raise
    
    # Extract raw_payload from queue_entry - the LLM prompt expects encounter data directly
    # If queue_entry has raw_payload, use that; otherwise use queue_entry itself
    if "raw_payload" in queue_entry and queue_entry["raw_payload"]:
        # Create a copy to avoid modifying the original
        encounter_data = dict(queue_entry["raw_payload"])
        # Also include encounter_id from queue_entry if not in raw_payload
        if "encounterId" not in encounter_data and "encounter_id" in queue_entry:
            encounter_data["encounterId"] = queue_entry["encounter_id"]
        # Only copy emr_id from queue_entry if it's actually an emrId (not clientId)
        # This prevents clientId from being incorrectly used as emrId
        if "emrId" not in encounter_data and "emr_id" in queue_entry:
            # Only use emr_id from queue_entry if it's not the same as clientId
            # (This is a safety check to prevent clientId from being used as emrId)
            client_id = encounter_data.get("clientId") or encounter_data.get("client_id")
            emr_id_from_queue = queue_entry.get("emr_id")
            if emr_id_from_queue and emr_id_from_queue != client_id:
                encounter_data["emrId"] = emr_id_from_queue
    else:
        # Fallback: use queue_entry directly if no raw_payload
        encounter_data = queue_entry
        logger.warning("No raw_payload found in queue_entry, using queue_entry directly")
    
    # Validate deployment/agent version is not empty
    if not AGENT_VERSION or not AGENT_VERSION.strip():
        raise AzureAIClientError(
            f"Azure AI deployment/agent version is empty or not set. "
            f"Please set AZURE_AI_DEPLOYMENT_NAME, AZURE_AI_AGENT_VERSION, or AZURE_EXISTING_AGENT_ID. "
            f"Current value: '{AGENT_VERSION}'"
        )
    
    # Prepare request payload - send encounter data directly (not the queue_entry wrapper)
    payload = {
        "input": [
            {
                "role": "user",
                "content": json.dumps(encounter_data)
            }
        ],
        "metadata": {
            "agentVersionId": AGENT_VERSION
        }
    }
    
    # Log the payload structure (without full content to avoid huge logs)
    logger.info(f"Making Azure AI request:")
    logger.info(f"   - URL: {url}")
    logger.info(f"   - AGENT_VERSION variable: '{AGENT_VERSION}'")
    logger.info(f"   - agentVersionId in metadata: '{payload['metadata'].get('agentVersionId', 'MISSING')}'")
    
    # Log the full metadata structure
    metadata_str = json.dumps(payload.get('metadata', {}), indent=2)
    logger.info(f"   - Full metadata JSON: {metadata_str}")
    
    # Serialize the entire payload to see what's actually being sent
    payload_str = json.dumps(payload, indent=2, default=str)
    logger.debug(f"   - Full payload (first 1000 chars): {payload_str[:1000]}")
    
    # Double-check that agentVersionId is not empty in the actual payload
    agent_version_in_payload = payload["metadata"].get("agentVersionId", "")
    if not agent_version_in_payload or not str(agent_version_in_payload).strip():
        raise AzureAIClientError(
            f"CRITICAL: agentVersionId is empty in request payload! "
            f"AGENT_VERSION variable: '{AGENT_VERSION}', "
            f"payload metadata: {payload['metadata']}, "
            f"agentVersionId type: {type(agent_version_in_payload)}"
        )
    
    logger.info(f"   ✅ Verified agentVersionId is set: '{agent_version_in_payload}'")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # Retry logic with exponential backoff
    last_error = None
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECTION_TIMEOUT)) as client:
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Calling Azure AI agent (attempt {attempt + 1}/{MAX_RETRIES}) "
                    f"for encounter_id: {queue_entry.get('encounter_id', 'unknown')}"
                )
                
                # Time the actual API call
                api_call_start = time.perf_counter()
                
                # Log the exact metadata being sent (for debugging)
                if attempt == 0:  # Only log on first attempt
                    logger.info(f"📤 Sending request with metadata: {json.dumps(payload.get('metadata', {}), indent=2)}")
                    # Verify the agentVersionId one more time right before sending
                    agent_ver = payload.get('metadata', {}).get('agentVersionId', '')
                    logger.info(f"📤 agentVersionId value being sent: '{agent_ver}' (type: {type(agent_ver).__name__})")
                
                response = await client.post(url, headers=headers, json=payload)
                api_call_time = time.perf_counter() - api_call_start
                logger.info(f"⏱️  Azure AI API call (attempt {attempt + 1}): {api_call_time:.3f}s")
                
                # Handle rate limiting
                if response.status_code == 429:
                    # Check for Retry-After header from Azure AI
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = int(retry_after)
                            logger.info(f"Azure AI provided Retry-After: {wait_time} seconds")
                        except ValueError:
                            wait_time = RETRY_BACKOFF_BASE ** attempt
                    else:
                        # Exponential backoff: 2^attempt (1s, 2s, 4s, 8s...)
                        wait_time = RETRY_BACKOFF_BASE ** attempt
                    
                    logger.warning(
                        f"Rate limited (429). Waiting {wait_time} seconds before retry "
                        f"{attempt + 1}/{MAX_RETRIES}..."
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Provide helpful error message with retry_after info
                        retry_after_seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
                        raise AzureAIRateLimitError(
                            f"Rate limit exceeded after {MAX_RETRIES} retries. "
                            f"Azure AI is throttling requests. Please wait a few minutes before trying again. "
                            f"Consider reducing request frequency or checking your Azure AI quota limits.",
                            retry_after=retry_after_seconds
                        )
                
                # Handle authentication errors
                if response.status_code == 401:
                    raise AzureAIAuthenticationError(
                        "Authentication failed. Check Azure credentials."
                    )
                
                # Handle other errors
                if response.status_code >= 400:
                    error_text = response.text[:500]  # Limit error text length
                    
                    # Special handling for deployment not found errors
                    if response.status_code == 400 and "Deployment" in error_text and "not found" in error_text:
                        raise AzureAIClientError(
                            f"Azure AI deployment not found (400). "
                            f"Deployment/agent version being used: '{AGENT_VERSION}'. "
                            f"Error: {error_text}. "
                            f"Please verify that AZURE_AI_DEPLOYMENT_NAME or AZURE_AI_AGENT_VERSION "
                            f"is set to a valid deployment name in your Azure AI project."
                        )
                    
                    raise AzureAIClientError(
                        f"Azure AI returned error {response.status_code}: {error_text}"
                    )
                
                # Parse response
                try:
                    response_json = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Azure AI response as JSON. Response text (first 500 chars): {response.text[:500]}")
                    raise AzureAIResponseError(f"Azure AI returned invalid JSON: {str(e)}")
                
                # Log response structure for debugging (first attempt only)
                if attempt == 0:
                    logger.debug(f"Azure AI response structure: {json.dumps(response_json, indent=2)[:500]}")
                
                # Extract Experity mapping response
                # Pass encounter_data for backward compatibility conversion
                parse_start = time.perf_counter()
                experity_mapping = extract_experity_actions(response_json, encounter_data=encounter_data)
                parse_time = time.perf_counter() - parse_start
                logger.info(f"⏱️  Response parsing: {parse_time:.3f}s")
                
                # Log summary info
                complaints_count = len(experity_mapping.get("complaints", []))
                total_time = time.perf_counter() - start_time
                logger.info(
                    f"✅ Successfully received Experity mapping with {complaints_count} complaints "
                    f"for encounter_id: {queue_entry.get('encounter_id', 'unknown')} "
                    f"(Total time: {total_time:.3f}s)"
                )
                
                return experity_mapping
                
            except httpx.TimeoutException as e:
                last_error = AzureAITimeoutError(
                    f"Request to Azure AI agent timed out after {REQUEST_TIMEOUT} seconds"
                )
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise last_error
                
            except httpx.RequestError as e:
                last_error = AzureAIClientError(f"Network error calling Azure AI: {str(e)}")
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise last_error
                
            except (AzureAIAuthenticationError, AzureAIRateLimitError, AzureAIResponseError):
                # These errors shouldn't be retried
                raise
                
            except Exception as e:
                last_error = AzureAIClientError(f"Unexpected error: {str(e)}")
                logger.error(str(last_error))
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise last_error
    
    # If we exhausted all retries
    if last_error:
        raise last_error
    
    raise AzureAIClientError("Failed to call Azure AI agent after all retries")

