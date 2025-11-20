#!/usr/bin/env python3
"""
Utility functions for parsing and normalizing encounter data.
"""

from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple


def parse_encounter_payload(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse raw encounter JSON and extract fields into a simplified parsed structure.
    
    This function handles both camelCase and snake_case field names and creates
    a standardized parsed_payload structure matching encounter_structure_example.json.
    
    Args:
        raw_json: Raw JSON payload from the POST request (dict)
        
    Returns:
        Dictionary with standardized field names matching the parsed_payload structure:
        {
            "id": str,
            "encounter_id": str,
            "client_id": str,
            "patient_id": str,
            "emr_id": Optional[str],
            "trauma_type": Optional[str],
            "chief_complaints": List[Dict],
            "status": Optional[str],
            "created_by": Optional[str],
            "started_at": Optional[str],
            "created_at": Optional[str],
            "updated_at": Optional[str]
        }
    """
    # Helper function to get value from either camelCase or snake_case
    def get_field(key_snake: str, key_camel: Optional[str] = None) -> Optional[Any]:
        """Get field value supporting both naming conventions."""
        if key_camel is None:
            # Auto-generate camelCase from snake_case
            parts = key_snake.split('_')
            key_camel = parts[0] + ''.join(word.capitalize() for word in parts[1:])
        
        # Try snake_case first, then camelCase
        return raw_json.get(key_snake) or raw_json.get(key_camel)
    
    # Extract id and encounter_id
    # id can come from 'id' or 'encounter_id'
    encounter_id_value = (
        get_field('encounter_id', 'encounterId') or 
        get_field('id')
    )
    
    id_value = (
        get_field('id') or 
        encounter_id_value
    )
    
    # Extract client_id
    client_id_value = get_field('client_id', 'clientId')
    
    # Extract patient_id
    patient_id_value = get_field('patient_id', 'patientId')
    
    # Extract emr_id
    emr_id_value = get_field('emr_id', 'emrId')
    
    # Extract trauma_type
    trauma_type_value = get_field('trauma_type', 'traumaType')
    
    # Extract chief_complaints (required field)
    chief_complaints_value = get_field('chief_complaints', 'chiefComplaints')
    if not chief_complaints_value or not isinstance(chief_complaints_value, list):
        # Ensure it's a list, even if empty (validation happens elsewhere)
        chief_complaints_value = []
    
    # Extract status
    status_value = get_field('status')
    
    # Extract created_by
    created_by_value = get_field('created_by', 'createdBy')
    
    # Extract started_at
    started_at_value = get_field('started_at', 'startedAt')
    
    # Extract created_at (fallback to current timestamp if not provided)
    created_at_value = get_field('created_at', 'createdAt')
    if not created_at_value:
        created_at_value = datetime.utcnow().isoformat() + 'Z'
    
    # Extract updated_at (fallback to current timestamp if not provided)
    updated_at_value = get_field('updated_at', 'updatedAt')
    if not updated_at_value:
        updated_at_value = datetime.utcnow().isoformat() + 'Z'
    
    # Build parsed_payload structure matching encounter_structure_example.json
    parsed_payload = {
        "id": id_value,
        "encounter_id": encounter_id_value,
        "client_id": client_id_value,
        "patient_id": patient_id_value,
        "emr_id": emr_id_value,
        "trauma_type": trauma_type_value,
        "chief_complaints": chief_complaints_value,
        "status": status_value,
        "created_by": created_by_value,
        "started_at": started_at_value,
        "created_at": created_at_value,
        "updated_at": updated_at_value,
    }
    
    # Remove None values to keep the payload clean (optional fields)
    # But keep empty strings and empty lists as they may be meaningful
    parsed_payload = {
        k: v for k, v in parsed_payload.items()
        if v is not None
    }
    
    # Ensure required fields are present (validation happens in the endpoint)
    # But we need at least id, encounter_id, client_id, patient_id for the structure
    return parsed_payload


def validate_encounter_payload(parsed_payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate that the parsed encounter payload has required fields.
    
    Args:
        parsed_payload: Parsed encounter payload dictionary
        
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    # Required fields
    required_fields = {
        'encounter_id': 'encounter_id',
        'patient_id': 'patient_id',
        'client_id': 'client_id',
    }
    
    missing_fields = []
    for field_key, field_name in required_fields.items():
        if not parsed_payload.get(field_key):
            missing_fields.append(field_name)
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Validate chief_complaints is present and non-empty
    chief_complaints = parsed_payload.get('chief_complaints', [])
    if not chief_complaints or not isinstance(chief_complaints, list) or len(chief_complaints) == 0:
        return False, "chief_complaints is required and must be a non-empty array"
    
    return True, None

