"""
Guardian Mapper - Extract and map guardian info from encounter data.

This module provides deterministic extraction of guardian information from
encounter additionalQuestions.guardianAssistedInterview, with a preserve-all-fields
approach to ensure no data is lost.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def extract_guardian(encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract guardian info from encounter additionalQuestions.guardianAssistedInterview.
    
    Strategy (preserve-all-fields):
    1. Start with source guardian data (preserves ALL fields including unknown ones)
    2. Map known fields explicitly (ensures correct field names)
    3. Additional fields are automatically preserved
    
    Known fields mapped:
    - present: boolean (defaults to False if missing)
    - guardianName: string or None
    - relationship: string or None
    - notes: string or None
    
    Args:
        encounter_data: Encounter dictionary with additionalQuestions field
        
    Returns:
        Guardian dictionary with all fields from source
        
    Examples:
        >>> extract_guardian({"additionalQuestions": {"guardianAssistedInterview": {"present": True}}})
        {"present": True, "guardianName": None, "relationship": None, "notes": None}
        
        >>> extract_guardian({"additionalQuestions": {"guardianAssistedInterview": 
        ...     {"present": True, "guardianName": "John", "newField": "value"}}})
        {"present": True, "guardianName": "John", "relationship": None, "notes": None, 
         "newField": "value"}
    """
    if not isinstance(encounter_data, dict):
        logger.warning("Encounter data is not a dict, returning default guardian")
        return _create_default_guardian()
    
    additional_questions = encounter_data.get("additionalQuestions", {})
    if not isinstance(additional_questions, dict):
        logger.warning("additionalQuestions is not a dict, returning default guardian")
        return _create_default_guardian()
    
    guardian_data = additional_questions.get("guardianAssistedInterview", {})
    if not isinstance(guardian_data, dict):
        logger.warning("guardianAssistedInterview is not a dict, returning default guardian")
        return _create_default_guardian()
    
    if not guardian_data:
        logger.debug("No guardian data found, returning default guardian")
        return _create_default_guardian()
    
    # Start with source guardian data (preserves ALL fields including unknown ones)
    guardian = dict(guardian_data)
    
    # Map known fields explicitly (ensures correct field names and defaults)
    known_field_mappings = {
        "present": guardian_data.get("present", False),
        "guardianName": guardian_data.get("guardianName"),
        "relationship": guardian_data.get("relationship"),
        "notes": guardian_data.get("notes"),
    }
    
    # Update with mapped values (preserves additional fields)
    guardian.update(known_field_mappings)
    
    # Ensure present is boolean
    if not isinstance(guardian.get("present"), bool):
        guardian["present"] = bool(guardian.get("present", False))
    
    # Log preserved additional fields
    known_fields = set(known_field_mappings.keys())
    additional_fields = set(guardian.keys()) - known_fields
    if additional_fields:
        logger.debug(f"Preserved additional fields from guardian data: {additional_fields}")
    
    return guardian


def _create_default_guardian() -> Dict[str, Any]:
    """
    Create default guardian structure.
    
    Returns:
        Dictionary with default guardian values
    """
    return {
        "present": False,
        "guardianName": None,
        "relationship": None,
        "notes": None,
    }
