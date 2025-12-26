#!/usr/bin/env python3
"""
Azure AI Agent Client Module - Using Official Azure SDK

This module provides a clean integration with Azure AI Agent Service
using the official azure-ai-projects and azure-ai-agents SDKs.

Requirements:
    pip install azure-ai-projects azure-ai-agents azure-identity

Environment Variables:
    PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
                      Format: https://<AIFoundryResourceName>.services.ai.azure.com/api/projects/<ProjectName>
    MODEL_DEPLOYMENT_NAME: Your model deployment name (e.g., "gpt-4o", "iv-experity-mapper-gpt-4o")
    
    For Service Principal Auth (optional):
    AZURE_TENANT_ID: Azure tenant ID
    AZURE_CLIENT_ID: Azure client ID  
    AZURE_CLIENT_SECRET: Azure client secret
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
from pathlib import Path

# Azure SDK imports
try:
    from azure.ai.agents import AgentsClient
    from azure.ai.agents.aio import AgentsClient as AsyncAgentsClient
    from azure.ai.agents.models import MessageRole
    from azure.identity import (
        DefaultAzureCredential,
        ClientSecretCredential,
    )
    from azure.core.exceptions import HttpResponseError
    from azure.core.rest import HttpRequest
    AZURE_SDK_AVAILABLE = True
except ImportError as e:
    AZURE_SDK_AVAILABLE = False
    # Define dummy types for type hints when SDK is not available
    AgentsClient = Any
    AsyncAgentsClient = Any
    MessageRole = Any
    DefaultAzureCredential = Any
    ClientSecretCredential = Any
    HttpResponseError = Exception
    HttpRequest = Any
    logging.warning(f"Azure SDK not available: {e}. Install with: pip install azure-ai-agents azure-identity")

logger = logging.getLogger(__name__)

# Request timeout constant (for compatibility with old implementation)
REQUEST_TIMEOUT = int(os.getenv("AZURE_AI_REQUEST_TIMEOUT", "120"))

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

# Exception classes (matching old implementation for compatibility)
class AgentClientError(Exception):
    """Base exception for Azure AI Agent client errors."""
    pass

# Alias for backward compatibility
AzureAIClientError = AgentClientError

class AuthenticationError(AgentClientError):
    """Authentication error with Azure AI."""
    pass

# Alias for backward compatibility
AzureAIAuthenticationError = AuthenticationError

class AgentNotFoundError(AgentClientError):
    """Agent not found error."""
    pass

class RunFailedError(AgentClientError):
    """Agent run failed error."""
    pass

# Alias for backward compatibility
AzureAIRateLimitError = AgentClientError  # SDK handles rate limits internally

class TimeoutError(AgentClientError):
    """Operation timeout error."""
    pass

# Alias for backward compatibility
AzureAITimeoutError = TimeoutError
AzureAIResponseError = AgentClientError  # Response errors are AgentClientError

# =============================================================================
# Default Instructions Loading
# =============================================================================

def _load_default_instructions() -> Optional[str]:
    """
    Load default instructions from iv_to_experity_llm_prompt.txt if it exists.
    
    Returns:
        Instructions string or None if file not found
    """
    # Try to find the prompt file in the project root
    project_root = Path(__file__).parent.parent.parent
    prompt_file = project_root / "iv_to_experity_llm_prompt.txt"
    
    if prompt_file.exists():
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                instructions = f.read().strip()
            logger.info(f"Loaded default instructions from {prompt_file}")
            return instructions
        except Exception as e:
            logger.warning(f"Failed to load default instructions from {prompt_file}: {e}")
            return None
    
    # Also try in current directory
    current_dir_prompt = Path("iv_to_experity_llm_prompt.txt")
    if current_dir_prompt.exists():
        try:
            with open(current_dir_prompt, 'r', encoding='utf-8') as f:
                instructions = f.read().strip()
            logger.info(f"Loaded default instructions from {current_dir_prompt}")
            return instructions
        except Exception as e:
            logger.warning(f"Failed to load default instructions from {current_dir_prompt}: {e}")
            return None
    
    logger.debug("No default instructions file found")
    return None

# =============================================================================
# Response Processing Functions (from old implementation for compatibility)
# =============================================================================

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


def _parse_experity_json(text: str, encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Parse JSON text into Experity mapping object.
    
    Handles wrapper structures and validates format.
    
    Returns:
        Parsed Experity mapping dictionary
        
    Raises:
        AgentClientError: If JSON is invalid or format is unexpected
    """
    cleaned_text = _clean_json_text(text)
    
    try:
        experity_mapping = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON. Text preview: {cleaned_text[:500]}")
        raise AgentClientError(
            f"Response text is not valid JSON: {str(e)}. "
            f"Preview: {cleaned_text[:200]}"
        ) from e
    
    # Handle wrapper structure: {success, data: {experity_actions: {...}}} or {success, data: {experityActions: {...}}}
    if isinstance(experity_mapping, dict) and "success" in experity_mapping:
        if experity_mapping.get("success") is True and "data" in experity_mapping:
            data = experity_mapping["data"]
            # Check for both snake_case and camelCase
            if "experity_actions" in data:
                logger.info("Extracted experity_actions from wrapper structure")
                return data["experity_actions"]
            elif "experityActions" in data:
                logger.info("Extracted experityActions from wrapper structure")
                return data["experityActions"]
            else:
                logger.warning("Wrapper structure found but experity_actions/experityActions not in data, using data directly")
                return data
        elif experity_mapping.get("success") is False:
            error_info = experity_mapping.get("error", {})
            error_msg = error_info.get("message", "Unknown error") if isinstance(error_info, dict) else str(error_info)
            raise AgentClientError(f"LLM returned error structure: {error_msg}")
    
    # Handle legacy array format conversion
    if isinstance(experity_mapping, list):
        experity_mapping = _convert_legacy_array_format(experity_mapping, encounter_data)
    
    if not isinstance(experity_mapping, dict):
        raise AgentClientError(
            f"Parsed response is not a JSON object (got {type(experity_mapping).__name__}). "
            f"Expected object with emrId, vitals, complaints, etc. "
            f"Preview: {str(experity_mapping)[:200]}"
        )
    
    # Validate structure
    _validate_response_structure(experity_mapping)
    
    return experity_mapping

@dataclass
class AgentConfig:
    """Configuration for Azure AI Agent Service."""
    project_endpoint: str
    model_deployment_name: str
    
    # Optional: existing agent ID to reuse
    existing_agent_id: Optional[str] = None
    
    # Agent creation settings (used if creating new agent)
    agent_name: str = "experity-mapper-agent"
    agent_instructions: Optional[str] = None  # None = use instructions from Azure AI Foundry if agent exists, or minimal default for new agents
    
    # Run settings
    max_poll_attempts: int = 60
    poll_interval_seconds: float = 2.0
    temperature: float = 0.0  # CRITICAL: Set to 0 for deterministic output
    seed: Optional[int] = 42  # CRITICAL: Fixed seed for additional determinism (use same seed for reproducibility)
    
    # Service Principal auth (optional - defaults to DefaultAzureCredential)
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Create config from environment variables."""
        return cls(
            project_endpoint=os.environ.get(
                "PROJECT_ENDPOINT",
                os.environ.get(
                    "AZURE_AI_PROJECT_ENDPOINT",
                    os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", "")
                )
            ),
            model_deployment_name=os.environ.get(
                "MODEL_DEPLOYMENT_NAME",
                os.environ.get("AZURE_AI_DEPLOYMENT_NAME", "experitymapper")
            ),
            existing_agent_id=os.environ.get("AZURE_EXISTING_AGENT_ID"),
            tenant_id=os.environ.get("AZURE_TENANT_ID"),
            client_id=os.environ.get("AZURE_CLIENT_ID"),
            client_secret=os.environ.get("AZURE_CLIENT_SECRET"),
            temperature=float(os.environ.get("AZURE_AI_TEMPERATURE", "0.0")),  # Default to 0 for deterministic output
            seed=int(os.environ.get("AZURE_AI_SEED", "42")) if os.environ.get("AZURE_AI_SEED") else 42,  # Fixed seed for determinism
        )

class AzureAIAgentClient:
    """
    Client for interacting with Azure AI Agent Service.
    
    This client uses the official Azure SDK (azure-ai-projects, azure-ai-agents)
    and properly passes the model deployment name to avoid the 
    "Deployment '' not found" error.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize the Azure AI Agent client.
        
        Args:
            config: AgentConfig instance. If None, loads from environment variables.
        """
        if not AZURE_SDK_AVAILABLE:
            raise AgentClientError(
                "Azure SDK not installed. Run: pip install azure-ai-projects azure-ai-agents azure-identity"
            )
        
        self.config = config or AgentConfig.from_env()
        self._validate_config()
        
        self._credential = self._get_credential()
        self._client: Optional[AgentsClient] = None
        self._agent_id: Optional[str] = None
    
    def _validate_config(self) -> None:
        """Validate configuration."""
        if not self.config.project_endpoint:
            raise ValueError(
                "PROJECT_ENDPOINT environment variable is required. "
                "Format: https://<AIFoundryResourceName>.services.ai.azure.com/api/projects/<ProjectName>"
            )
        if not self.config.model_deployment_name:
            raise ValueError(
                "MODEL_DEPLOYMENT_NAME environment variable is required. "
                "This is your deployed model name in Azure AI Foundry."
            )
    
    def _get_credential(self):
        """Get Azure credential for authentication."""
        # Use Service Principal if credentials provided
        if all([self.config.tenant_id, self.config.client_id, self.config.client_secret]):
            logger.info("Using ClientSecretCredential for authentication")
            return ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
            )
        
        # Otherwise use DefaultAzureCredential (supports managed identity, CLI, etc.)
        logger.info("Using DefaultAzureCredential for authentication")
        return DefaultAzureCredential()
    
    @property
    def client(self) -> "AgentsClient":
        """Get or create the Agents client."""
        if self._client is None:
            try:
                self._client = AgentsClient(
                    credential=self._credential,
                    endpoint=self.config.project_endpoint,
                )
                logger.info(f"Connected to Azure AI Agents: {self.config.project_endpoint}")
            except Exception as e:
                logger.error(f"Failed to create Agents client: {e}")
                raise AuthenticationError(f"Failed to connect to Azure AI: {e}") from e
        return self._client
    
    def get_or_create_agent(self, force_create: bool = False) -> str:
        """
        Get existing agent or create a new one.
        
        Args:
            force_create: If True, always create a new agent
            
        Returns:
            Agent ID string
        """
        # Use existing agent if configured and not forcing creation
        if not force_create and self.config.existing_agent_id:
            agent_id = self.config.existing_agent_id
            logger.info(f"Using existing agent: {agent_id}")
            
            # Handle agent ID format like "experitymapper:4" - SDK doesn't accept colons
            # Try to find the agent by name if ID contains a colon
            if ":" in agent_id:
                agent_name = agent_id.split(":")[0]
                logger.info(f"Agent ID contains colon, searching for agent by name: {agent_name}")
                try:
                    # List agents and find by name
                    agents = self.client.list_agents()
                    for agent in agents:
                        if agent.name == agent_name:
                            self._agent_id = agent.id
                            logger.info(f"Found agent: {agent.id} ({agent.name})")
                            return self._agent_id
                    logger.info(f"Agent '{agent_name}' not found, will create new agent")
                    self.config.agent_name = agent_name
                    self.config.existing_agent_id = None
                except Exception as e:
                    logger.warning(f"Could not list agents: {e}, will create new agent")
                    self.config.agent_name = agent_name
                    self.config.existing_agent_id = None
            else:
                # Try to verify agent exists (for IDs without colons)
                try:
                    agent = self.client.get_agent(agent_id)
                    self._agent_id = agent.id
                    logger.info(f"Found existing agent: {agent.id} ({agent.name})")
                    return self._agent_id
                except Exception as e:
                    logger.warning(f"Could not verify agent exists, will try to use ID anyway: {e}")
                    self._agent_id = agent_id
                    return self._agent_id
        
        # Create new agent
        logger.info(f"Creating new agent with model: {self.config.model_deployment_name}")
        
        try:
            # Only pass instructions if explicitly provided (don't override Azure AI Foundry settings)
            create_params = {
                "model": self.config.model_deployment_name,  # CRITICAL: This must be the deployment name!
                "name": self.config.agent_name,
            }
            # Only add instructions if provided, otherwise try to load from prompt file
            if self.config.agent_instructions:
                create_params["instructions"] = self.config.agent_instructions
                logger.info("Using provided agent instructions")
            else:
                # Try to load default instructions from prompt file
                default_instructions = _load_default_instructions()
                if default_instructions:
                    create_params["instructions"] = default_instructions
                    logger.info("Using default instructions from iv_to_experity_llm_prompt.txt")
                else:
                    logger.info("No instructions provided - agent will use instructions from Azure AI Foundry configuration")
            
            agent = self.client.create_agent(**create_params)
            self._agent_id = agent.id
            logger.info(f"Created agent: {agent.id} ({agent.name})")
            return self._agent_id
            
        except HttpResponseError as e:
            logger.error(f"Failed to create agent: {e.message}")
            raise AgentClientError(f"Failed to create agent: {e.message}") from e
    
    def process_encounter(self, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an encounter through the Azure AI Agent.
        
        This is the main method that replaces the old httpx-based implementation.
        It properly uses the Azure SDK and passes the model deployment name.
        
        Args:
            encounter_data: The encounter data to process
            
        Returns:
            Experity mapping response dictionary
        """
        # Ensure we have an agent
        agent_id = self.get_or_create_agent()
        
        # Prepare the message content
        message_content = json.dumps(encounter_data, indent=2)
        
        # Create thread with initial message and run the agent
        # This method handles thread creation, message adding, running, and polling all in one
        logger.info(f"Creating thread and running agent: {agent_id}")
        
        try:
            # Create thread and run - use dict format for messages
            # CRITICAL: Set temperature=0 for deterministic output
            run_params = {
                "agent_id": agent_id,
                "thread": {
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                },
                "polling_interval": self.config.poll_interval_seconds,
            }
            
            # CRITICAL: Set temperature=0 for deterministic output
            logger.info(f"Setting temperature={self.config.temperature} for deterministic output")
            
            # Add temperature to run parameters
            # Note: Azure AI Agents SDK may support temperature as a direct parameter
            # If not supported, it may need to be configured in Azure AI Foundry model deployment settings
            if self.config.temperature is not None:
                run_params["temperature"] = self.config.temperature
            
            run = self.client.create_thread_and_process_run(**run_params)
            
            logger.info(f"Run completed with status: {run.status}")
            
            # Check run status
            if run.status == "failed":
                error_msg = getattr(run, 'last_error', None)
                if error_msg:
                    error_msg = getattr(error_msg, 'message', str(error_msg))
                else:
                    error_msg = "Unknown error"
                raise RunFailedError(f"Agent run failed: {error_msg}")
            
            if run.status == "cancelled":
                raise RunFailedError("Agent run was cancelled")
            
            if run.status == "expired":
                raise TimeoutError("Agent run expired")
            
            # Get the response from the thread using thread_id
            if not hasattr(run, 'thread_id') or not run.thread_id:
                raise AgentClientError("Run completed but no thread_id found")
            
            thread_id = run.thread_id
            logger.info(f"Fetching messages from thread: {thread_id}")
            
            try:
                # Use send_request to get messages from the thread
                messages_url = f"{self.config.project_endpoint}/threads/{thread_id}/messages?api-version=2025-11-15-preview"
                request = HttpRequest("GET", messages_url)
                
                # Send request using the client (it will handle auth automatically)
                response = self.client.send_request(request)
                response.raise_for_status()
                messages_data = response.json()
                
                # Extract messages list from response
                messages_list = None
                if isinstance(messages_data, dict):
                    messages_list = messages_data.get("data") or messages_data.get("messages") or messages_data.get("value")
                elif isinstance(messages_data, list):
                    messages_list = messages_data
                
                if not messages_list:
                    raise AgentClientError("No messages found in thread response")
                
                # Find assistant message (check from last to first)
                assistant_response = None
                for msg in reversed(messages_list):
                    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                    role_str = str(role).lower() if role else ""
                    
                    # Check if this is an assistant/agent message
                    # Use string comparison which is most reliable
                    if role_str in ["assistant", "agent"]:
                        # Extract content
                        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                        if content:
                            if isinstance(content, list) and len(content) > 0:
                                first_item = content[0]
                                if isinstance(first_item, dict) and "text" in first_item:
                                    text_obj = first_item["text"]
                                    text_content = text_obj.get("value") if isinstance(text_obj, dict) else str(text_obj)
                                else:
                                    text_content = str(first_item)
                            elif isinstance(content, str):
                                text_content = content
                            else:
                                text_content = str(content)
                            
                            if text_content:
                                assistant_response = text_content
                                break
                
                if not assistant_response:
                    raise AgentClientError("No assistant message found in thread")
                    
            except HttpResponseError as e:
                logger.error(f"HTTP error fetching messages: {e.message}")
                raise AgentClientError(f"Could not retrieve response from thread: {e.message}") from e
            except Exception as e:
                logger.error(f"Failed to fetch messages from thread: {e}")
                raise AgentClientError(f"Could not retrieve response from thread: {e}") from e
            
            if not assistant_response:
                # Log all run attributes for debugging
                logger.error(f"Run attributes: {[a for a in dir(run) if not a.startswith('_')]}")
                raise AgentClientError("No response received from agent")
            
            # Parse the JSON response with encounter data for backward compatibility
            return self._parse_response(assistant_response, encounter_data)
                
        except HttpResponseError as e:
            logger.error(f"HTTP error during agent run: {e.message}")
            raise AgentClientError(f"Agent run failed: {e.message}") from e
    
    
    def _parse_response(self, response_text: str, encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse the agent's response text into a structured dictionary.
        
        Uses the same parsing logic as the old implementation for compatibility.
        
        Args:
            response_text: Raw response text from agent
            encounter_data: Optional encounter data for backward compatibility conversion
            
        Returns:
            Experity mapping dictionary with structure:
                {emrId, vitals, guardianAssistedInterview, labOrders, icdUpdates, complaints}
        """
        return _parse_experity_json(response_text, encounter_data)
    
    def close(self) -> None:
        """Close the client and release resources."""
        if self._client:
            self._client.close()
            self._client = None
        logger.info("Azure AI Agent client closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# =============================================================================
# Async Version
# =============================================================================

class AsyncAzureAIAgentClient:
    """
    Async client for interacting with Azure AI Agent Service.
    
    Same functionality as AzureAIAgentClient but with async/await support.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        if not AZURE_SDK_AVAILABLE:
            raise AgentClientError(
                "Azure SDK not installed. Run: pip install azure-ai-projects azure-ai-agents azure-identity"
            )
        
        self.config = config or AgentConfig.from_env()
        self._validate_config()
        
        self._credential = self._get_credential()
        self._client: Optional[AsyncAgentsClient] = None
        self._agent_id: Optional[str] = None
    
    def _validate_config(self) -> None:
        if not self.config.project_endpoint:
            raise ValueError("PROJECT_ENDPOINT is required")
        if not self.config.model_deployment_name:
            raise ValueError("MODEL_DEPLOYMENT_NAME is required")
    
    def _get_credential(self):
        if all([self.config.tenant_id, self.config.client_id, self.config.client_secret]):
            return ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
            )
        return DefaultAzureCredential()
    
    @property
    def client(self) -> "AsyncAgentsClient":
        if self._client is None:
            self._client = AsyncAgentsClient(
                credential=self._credential,
                endpoint=self.config.project_endpoint,
            )
        return self._client
    
    async def get_or_create_agent(self, force_create: bool = False) -> str:
        """Get existing agent or create a new one (async)."""
        if not force_create and self.config.existing_agent_id:
            agent_id = self.config.existing_agent_id
            logger.info(f"Using existing agent: {agent_id}")
            
            # Handle agent ID format like "experitymapper:4" - SDK doesn't accept colons
            if ":" in agent_id:
                agent_name = agent_id.split(":")[0]
                logger.info(f"Agent ID contains colon, searching for agent by name: {agent_name}")
                try:
                    agents = await self.client.list_agents()
                    async for agent in agents:
                        if agent.name == agent_name:
                            self._agent_id = agent.id
                            logger.info(f"Found agent: {agent.id} ({agent.name})")
                            return self._agent_id
                    logger.info(f"Agent '{agent_name}' not found, will create new agent")
                    self.config.agent_name = agent_name
                    self.config.existing_agent_id = None
                except Exception as e:
                    logger.warning(f"Could not list agents: {e}, will create new agent")
                    self.config.agent_name = agent_name
                    self.config.existing_agent_id = None
            
            # Try to verify agent exists (for IDs without colons)
            try:
                agent = await self.client.get_agent(agent_id)
                self._agent_id = agent.id
                logger.info(f"Found existing agent: {agent.id} ({agent.name})")
                return self._agent_id
            except Exception as e:
                logger.warning(f"Could not verify agent exists, will try to use ID anyway: {e}")
            
            self._agent_id = agent_id
            return self._agent_id
        
        # Create new agent
        logger.info(f"Creating new agent with model: {self.config.model_deployment_name}")
        
        # Only pass instructions if explicitly provided (don't override Azure AI Foundry settings)
        create_params = {
            "model": self.config.model_deployment_name,
            "name": self.config.agent_name,
        }
        # Only add instructions if provided, otherwise try to load from prompt file
        if self.config.agent_instructions:
            create_params["instructions"] = self.config.agent_instructions
            logger.info("Using provided agent instructions")
        else:
            # Try to load default instructions from prompt file
            default_instructions = _load_default_instructions()
            if default_instructions:
                create_params["instructions"] = default_instructions
                logger.info("Using default instructions from iv_to_experity_llm_prompt.txt")
            else:
                logger.info("No instructions provided - agent will use instructions from Azure AI Foundry configuration")
        
        agent = await self.client.create_agent(**create_params)
        self._agent_id = agent.id
        logger.info(f"Created agent: {agent.id}")
        return self._agent_id
    
    async def process_encounter(self, encounter_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an encounter through the Azure AI Agent (async)."""
        agent_id = await self.get_or_create_agent()
        
        # Prepare the message content
        message_content = json.dumps(encounter_data, indent=2)
        
        # Create thread with initial message and run the agent
        logger.info(f"Creating thread and running agent: {agent_id}")
        
        try:
            # Create thread and run - use dict format for messages
            # CRITICAL: Set temperature=0 for deterministic output
            run_params = {
                "agent_id": agent_id,
                "thread": {
                    "messages": [
                        {
                            "role": "user",
                            "content": message_content
                        }
                    ]
                },
                "polling_interval": self.config.poll_interval_seconds,
            }
            
            # CRITICAL: Set temperature=0 for deterministic output
            # NOTE: seed parameter removed temporarily due to Azure SDK bug with aiohttp
            # The seed parameter causes: TypeError: ClientSession._request() got an unexpected keyword argument 'seed'
            # This is a known issue in azure-core 1.30.0 with aiohttp transport
            logger.info(f"Setting temperature={self.config.temperature} for deterministic output")
            
            # Add temperature to run parameters
            # Note: Azure AI Agents SDK may support temperature as a direct parameter
            # If not supported, it may need to be configured in Azure AI Foundry model deployment settings
            if self.config.temperature is not None:
                run_params["temperature"] = self.config.temperature
            # TEMPORARILY DISABLED: seed parameter causes compatibility issue with aiohttp
            # if self.config.seed is not None:
            #     run_params["seed"] = self.config.seed
            
            run = await self.client.create_thread_and_process_run(**run_params)
            
            logger.info(f"Run completed with status: {run.status}")
            
            # Check run status
            if run.status == "failed":
                error_msg = getattr(run, 'last_error', None)
                if error_msg:
                    error_msg = getattr(error_msg, 'message', str(error_msg))
                else:
                    error_msg = "Unknown error"
                raise RunFailedError(f"Agent run failed: {error_msg}")
            
            if run.status == "cancelled":
                raise RunFailedError("Agent run was cancelled")
            
            if run.status == "expired":
                raise TimeoutError("Agent run expired")
            
            # Get the response from the thread using thread_id (same approach as sync version)
            if not hasattr(run, 'thread_id') or not run.thread_id:
                raise AgentClientError("Run completed but no thread_id found")
            
            thread_id = run.thread_id
            logger.info(f"Fetching messages from thread: {thread_id}")
            
            try:
                # Use send_request to get messages from the thread
                messages_url = f"{self.config.project_endpoint}/threads/{thread_id}/messages?api-version=2025-11-15-preview"
                request = HttpRequest("GET", messages_url)
                
                # Send request using the client (it will handle auth automatically)
                response = await self.client.send_request(request)
                response.raise_for_status()
                messages_data = response.json()
                
                # Extract messages list from response
                messages_list = None
                if isinstance(messages_data, dict):
                    messages_list = messages_data.get("data") or messages_data.get("messages") or messages_data.get("value")
                elif isinstance(messages_data, list):
                    messages_list = messages_data
                
                if not messages_list:
                    raise AgentClientError("No messages found in thread response")
                
                # Find assistant message (check from last to first)
                assistant_response = None
                for msg in reversed(messages_list):
                    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                    role_str = str(role).lower() if role else ""
                    
                    # Check if this is an assistant/agent message
                    # Use string comparison which is most reliable
                    if role_str in ["assistant", "agent"]:
                        # Extract content
                        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                        if content:
                            if isinstance(content, list) and len(content) > 0:
                                first_item = content[0]
                                if isinstance(first_item, dict) and "text" in first_item:
                                    text_obj = first_item["text"]
                                    text_content = text_obj.get("value") if isinstance(text_obj, dict) else str(text_obj)
                                else:
                                    text_content = str(first_item)
                            elif isinstance(content, str):
                                text_content = content
                            else:
                                text_content = str(content)
                            
                            if text_content:
                                assistant_response = text_content
                                break
                
                if not assistant_response:
                    raise AgentClientError("No assistant message found in thread")
                    
            except HttpResponseError as e:
                logger.error(f"HTTP error fetching messages: {e.message}")
                raise AgentClientError(f"Could not retrieve response from thread: {e.message}") from e
            except Exception as e:
                logger.error(f"Failed to fetch messages from thread: {e}")
                raise AgentClientError(f"Could not retrieve response from thread: {e}") from e
            
            if not assistant_response:
                raise AgentClientError("No response received from agent")
            
            # Parse response with encounter data for backward compatibility
            return self._parse_response(assistant_response, encounter_data)
                
        except HttpResponseError as e:
            logger.error(f"HTTP error during agent run: {e.message}")
            raise AgentClientError(f"Agent run failed: {e.message}") from e
    
    def _parse_response(self, response_text: str, encounter_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse response text to dict (async version).
        
        Uses the same parsing logic as the old implementation for compatibility.
        """
        return _parse_experity_json(response_text, encounter_data)
    
    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# =============================================================================
# Convenience function for backward compatibility
# =============================================================================

async def call_azure_ai_agent(queue_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a queue entry through the Azure AI Agent.
    
    This is a drop-in replacement for the old httpx-based implementation.
    
    Args:
        queue_entry: Queue entry containing encounter data
        
    Returns:
        Experity mapping response
        
    Raises:
        AgentClientError: If SDK is not available or client initialization fails
        Various Azure AI exceptions: If agent processing fails
    """
    if not AZURE_SDK_AVAILABLE:
        raise AgentClientError(
            "Azure SDK not installed. Run: pip install azure-ai-projects azure-ai-agents azure-identity"
        )
    
    # Extract encounter data
    try:
        # Store original emr_id from queue_entry for post-processing
        original_emr_id = queue_entry.get("emr_id")
        
        if "raw_payload" in queue_entry and queue_entry["raw_payload"]:
            encounter_data = dict(queue_entry["raw_payload"])
            if "encounterId" not in encounter_data and "encounter_id" in queue_entry:
                encounter_data["encounterId"] = queue_entry["encounter_id"]
            # Always set emrId from queue_entry.emr_id if available (overwrites any existing emrId)
            if "emr_id" in queue_entry and queue_entry["emr_id"]:
                encounter_data["emrId"] = queue_entry["emr_id"]
                logger.info(f"Set emrId from queue_entry: {queue_entry['emr_id']}")
        else:
            encounter_data = queue_entry
            # Ensure emrId is set from queue_entry if available
            if "emr_id" in queue_entry and queue_entry["emr_id"]:
                encounter_data["emrId"] = queue_entry["emr_id"]
                logger.info(f"Set emrId from queue_entry: {queue_entry['emr_id']}")
        
        encounter_id = encounter_data.get("id") or encounter_data.get("encounterId") or queue_entry.get("encounter_id", "unknown")
        logger.info(f"Processing encounter {encounter_id} through Azure AI Agent")
        
    except Exception as e:
        logger.error(f"Error extracting encounter data: {e}")
        raise AgentClientError(f"Invalid queue_entry format: {e}") from e
    
    try:
        logger.info("Initializing Azure AI Agent client...")
        async with AsyncAzureAIAgentClient() as client:
            logger.info("Azure AI Agent client initialized successfully")
            logger.info(f"Calling process_encounter for encounter: {encounter_id}")
            result = await client.process_encounter(encounter_data)
            logger.info(f"Successfully processed encounter {encounter_id}")
            
            # Post-process: Ensure emrId is correct (fix if LLM used clientId instead)
            # Handle different response structures: direct experityActions, wrapped in experityActions, or wrapped in data.experityActions
            if original_emr_id:
                actions = None
                # Try to find experityActions in various structures
                if isinstance(result, dict):
                    # Case 1: Direct experityActions object
                    if "vitals" in result or "complaints" in result:
                        actions = result
                    # Case 2: Wrapped in experityActions
                    elif "experityActions" in result:
                        actions = result["experityActions"]
                    # Case 3: Wrapped in data.experityActions
                    elif "data" in result and isinstance(result["data"], dict):
                        if "experityActions" in result["data"]:
                            actions = result["data"]["experityActions"]
                        elif "vitals" in result["data"] or "complaints" in result["data"]:
                            actions = result["data"]
                
                if actions and isinstance(actions, dict):
                    current_emr_id = actions.get("emrId")
                    # If emrId matches clientId, it's likely wrong - replace with original
                    client_id = encounter_data.get("clientId")
                    if current_emr_id == client_id and current_emr_id != original_emr_id:
                        logger.warning(f"LLM used clientId ({client_id}) as emrId. Correcting to {original_emr_id}")
                        actions["emrId"] = original_emr_id
                    elif current_emr_id != original_emr_id:
                        logger.info(f"Correcting emrId from {current_emr_id} to {original_emr_id}")
                        actions["emrId"] = original_emr_id
                    else:
                        logger.info(f"emrId is correct: {original_emr_id}")
                elif original_emr_id:
                    logger.warning(f"Could not find experityActions structure to fix emrId. Original emrId: {original_emr_id}")
            
            return result
    except AgentClientError:
        # Re-raise client errors as-is
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Error in call_azure_ai_agent: {error_type}: {error_msg}")
        logger.error(f"Encounter ID: {encounter_id}", exc_info=True)
        # Wrap unexpected errors in AgentClientError
        raise AgentClientError(f"Azure AI agent processing failed: {error_type}: {error_msg}") from e

