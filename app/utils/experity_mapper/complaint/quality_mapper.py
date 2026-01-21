"""
Quality Mapper - Extract and map quality from complaint data.

This module provides deterministic extraction of quality values from
complaint data, following the rules from the prompt specification.

CRITICAL: No fabrication - if quality is not explicitly present in source,
return empty array [].
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _normalize_quality_value(value: Any) -> Optional[str]:
    """
    Normalize a quality value to match template format.
    
    Args:
        value: Quality value from source (string, number, etc.)
        
    Returns:
        Normalized quality string or None if invalid
    """
    if not value:
        return None
    
    # Convert to string and normalize
    if isinstance(value, (int, float)):
        return None  # Quality should be text, not numbers
    
    quality_str = str(value).strip()
    if not quality_str:
        return None
    
    # Capitalize first letter (match template format)
    # Templates use capitalized values like "Sharp", "Dull", etc.
    normalized = quality_str[0].upper() + quality_str[1:].lower() if len(quality_str) > 1 else quality_str.upper()
    
    return normalized


def extract_quality(complaint: Dict[str, Any]) -> List[str]:
    """
    Extract quality from complaint data.
    
    Rules:
    - Extract from complaint.painQuality (if present)
    - Extract from complaint.quality (if present)
    - **CRITICAL**: Return [] if no quality found (no fabrication)
    - Always return array (never string)
    - **DO NOT extract from description text** - only use explicit fields
    
    Priority:
    1. painQuality field
    2. quality field
    
    Args:
        complaint: Complaint dictionary from chiefComplaints array
        
    Returns:
        List of quality strings (empty list if no quality found)
        
    Examples:
        >>> extract_quality({"painQuality": "Sharp"})
        ["Sharp"]
        >>> extract_quality({"description": "sharp chest pain"})
        []  # No quality field, returns empty
        >>> extract_quality({"quality": ["Sharp", "Dull"]})
        ["Sharp", "Dull"]
        >>> extract_quality({"description": "chest pain"})
        []  # No explicit quality fields
    """
    if not isinstance(complaint, dict):
        logger.debug("Complaint is not a dict, returning empty quality array")
        return []
    
    found_qualities = []
    
    # Priority 1: Extract from painQuality field
    pain_quality = complaint.get("painQuality")
    if pain_quality:
        normalized = _normalize_quality_value(pain_quality)
        if normalized:
            found_qualities.append(normalized)
            logger.debug(f"Extracted quality from painQuality: {normalized}")
    
    # Priority 2: Extract from quality field
    quality_field = complaint.get("quality")
    if quality_field:
        if isinstance(quality_field, list):
            # If it's already a list, normalize each item
            for item in quality_field:
                normalized = _normalize_quality_value(item)
                if normalized and normalized not in found_qualities:
                    found_qualities.append(normalized)
        else:
            # If it's a single value, normalize it
            normalized = _normalize_quality_value(quality_field)
            if normalized and normalized not in found_qualities:
                found_qualities.append(normalized)
        logger.debug(f"Extracted quality from quality field: {found_qualities}")
    
    # CRITICAL: If no quality found, return empty array (no fabrication)
    if not found_qualities:
        logger.debug("No quality found in complaint (no painQuality or quality field), returning empty array (no fabrication)")
        return []
    
    # Remove duplicates while preserving order
    unique_qualities = []
    for q in found_qualities:
        if q not in unique_qualities:
            unique_qualities.append(q)
    
    logger.debug(f"Final extracted quality: {unique_qualities}")
    return unique_qualities


def extract_qualities_from_complaints(
    complaints: list,
    encounter_id: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    Extract quality for all complaints in a list.
    
    Creates a mapping from complaint ID or index to quality array.
    This allows matching quality to complaints in the LLM response.
    
    Args:
        complaints: List of complaint dictionaries from chiefComplaints
        encounter_id: Optional encounter ID for logging
        
    Returns:
        Dictionary mapping complaint identifier to quality array:
        - Key: complaint ID (if available) or index as string
        - Value: list of quality strings (empty list if none found)
        
    Examples:
        >>> complaints = [
        ...     {"id": "c1", "painQuality": "Sharp"},
        ...     {"id": "c2", "quality": "Dull"},
        ...     {"id": "c3", "description": "burning pain"}  # No quality field
        ... ]
        >>> extract_qualities_from_complaints(complaints)
        {"c1": ["Sharp"], "c2": ["Dull"], "c3": []}
    """
    quality_map = {}
    
    if not isinstance(complaints, list):
        logger.warning(f"Complaints is not a list, returning empty quality map")
        return quality_map
    
    for idx, complaint in enumerate(complaints):
        if not isinstance(complaint, dict):
            logger.warning(f"Complaint at index {idx} is not a dict, skipping")
            continue
        
        # Try to get complaint ID for mapping
        complaint_id = complaint.get("id") or complaint.get("complaintId")
        
        # Extract quality
        quality = extract_quality(complaint)
        
        # Use complaint ID if available, otherwise use index
        key = complaint_id if complaint_id else str(idx)
        quality_map[key] = quality
        
        logger.debug(
            f"Extracted quality {quality} for complaint {key} "
            f"(encounter: {encounter_id or 'unknown'})"
        )
    
    logger.info(
        f"Extracted {len(quality_map)} quality values from {len(complaints)} complaints "
        f"(encounter: {encounter_id or 'unknown'})"
    )
    return quality_map
