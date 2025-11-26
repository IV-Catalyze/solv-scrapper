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
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
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
    Get Azure AD token using Service Principal credentials if available,
    otherwise falls back to DefaultAzureCredential.
    
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
        # Prefer Service Principal credentials if available (for production)
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        
        if client_id and client_secret and tenant_id:
            logger.info("Using Service Principal credentials for Azure authentication")
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        else:
            logger.info("Using DefaultAzureCredential for Azure authentication")
            credential = DefaultAzureCredential()
        
        token = credential.get_token(AZURE_SCOPE)
        logger.debug(f"Successfully obtained Azure token (expires: {token.expires_on})")
        return token.token
    except Exception as e:
        logger.error(f"Failed to get Azure token: {str(e)}")
        raise AzureAIAuthenticationError(f"Failed to authenticate with Azure: {str(e)}") from e


def extract_experity_actions(response_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract Experity actions from Azure AI response format.
    
    The Azure AI response has this structure:
    {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "[{...}, {...}]"  # JSON string
                    }
                ]
            }
        ]
    }
    
    Args:
        response_json: Full Azure AI response JSON
        
    Returns:
        List of Experity action dictionaries
        
    Raises:
        AzureAIResponseError: If response format is invalid or JSON parsing fails
    """
    try:
        output_items = response_json.get("output", [])
        if not output_items:
            raise AzureAIResponseError("Response contains no output items")
        
        # Extract text from output
        output_text = ""
        for item in output_items:
            if item.get("type") == "message":
                content_blocks = item.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "output_text":
                        output_text += block.get("text", "")
        
        if not output_text:
            logger.error(
                f"No output_text found in Azure AI response. "
                f"Response structure: {json.dumps(response_json, indent=2)[:1000]}"
            )
            raise AzureAIResponseError(
                "No output_text found in response. Azure AI may have returned an unexpected format."
            )
        
        # Strip markdown code blocks if present (Azure AI sometimes wraps JSON in ```json ... ```)
        # Also handle cases where there might be extra text before/after
        import re
        
        output_text_clean = output_text.strip()
        
        # Try regex extraction first (more reliable for markdown code blocks)
        markdown_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(markdown_pattern, output_text_clean, re.DOTALL)
        if match:
            output_text_clean = match.group(1).strip()
            logger.debug("Extracted JSON from markdown code block using regex")
        else:
            # Fallback to simple string operations
            if output_text_clean.startswith("```json"):
                output_text_clean = output_text_clean[7:].lstrip()
            elif output_text_clean.startswith("```"):
                output_text_clean = output_text_clean[3:].lstrip()
            
            if output_text_clean.endswith("```"):
                output_text_clean = output_text_clean[:-3].rstrip()
        
        # Sometimes there's extra content after the JSON - find the first valid JSON array/dict
        # by looking for the opening bracket/brace and finding its matching close
        output_text_clean = output_text_clean.strip()
        first_bracket = output_text_clean.find('[')
        first_brace = output_text_clean.find('{')
        
        # Use the first opening bracket or brace, whichever comes first (or -1 if neither)
        start_idx = min(first_bracket, first_brace) if first_bracket >= 0 and first_brace >= 0 else (first_bracket if first_bracket >= 0 else first_brace)
        
        if start_idx > 0:
            # Found JSON starting after some prefix text
            logger.debug(f"JSON starts at index {start_idx}, stripping prefix")
            output_text_clean = output_text_clean[start_idx:]
        
        # Find the matching closing bracket/brace and strip anything after it
        # Count brackets/braces to find where the JSON ends (ignoring brackets inside strings)
        if output_text_clean.startswith('['):
            bracket_count = 0
            in_string = False
            escape_next = False
            
            for i, char in enumerate(output_text_clean):
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            # Found matching closing bracket
                            output_text_clean = output_text_clean[:i+1]
                            break
        elif output_text_clean.startswith('{'):
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i, char in enumerate(output_text_clean):
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Found matching closing brace
                            output_text_clean = output_text_clean[:i+1]
                            break
        
        output_text_clean = output_text_clean.strip()
        
        # Parse JSON string to list of actions
        # Try to parse - if it fails, attempt to extract valid JSON by trying different lengths
        experity_actions = None
        last_error = None
        
        try:
            experity_actions = json.loads(output_text_clean)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                f"Initial JSON parse failed: {str(e)}. "
                f"Attempting to extract valid JSON from response..."
            )
            
            # Try to find valid JSON by attempting to parse progressively shorter substrings
            # This handles cases where there's trailing content or incomplete extraction
            for truncate_pos in range(len(output_text_clean), max(100, len(output_text_clean) - 500), -50):
                try:
                    test_json = output_text_clean[:truncate_pos].rstrip().rstrip(',')
                    experity_actions = json.loads(test_json)
                    logger.info(f"Successfully parsed JSON after truncating to {truncate_pos} characters")
                    break
                except json.JSONDecodeError:
                    continue
            
            # If still failed, try to find JSON array/object boundaries more carefully
            if experity_actions is None:
                # Try to parse from different starting positions
                for start_pos in range(min(50, len(output_text_clean))):
                    if output_text_clean[start_pos:start_pos+1] in ['[', '{']:
                        try:
                            test_json = output_text_clean[start_pos:]
                            experity_actions = json.loads(test_json)
                            logger.info(f"Successfully parsed JSON starting from position {start_pos}")
                            break
                        except json.JSONDecodeError:
                            continue
        
        if experity_actions is None:
            # Show error context for debugging
            error_pos = getattr(last_error, 'pos', None) if last_error else 0
            start_pos = max(0, error_pos - 200)
            end_pos = min(len(output_text_clean), error_pos + 200)
            error_context = output_text_clean[start_pos:end_pos] if output_text_clean else "N/A"
            logger.error(
                f"Failed to parse JSON from output text after all attempts. "
                f"Output text length: {len(output_text_clean)}. "
                f"Error position: {error_pos}. "
                f"Error: {str(last_error) if last_error else 'Unknown'}. "
                f"First 500 chars: {output_text_clean[:500]}"
            )
            raise AzureAIResponseError(
                f"Response text is not valid JSON: {str(last_error) if last_error else 'Failed to parse'}"
            ) from last_error
        
        # Validate it's a list
        if not isinstance(experity_actions, list):
            raise AzureAIResponseError("Parsed response is not a list of actions")
        
        # Validate each action has required fields
        required_fields = ["template", "bodyAreaKey", "mainProblem"]
        for idx, action in enumerate(experity_actions):
            if not isinstance(action, dict):
                raise AzureAIResponseError(f"Action at index {idx} is not a dictionary")
            for field in required_fields:
                if field not in action:
                    logger.warning(f"Action at index {idx} missing field: {field}")
        
        return experity_actions
        
    except AzureAIResponseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error extracting Experity actions: {str(e)}")
        raise AzureAIResponseError(f"Failed to extract Experity actions: {str(e)}") from e


async def call_azure_ai_agent(queue_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Call Azure AI Experity Mapper Agent with a queue entry.
    
    Args:
        queue_entry: Queue entry dictionary to send to the agent
        
    Returns:
        List of Experity action dictionaries
        
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
    
    # Prepare request payload
    payload = {
        "input": [
            {
                "role": "user",
                "content": json.dumps(queue_entry)
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
                    logger.error(
                        f"Azure AI returned error {response.status_code}. "
                        f"Response headers: {dict(response.headers)}. "
                        f"Response text: {error_text}"
                    )
                    raise AzureAIClientError(
                        f"Azure AI returned error {response.status_code}: {error_text}"
                    )
                
                # Check response content
                response_text = response.text
                logger.debug(f"Azure AI response status: {response.status_code}")
                logger.debug(f"Azure AI response length: {len(response_text)} chars")
                logger.debug(f"Azure AI response preview: {response_text[:200]}")
                
                if not response_text:
                    raise AzureAIClientError(
                        "Azure AI returned empty response body"
                    )
                
                # Parse response
                try:
                    response_json = response.json()
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(
                        f"Failed to parse Azure AI response as JSON. "
                        f"Status: {response.status_code}. "
                        f"Response text (first 500 chars): {response_text[:500]}"
                    )
                    raise AzureAIClientError(
                        f"Azure AI returned non-JSON response: {str(e)}. "
                        f"Response preview: {response_text[:200]}"
                    )
                
                # Extract Experity actions
                experity_actions = extract_experity_actions(response_json)
                
                logger.info(
                    f"Successfully received {len(experity_actions)} Experity actions "
                    f"for encounter_id: {queue_entry.get('encounter_id', 'unknown')}"
                )
                
                return experity_actions
                
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

