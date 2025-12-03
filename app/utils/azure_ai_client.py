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

# Azure AI Configuration from environment variables
PROJECT_ENDPOINT = os.getenv(
    "AZURE_AI_PROJECT_ENDPOINT",
    "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"
)
AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "IV-Experity-Mapper-Agent")
AGENT_VERSION = os.getenv("AZURE_AI_AGENT_VERSION", "IV-Experity-Mapper-Agent:8")
API_VERSION = os.getenv("AZURE_AI_API_VERSION", "2025-11-15-preview")

# Timeout configuration
REQUEST_TIMEOUT = int(os.getenv("AZURE_AI_REQUEST_TIMEOUT", "60"))
CONNECTION_TIMEOUT = int(os.getenv("AZURE_AI_CONNECTION_TIMEOUT", "10"))

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
    pass


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


def extract_experity_actions(response_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract Experity mapping response from Azure AI response format.
    
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
        
        # Validate it's a dictionary
        if not isinstance(experity_mapping, dict):
            raise AzureAIResponseError("Parsed response is not a JSON object")
        
        # Basic validation - check for expected top-level fields
        expected_fields = ["vitals", "complaints"]
        for field in expected_fields:
            if field not in experity_mapping:
                logger.warning(f"Response missing expected field: {field}")
        
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
    if not HTTPX_AVAILABLE:
        raise AzureAIClientError(
            "httpx package not installed. Install it with: pip install httpx"
        )
    
    # Build URL
    url = f"{PROJECT_ENDPOINT}/applications/{AGENT_NAME}/protocols/openai/responses?api-version={API_VERSION}"
    
    # Get Azure token
    try:
        token = get_azure_token()
    except AzureAIAuthenticationError:
        raise
    
    # Extract raw_payload from queue_entry - the LLM prompt expects encounter data directly
    # If queue_entry has raw_payload, use that; otherwise use queue_entry itself
    if "raw_payload" in queue_entry and queue_entry["raw_payload"]:
        # Create a copy to avoid modifying the original
        encounter_data = dict(queue_entry["raw_payload"])
        # Also include encounter_id and emr_id from queue_entry if not in raw_payload
        if "encounterId" not in encounter_data and "encounter_id" in queue_entry:
            encounter_data["encounterId"] = queue_entry["encounter_id"]
        if "emrId" not in encounter_data and "emr_id" in queue_entry:
            encounter_data["emrId"] = queue_entry["emr_id"]
    else:
        # Fallback: use queue_entry directly if no raw_payload
        encounter_data = queue_entry
        logger.warning("No raw_payload found in queue_entry, using queue_entry directly")
    
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
                
                response = await client.post(url, headers=headers, json=payload)
                
                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Rate limited (429). Waiting {wait_time} seconds before retry "
                        f"{attempt + 1}/{MAX_RETRIES}..."
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise AzureAIRateLimitError(
                            f"Rate limit exceeded after {MAX_RETRIES} retries"
                        )
                
                # Handle authentication errors
                if response.status_code == 401:
                    raise AzureAIAuthenticationError(
                        "Authentication failed. Check Azure credentials."
                    )
                
                # Handle other errors
                if response.status_code >= 400:
                    error_text = response.text[:500]  # Limit error text length
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
                experity_mapping = extract_experity_actions(response_json)
                
                # Log summary info
                complaints_count = len(experity_mapping.get("complaints", []))
                logger.info(
                    f"Successfully received Experity mapping with {complaints_count} complaints "
                    f"for encounter_id: {queue_entry.get('encounter_id', 'unknown')}"
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

