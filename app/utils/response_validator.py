"""
Response validation and format correction utilities.

This module provides functions to validate and correct format issues in Azure AI agent responses,
ensuring compliance with the expected schema and prompt rules.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def validate_and_fix_quality_field(complaint: Dict[str, Any], source_data: Optional[Dict[str, Any]] = None) -> None:
    """
    Validate and fix the quality field in a complaint's notesPayload.
    
    Rules:
    1. Quality must be an array (not a string)
    2. Quality should not be fabricated if not in source data
    
    Args:
        complaint: The complaint dictionary to validate/fix
        source_data: Optional source encounter data to check for quality information
    """
    if "notesPayload" not in complaint:
        return
    
    notes_payload = complaint["notesPayload"]
    if "quality" not in notes_payload:
        return
    
    quality = notes_payload["quality"]
    
    # Fix 1: Convert string to array if needed
    if isinstance(quality, str):
        logger.warning(f"Quality field is string '{quality}', converting to array")
        notes_payload["quality"] = [quality]
        quality = notes_payload["quality"]
    
    # Fix 2: Check for fabrication (if source_data provided)
    if source_data and isinstance(quality, list) and len(quality) > 0:
        # Check if quality exists in source data
        has_quality_in_source = False
        
        # Check chiefComplaints for quality
        if "chiefComplaints" in source_data:
            for cc in source_data.get("chiefComplaints", []):
                if "painQuality" in cc and cc["painQuality"]:
                    has_quality_in_source = True
                    break
                if "quality" in cc and cc["quality"]:
                    has_quality_in_source = True
                    break
                # Check description text for quality keywords
                desc = cc.get("description", "").lower()
                quality_keywords = ["sharp", "dull", "pressure", "aching", "throbbing", "burning", "crushing", "squeezing"]
                if any(keyword in desc for keyword in quality_keywords):
                    has_quality_in_source = True
                    break
        
        # If quality not in source and we have fabricated values, log warning
        if not has_quality_in_source:
            logger.warning(
                f"Quality field contains values {quality} but source data doesn't specify quality. "
                "This may be fabrication. Consider setting to empty array."
            )
            # Optionally: Set to empty array to prevent fabrication
            # notes_payload["quality"] = []


def validate_and_fix_severity_field(complaint: Dict[str, Any]) -> None:
    """
    Validate and fix the severity field in a complaint's notesPayload.
    
    Rules:
    1. Severity must be numeric (not a string)
    
    Args:
        complaint: The complaint dictionary to validate/fix
    """
    if "notesPayload" not in complaint:
        return
    
    notes_payload = complaint["notesPayload"]
    if "severity" not in notes_payload:
        return
    
    severity = notes_payload["severity"]
    
    # Convert string to numeric if it's a valid number
    if isinstance(severity, str):
        try:
            # Try to convert to int first, then float
            if "." in severity:
                notes_payload["severity"] = float(severity)
            else:
                notes_payload["severity"] = int(severity)
            logger.warning(f"Severity field is string '{severity}', converted to numeric")
        except ValueError:
            logger.error(f"Severity field is string '{severity}' but cannot be converted to number")
            # Could set to None or keep as-is
            notes_payload["severity"] = None


def validate_and_fix_experity_response(
    experity_mapping: Dict[str, Any],
    source_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Validate and fix format issues in the Experity mapping response.
    
    This function:
    1. Fixes quality field format (string -> array)
    2. Fixes severity field format (string -> numeric)
    3. Logs warnings for potential fabrications
    
    Args:
        experity_mapping: The Experity mapping response from Azure AI
        source_data: Optional source encounter data for validation
    
    Returns:
        The validated and corrected mapping
    """
    # Unwrap experityActions if nested
    experity_actions = experity_mapping
    if "experityActions" in experity_actions:
        experity_actions = experity_actions["experityActions"]
    
    # Validate complaints
    if "complaints" in experity_actions:
        for complaint in experity_actions["complaints"]:
            validate_and_fix_quality_field(complaint, source_data)
            validate_and_fix_severity_field(complaint)
    
    return experity_mapping

