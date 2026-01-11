"""
Validation routes for EMR image validation.

This module contains routes for validating EMR images against JSON responses.
"""

import logging
import json
import base64
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form

from app.api.routes.dependencies import (
    logger,
    require_auth,
)

router = APIRouter()


@router.post(
    "/emr/validate",

    summary="Validate EMR Image with JSON",

    response_model=Dict[str, Any],

    include_in_schema=False,

)

async def validate_emr_image(

    request: Request,

    image: UploadFile = File(...),

    json_response: str = Form(...),

    current_user: dict = Depends(require_auth),

):

    """

    Validate EMR screenshot against JSON response using Azure AI ImageMapper agent.

    

    This endpoint:

    - Accepts an image file and JSON response

    - Calls the ImageMapper Azure AI agent

    - Returns validation results

    

    Requires authentication - users must be logged in to use this endpoint.

    """

    try:

        # Import Azure AI Agents client (same as azure_ai_agent_client.py)

        try:

            from azure.identity import DefaultAzureCredential

            from azure.ai.agents import AgentsClient

            from azure.core.rest import HttpRequest

            from azure.core.exceptions import HttpResponseError

        except ImportError:

            raise HTTPException(

                status_code=500,

                detail="Azure AI Agents SDK not installed. Install with: pip install azure-ai-agents azure-identity"

            )

        

        # Hardcoded configuration (same pattern as azure_ai_agent_client.py)

        project_endpoint = "https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project"

        agent_name = "ImageMapper"

        

        # Read image file

        image_bytes = await image.read()

        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        image_mime_type = image.content_type or "image/jpeg"

        

        # Parse JSON response

        try:

            json_data = json.loads(json_response)

        except json.JSONDecodeError as e:

            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

        

        # Initialize Azure AI Agents client (same pattern as azure_ai_agent_client.py)

        credential = DefaultAzureCredential()

        agents_client = AgentsClient(

            credential=credential,

            endpoint=project_endpoint,

        )

        

        # Get the agent by name (same pattern as azure_ai_agent_client.py)

        try:

            # List agents and find by name

            agents = agents_client.list_agents()

            agent = None

            for a in agents:

                if a.name == agent_name:

                    agent = a

                    break

            

            if not agent:

                raise HTTPException(

                    status_code=404,

                    detail=f"Agent '{agent_name}' not found"

                )

            

            agent_id = agent.id

            logger.info(f"Found agent: {agent_id} ({agent.name})")

        except HttpResponseError as e:

            raise HTTPException(

                status_code=404,

                detail=f"Error retrieving agent '{agent_name}': {str(e)}"

            )

        

        # Prepare content with image and JSON

        # The agent already has the validation instructions with [PASTE YOUR JSON HERE] placeholder

        json_string = json.dumps(json_data, indent=2)

        

        # Create message content with image and JSON (same pattern as azure_ai_agent_client.py)

        # Format matches the agent's instruction: "## JSON TO VALIDATE: [PASTE JSON HERE]"

        # For vision models, content should be a list with text and image_url items

        message_content = [

            {

                "type": "text",

                "text": f"## JSON TO VALIDATE:\n{json_string}\n\n---\n\nAnalyze the screenshot and return the validation report."

            },

            {

                "type": "image_url",

                "image_url": {

                    "url": f"data:{image_mime_type};base64,{image_base64}"

                }

            }

        ]

        

        # Call the agent using thread-based approach (same as azure_ai_agent_client.py)

        try:

            # Create thread and run the agent (same pattern as azure_ai_agent_client.py)

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

                "polling_interval": 2.0,

            }

            

            logger.info(f"Creating thread and running agent: {agent_id}")

            run = agents_client.create_thread_and_process_run(**run_params)

            

            logger.info(f"Run completed with status: {run.status}")

            

            # Check run status

            if run.status == "failed":

                error_msg = getattr(run, 'last_error', None)

                if error_msg:

                    error_msg = getattr(error_msg, 'message', str(error_msg))

                else:

                    error_msg = "Unknown error"

                raise HTTPException(

                    status_code=500,

                    detail=f"Agent run failed: {error_msg}"

                )

            

            if run.status == "cancelled":

                raise HTTPException(status_code=500, detail="Agent run was cancelled")

            

            if run.status == "expired":

                raise HTTPException(status_code=500, detail="Agent run expired")

            

            # Get the response from the thread (same pattern as azure_ai_agent_client.py)

            if not hasattr(run, 'thread_id') or not run.thread_id:

                raise HTTPException(status_code=500, detail="Run completed but no thread_id found")

            

            thread_id = run.thread_id

            logger.info(f"Fetching messages from thread: {thread_id}")

            

            # Use send_request to get messages from the thread (same as azure_ai_agent_client.py)

            messages_url = f"{project_endpoint}/threads/{thread_id}/messages?api-version=2025-11-15-preview"

            request = HttpRequest("GET", messages_url)

            

            response = agents_client.send_request(request)

            response.raise_for_status()

            messages_data = response.json()

            

            # Extract messages list from response (same pattern as azure_ai_agent_client.py)

            messages_list = None

            if isinstance(messages_data, dict):

                messages_list = messages_data.get("data") or messages_data.get("messages") or messages_data.get("value")

            elif isinstance(messages_data, list):

                messages_list = messages_data

            

            if not messages_list:

                raise HTTPException(status_code=500, detail="No messages found in thread response")

            

            # Find assistant message (same pattern as azure_ai_agent_client.py)

            response_text = None

            for msg in reversed(messages_list):

                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)

                role_str = str(role).lower() if role else ""

                

                if role_str in ["assistant", "agent"]:

                    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)

                    if content:

                        if isinstance(content, list) and len(content) > 0:

                            first_item = content[0]

                            if isinstance(first_item, dict) and "text" in first_item:

                                text_obj = first_item["text"]

                                response_text = text_obj.get("value") if isinstance(text_obj, dict) else str(text_obj)

                            else:

                                response_text = str(first_item)

                        elif isinstance(content, str):

                            response_text = content

                        else:

                            response_text = str(content)

                        

                        if response_text:

                            break

            

            if not response_text:

                raise HTTPException(status_code=500, detail="No assistant message found in thread")

            

            # Parse JSON response (handle markdown code blocks and extra text)

            try:

                # Remove markdown code blocks if present (same pattern as azure_ai_agent_client.py)

                cleaned_text = response_text.strip()

                if cleaned_text.startswith('```json'):

                    cleaned_text = cleaned_text[7:]

                elif cleaned_text.startswith('```'):

                    cleaned_text = cleaned_text[3:]

                if cleaned_text.endswith('```'):

                    cleaned_text = cleaned_text[:-3]

                cleaned_text = cleaned_text.strip()

                

                # Try to extract JSON if there's extra text before or after

                # Look for the first { and try to find the matching closing }

                json_start = cleaned_text.find('{')

                if json_start >= 0:

                    # Find the matching closing brace

                    brace_count = 0

                    json_end = -1

                    for i in range(json_start, len(cleaned_text)):

                        if cleaned_text[i] == '{':

                            brace_count += 1

                        elif cleaned_text[i] == '}':

                            brace_count -= 1

                            if brace_count == 0:

                                json_end = i + 1

                                break

                    

                    if json_end > json_start:

                        # Extract just the JSON portion

                        cleaned_text = cleaned_text[json_start:json_end]

                

                validation_result = json.loads(cleaned_text)

                

                # Handle new response format with "extraction" and "validation" sections

                # If agent returns new format, extract just the validation part

                if isinstance(validation_result, dict) and "validation" in validation_result:

                    # Use the validation section, but also include extraction for debugging

                    validation_result = {

                        **validation_result.get("validation", {}),

                        "extraction": validation_result.get("extraction", {})  # Include for debugging

                    }

                # If agent returns old format directly, use as-is

                elif isinstance(validation_result, dict) and "overall_status" in validation_result:

                    # Already in correct format

                    pass

                else:

                    # Unexpected format, wrap it

                    validation_result = {

                        "overall_status": "ERROR",

                        "error": "Unexpected response format",

                        "raw_response": validation_result

                    }

                    

            except json.JSONDecodeError as e:

                # If parsing failed, try to extract JSON from the response more aggressively

                try:

                    # Try to find JSON object in the response

                    import re

                    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned_text, re.DOTALL)

                    if json_match:

                        json_str = json_match.group(0)

                        validation_result = json.loads(json_str)

                        logger.warning(f"Successfully extracted JSON from response with extra text")

                    else:

                        raise json.JSONDecodeError("No JSON object found", cleaned_text, 0)

                except (json.JSONDecodeError, Exception) as e2:

                    raise HTTPException(

                        status_code=500,

                        detail=f"Failed to parse validation response as JSON: {str(e)}. Raw response preview: {response_text[:500]}"

                    )

                # If not JSON, return as text

                validation_result = {

                    "overall_status": "ERROR",

                    "error": f"Failed to parse response as JSON: {str(e)}",

                    "raw_response": response_text[:500]  # Limit length

                }

            

            return validation_result

            

        except HttpResponseError as e:

            logger.error(f"HTTP error during agent run: {e.message}")

            raise HTTPException(

                status_code=500,

                detail=f"Error calling Azure AI agent: {e.message}"

            )

        except Exception as e:

            logger.error(f"Error calling Azure AI agent: {e}", exc_info=True)

            raise HTTPException(

                status_code=500,

                detail=f"Error calling Azure AI agent: {str(e)}"

            )

            

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Unexpected error in validate_emr_image: {e}", exc_info=True)

        raise HTTPException(

            status_code=500,

            detail=f"Internal server error: {str(e)}"

        )


