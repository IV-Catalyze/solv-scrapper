"""
Onset Mapper - Extract and format onset from complaint data.

This module provides deterministic extraction and formatting of onset values from
complaint durationDays, following the rules from the prompt specification.

CRITICAL: No fabrication - if durationDays is missing, return null.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def extract_onset(complaint: Dict[str, Any]) -> Optional[str]:
    """
    Extract and format onset from complaint data.
    
    Rules (from prompt):
    - Extract from complaint.durationDays
    - Format: "{N} day(s) ago" where N is the durationDays value
    - If durationDays is 0: Use "Today" or "0 days ago"
    - If durationDays is 1: Use "1 day ago" (singular)
    - If durationDays > 1: Use "{N} days ago" (plural)
    - If durationDays is null or missing: Use null (DO NOT fabricate)
    - NEVER generate ISO timestamps or specific dates
    - NEVER calculate dates by subtracting from current date
    
    Args:
        complaint: Complaint dictionary from chiefComplaints array
        
    Returns:
        Onset string ("Today", "1 day ago", "2 days ago", etc.) or None if durationDays missing
        
    Examples:
        >>> extract_onset({"durationDays": 1})
        "1 day ago"
        >>> extract_onset({"durationDays": 2})
        "2 days ago"
        >>> extract_onset({"durationDays": 0})
        "Today"
        >>> extract_onset({"durationDays": None})
        None
        >>> extract_onset({})
        None
    """
    if not isinstance(complaint, dict):
        logger.debug("Complaint is not a dict, returning None for onset")
        return None
    
    duration_days = complaint.get("durationDays")
    
    # If durationDays is missing or None, return None (no fabrication)
    if duration_days is None:
        logger.debug("durationDays is missing or None, returning None for onset")
        return None
    
    # Convert to integer (handle string/float inputs)
    try:
        duration = int(float(duration_days))
    except (ValueError, TypeError):
        logger.warning(f"Invalid durationDays '{duration_days}', returning None for onset")
        return None
    
    # Format according to rules
    if duration == 0:
        onset = "Today"
        logger.debug(f"durationDays is 0, formatted as 'Today'")
    elif duration == 1:
        onset = "1 day ago"
        logger.debug(f"durationDays is 1, formatted as '1 day ago'")
    elif duration > 1:
        onset = f"{duration} days ago"
        logger.debug(f"durationDays is {duration}, formatted as '{onset}'")
    else:
        # Negative duration (invalid)
        logger.warning(f"Negative durationDays {duration}, returning None for onset")
        return None
    
    return onset


def extract_onsets_from_complaints(
    complaints: list,
    encounter_id: Optional[str] = None
) -> Dict[str, Optional[str]]:
    """
    Extract onset for all complaints in a list.
    
    Creates a mapping from complaint ID or index to onset string.
    This allows matching onset to complaints in the LLM response.
    
    Args:
        complaints: List of complaint dictionaries from chiefComplaints
        encounter_id: Optional encounter ID for logging
        
    Returns:
        Dictionary mapping complaint identifier to onset string:
        - Key: complaint ID (if available) or index as string
        - Value: onset string ("Today", "1 day ago", etc.) or None if durationDays missing
        
    Examples:
        >>> complaints = [
        ...     {"id": "c1", "durationDays": 1},
        ...     {"id": "c2", "durationDays": 0},
        ...     {"id": "c3"}  # No durationDays
        ... ]
        >>> extract_onsets_from_complaints(complaints)
        {"c1": "1 day ago", "c2": "Today", "c3": None}
    """
    onset_map = {}
    
    if not isinstance(complaints, list):
        logger.warning(f"Complaints is not a list, returning empty onset map")
        return onset_map
    
    for idx, complaint in enumerate(complaints):
        if not isinstance(complaint, dict):
            logger.warning(f"Complaint at index {idx} is not a dict, skipping")
            continue
        
        # Try to get complaint ID for mapping
        complaint_id = complaint.get("id") or complaint.get("complaintId")
        
        # Extract onset
        onset = extract_onset(complaint)
        
        # Use complaint ID if available, otherwise use index
        key = complaint_id if complaint_id else str(idx)
        onset_map[key] = onset
        
        logger.debug(
            f"Extracted onset '{onset}' for complaint {key} "
            f"(encounter: {encounter_id or 'unknown'})"
        )
    
    logger.info(
        f"Extracted {len(onset_map)} onset values from {len(complaints)} complaints "
        f"(encounter: {encounter_id or 'unknown'})"
    )
    return onset_map
