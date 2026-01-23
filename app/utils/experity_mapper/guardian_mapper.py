"""
Guardian Mapper - Extract and map guardian info from encounter data.

This module provides deterministic extraction of guardian information from
encounter additionalQuestions.guardianAssistedInterview, with a preserve-all-fields
approach to ensure no data is lost.

New mapping logic (when guardianAssistedInterview is a string):
- If "No" → relationship = "Self", present = False
- If "Yes" AND guardianAssistedInterviewBy contains "Mother"/"Father" 
  → relationship = "Mother"/"Father", present = True
- If "Yes" AND guardianAssistedInterviewBy is empty or contains other values
  → relationship = "Other", present = True, guardianName = first value (if available)
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def extract_guardian(encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract guardian info from encounter additionalQuestions.guardianAssistedInterview.
    
    Supports two formats:
    1. String format: guardianAssistedInterview = "Yes"/"No" with guardianAssistedInterviewBy array
    2. Object format: guardianAssistedInterview = {present: bool, guardianName: str, ...}
    
    Strategy (preserve-all-fields):
    1. Check if guardianAssistedInterview is a string (new format)
    2. If string, apply new mapping logic
    3. If object, preserve ALL fields including unknown ones
    4. Map known fields explicitly (ensures correct field names)
    
    Known fields mapped:
    - present: boolean (defaults to False if missing)
    - guardianName: string or None
    - relationship: string or None
    - notes: string or None
    
    Args:
        encounter_data: Encounter dictionary with additionalQuestions field
        
    Returns:
        Guardian dictionary with all fields from source (backward compatible format)
        
    Examples:
        >>> extract_guardian({"additionalQuestions": {"guardianAssistedInterview": "No"}})
        {"present": False, "guardianName": None, "relationship": "Self", "notes": None}
        
        >>> extract_guardian({"additionalQuestions": {
        ...     "guardianAssistedInterview": "Yes",
        ...     "guardianAssistedInterviewBy": ["Mother"]
        ... }})
        {"present": True, "guardianName": None, "relationship": "Mother", "notes": None}
        
        >>> extract_guardian({"additionalQuestions": {
        ...     "guardianAssistedInterview": "Yes",
        ...     "guardianAssistedInterviewBy": ["Grandmother"]
        ... }})
        {"present": True, "guardianName": "Grandmother", "relationship": "Other", "notes": None}
        
        >>> extract_guardian({"additionalQuestions": {
        ...     "guardianAssistedInterview": {"present": True, "guardianName": "John"}}})
        {"present": True, "guardianName": "John", "relationship": None, "notes": None}
    """
    if not isinstance(encounter_data, dict):
        logger.warning("Encounter data is not a dict, returning default guardian")
        return _create_default_guardian()
    
    additional_questions = encounter_data.get("additionalQuestions", {})
    if not isinstance(additional_questions, dict):
        logger.warning("additionalQuestions is not a dict, returning default guardian")
        return _create_default_guardian()
    
    # Check if guardianAssistedInterview is a string (new format)
    guardian_interview_value = additional_questions.get("guardianAssistedInterview")
    guardian_interview_by = additional_questions.get("guardianAssistedInterviewBy", [])
    
    # Handle string-based format ("Yes"/"No")
    if isinstance(guardian_interview_value, str):
        guardian_interview_value = guardian_interview_value.strip()
        
        if guardian_interview_value.upper() == "NO":
            # Case 1: guardianAssistedInterview = "No" → relationship = "Self"
            return {
                "present": False,
                "guardianName": None,
                "relationship": "Self",
                "notes": None
            }
        
        elif guardian_interview_value.upper() == "YES":
            # Case 2 & 3: guardianAssistedInterview = "Yes"
            if not isinstance(guardian_interview_by, list):
                guardian_interview_by = []
            
            # Normalize the array (handle case-insensitive, get first non-empty value)
            normalized_by = [str(item).strip() for item in guardian_interview_by if item]
            
            # Case 2a: Empty array → relationship = "Other"
            if not normalized_by:
                return {
                    "present": True,
                    "guardianName": None,
                    "relationship": "Other",
                    "notes": None
                }
            
            first_value = normalized_by[0]
            first_value_lower = first_value.lower()
            
            # Case 2b: Check if it's "Mother" or "Father" (case-insensitive)
            if first_value_lower in ["mother", "father"]:
                # Capitalize properly: "Mother" or "Father"
                relationship = "Mother" if first_value_lower == "mother" else "Father"
                return {
                    "present": True,
                    "guardianName": None,
                    "relationship": relationship,
                    "notes": None
                }
            
            # Case 3: Not "Mother" or "Father" → relationship = "Other", guardianName = value
            else:
                return {
                    "present": True,
                    "guardianName": first_value,  # Use the value as guardianName
                    "relationship": "Other",
                    "notes": None
                }
    
    # Fallback: Handle object-based format (existing logic - backward compatible)
    guardian_data = additional_questions.get("guardianAssistedInterview", {})
    if not isinstance(guardian_data, dict):
        logger.warning("guardianAssistedInterview is not a dict or string, returning default guardian")
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
