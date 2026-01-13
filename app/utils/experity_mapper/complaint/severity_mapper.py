"""
Severity Mapper - Extract and map severity from complaint data.

This module provides deterministic extraction of severity values from
complaint data, following the rules from the prompt specification.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default severity when painScale is missing (from prompt: default to 5)
DEFAULT_SEVERITY = 5

# Valid severity range (0-10)
MIN_SEVERITY = 0
MAX_SEVERITY = 10


def extract_severity(complaint: Dict[str, Any]) -> int:
    """
    Extract severity from complaint data.
    
    Rules (from prompt):
    - Use painScale from complaint if available (numeric 0-10)
    - If missing, default to 5
    - Always return numeric (never string)
    - Validate range (0-10)
    - Clamp out-of-range values to valid range
    
    Args:
        complaint: Complaint dictionary from chiefComplaints array
        
    Returns:
        Severity value (0-10) as integer
        
    Examples:
        >>> extract_severity({"painScale": 7})
        7
        >>> extract_severity({"painScale": None})
        5
        >>> extract_severity({})
        5
        >>> extract_severity({"painScale": "8"})
        8
        >>> extract_severity({"painScale": 15})
        10
        >>> extract_severity({"painScale": -5})
        0
    """
    if not isinstance(complaint, dict):
        logger.warning(f"Complaint is not a dict, using default severity {DEFAULT_SEVERITY}")
        return DEFAULT_SEVERITY
    
    # Extract painScale
    pain_scale = complaint.get("painScale")
    
    # Handle None or missing
    if pain_scale is None:
        logger.debug(f"No painScale found in complaint, using default {DEFAULT_SEVERITY}")
        return DEFAULT_SEVERITY
    
    # Convert to numeric if needed
    try:
        # Handle both int and float (including string representations)
        if isinstance(pain_scale, str):
            # Try to convert string to float first (handles "7.5"), then int
            severity = int(float(pain_scale))
        elif isinstance(pain_scale, float):
            severity = int(pain_scale)
        elif isinstance(pain_scale, int):
            severity = pain_scale
        else:
            logger.warning(f"painScale has unexpected type {type(pain_scale)}, using default {DEFAULT_SEVERITY}")
            return DEFAULT_SEVERITY
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid painScale '{pain_scale}' (error: {e}), using default {DEFAULT_SEVERITY}")
        return DEFAULT_SEVERITY
    
    # Validate and clamp range
    if severity < MIN_SEVERITY:
        logger.warning(f"painScale {severity} < {MIN_SEVERITY}, clamping to {MIN_SEVERITY}")
        return MIN_SEVERITY
    if severity > MAX_SEVERITY:
        logger.warning(f"painScale {severity} > {MAX_SEVERITY}, clamping to {MAX_SEVERITY}")
        return MAX_SEVERITY
    
    logger.debug(f"Extracted severity {severity} from painScale {pain_scale}")
    return severity


def extract_severities_from_complaints(
    complaints: list,
    encounter_id: Optional[str] = None
) -> Dict[str, int]:
    """
    Extract severity for all complaints in a list.
    
    Creates a mapping from complaint ID or index to severity value.
    This allows matching severity to complaints in the LLM response.
    
    Args:
        complaints: List of complaint dictionaries from chiefComplaints
        encounter_id: Optional encounter ID for logging
        
    Returns:
        Dictionary mapping complaint identifier to severity:
        - Key: complaint ID (if available) or index as string
        - Value: severity (0-10)
        
    Examples:
        >>> complaints = [
        ...     {"id": "c1", "painScale": 7},
        ...     {"id": "c2", "painScale": 3}
        ... ]
        >>> extract_severities_from_complaints(complaints)
        {"c1": 7, "c2": 3}
    """
    severity_map = {}
    
    if not isinstance(complaints, list):
        logger.warning(f"Complaints is not a list, returning empty severity map")
        return severity_map
    
    for idx, complaint in enumerate(complaints):
        if not isinstance(complaint, dict):
            logger.warning(f"Complaint at index {idx} is not a dict, skipping")
            continue
        
        # Try to get complaint ID for mapping
        complaint_id = complaint.get("id") or complaint.get("complaintId")
        
        # Extract severity
        severity = extract_severity(complaint)
        
        # Use complaint ID if available, otherwise use index
        key = complaint_id if complaint_id else str(idx)
        severity_map[key] = severity
        
        logger.debug(
            f"Extracted severity {severity} for complaint {key} "
            f"(encounter: {encounter_id or 'unknown'})"
        )
    
    logger.info(
        f"Extracted {len(severity_map)} severity values from {len(complaints)} complaints "
        f"(encounter: {encounter_id or 'unknown'})"
    )
    return severity_map
