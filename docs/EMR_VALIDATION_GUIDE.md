# EMR Image Validation Guide

## Overview

The EMR Image Validation feature provides a simple, single-page web application for validating EMR (Electronic Medical Record) screenshots against JSON responses using Azure OpenAI GPT-4.1 vision capabilities.

## Features

- **Image Upload**: Upload EMR screenshots for validation
- **JSON Validation**: Paste JSON responses to compare against screenshots
- **Automated Validation**: Uses Azure AI ImageMapper agent to compare fields
- **Detailed Results**: Shows field-by-field comparison with match/mismatch indicators
- **Clean UI**: Simple, modern interface with no configuration required

## Access

**Production URL**: `https://app-97926.on-aptible.com/emr/validation`

For local development: `http://localhost:8000/emr/validation`

## Usage

1. **Upload Screenshot**: Click "Choose File" and select your EMR screenshot image
2. **Paste JSON Response**: Paste the JSON response that needs to be validated
3. **Click Validate**: The application will compare the JSON against the screenshot
4. **Review Results**: See detailed validation results with match/mismatch indicators

## Validated Fields

The validation checks the following 5 fields:

1. **Main Problem** - Which radio button is selected
   - JSON path: `complaints[].mainProblem`

2. **Body Area** - Which checkbox is checked + shaded area on body diagram
   - Also checks if "Generalized/Whole Body" is checked
   - JSON path: `complaints[].bodyAreaKey`

3. **Notes** - Text in Notes box
   - JSON path: `complaints[].notesFreeText`

4. **Quality** - Which quality checkboxes are checked
   - JSON path: `complaints[].notesPayload.quality`

5. **Severity** - Which number 0-10 is selected
   - JSON path: `complaints[].notesPayload.severity`

## Response Format

The validation returns a JSON object with the following structure:

```json
{
  "overall_status": "PASS / PARTIAL / FAIL",
  "results": {
    "main_problem": {
      "json": "",
      "screenshot": "",
      "match": true/false
    },
    "body_area": {
      "json": "",
      "screenshot": "",
      "generalized_whole_body": true/false,
      "match": true/false
    },
    "notes": {
      "json": "",
      "screenshot": "",
      "match": true/false
    },
    "quality": {
      "json": [],
      "screenshot": [],
      "match": true/false
    },
    "severity": {
      "json": null,
      "screenshot": null,
      "match": true/false
    }
  },
  "mismatches": []
}
```

## Configuration

All configuration is hardcoded (no environment variables needed):

- **Project Endpoint**: `https://iv-catalyze-openai.services.ai.azure.com/api/projects/IV-Catalyze-OpenAI-project`
- **Agent Name**: `ImageMapper`
- **Authentication**: Uses `DefaultAzureCredential` (Azure CLI, Managed Identity, etc.)

## API Endpoint

### POST `/emr/validate`

Validates an EMR screenshot against a JSON response.

**Request:**
- Content-Type: `multipart/form-data`
- Parameters:
  - `image`: Image file (required)
  - `json_response`: JSON string (required)

**Response:**
- Status: 200 OK
- Body: Validation results JSON (see Response Format above)

**Error Responses:**
- 400: Invalid JSON format
- 404: Agent not found
- 422: Missing required fields
- 500: Server error

## Technical Details

### Backend Implementation

- Uses `AgentsClient` from `azure.ai.agents` SDK
- Follows the same pattern as `azure_ai_agent_client.py`
- Uses thread-based agent execution with `create_thread_and_process_run`
- Retrieves messages using `send_request` pattern

### Frontend Implementation

- Single-page HTML application (no frameworks)
- Client-side image to base64 conversion
- FormData submission to backend
- Dynamic results display with match/mismatch indicators

### Agent Configuration

The ImageMapper agent is configured with:
- **Model**: gpt-4.1
- **Temperature**: 1
- **Instructions**: Pre-configured validation prompt
- **Tools**: None (prompt-based agent)

## Example JSON Input

```json
{
  "complaints": [{
    "mainProblem": "Cough",
    "bodyAreaKey": "chest",
    "notesFreeText": "Patient has persistent cough",
    "notesPayload": {
      "quality": ["dry"],
      "severity": 5
    }
  }]
}
```

## Example Response

```json
{
  "overall_status": "PASS",
  "results": {
    "main_problem": {
      "json": "Cough",
      "screenshot": "Cough",
      "match": true
    },
    "body_area": {
      "json": "chest",
      "screenshot": "chest",
      "generalized_whole_body": false,
      "match": true
    },
    "notes": {
      "json": "Patient has persistent cough",
      "screenshot": "Patient has persistent cough",
      "match": true
    },
    "quality": {
      "json": ["dry"],
      "screenshot": ["dry"],
      "match": true
    },
    "severity": {
      "json": 5,
      "screenshot": 5,
      "match": true
    }
  },
  "mismatches": []
}
```

## Testing

The feature has been thoroughly tested:

- ✅ Valid matching data → PASS
- ✅ Mismatched data → FAIL with detailed mismatches
- ✅ Invalid JSON → 400 error
- ✅ Missing image → 422 error
- ✅ Frontend form validation
- ✅ Results display

## Files

- **Template**: `app/templates/emr_validation.html`
- **Route**: `app/api/routes.py` (routes: `/emr/validation`, `/emr/validate`)
- **Agent**: Azure AI ImageMapper agent (created automatically if not exists)

## Dependencies

- `azure-ai-agents` - Azure AI Agents SDK
- `azure-identity` - Azure authentication
- FastAPI - Web framework
- Jinja2 - Template engine

## Troubleshooting

### Agent Not Found (404)
- Ensure Azure credentials are configured
- Verify agent "ImageMapper" exists in the project
- Check Azure CLI login: `az account show`

### Authentication Errors (401)
- Configure Azure credentials:
  - Azure CLI: `az login`
  - Or set environment variables for service principal
  - Or use managed identity in Azure

### Image Upload Issues
- Ensure image format is supported (PNG, JPEG, etc.)
- Check file size (should be reasonable for API limits)
- Verify image is readable

## Support

For issues or questions, check:
- Server logs for detailed error messages
- Browser console for frontend errors
- Azure AI Studio for agent status

