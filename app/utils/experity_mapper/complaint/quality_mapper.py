"""
Quality Mapper - Extract and map quality from complaint data.

This module provides deterministic extraction of quality values from
complaint data, following the rules from the prompt specification.

CRITICAL: No fabrication - if quality is not explicitly present in source,
return empty array [].
"""

import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Common quality keywords that can be extracted from description text
# These match common quality values from NOTES_TEMPLATES
QUALITY_KEYWORDS = {
    # Pain qualities
    "sharp": "Sharp",
    "dull": "Dull",
    "aching": "Aching",
    "throbbing": "Throbbing",
    "burning": "Burning",
    "shooting": "Shooting",
    "spasmodic": "Spasmodic",
    "colicky": "Colicky",
    "cramping": "Cramping",
    "pressure": "Pressure",
    "crushing": "Crushing",
    "squeezing": "Squeezing",
    "migratory": "Migratory",
    
    # Visual/Physical qualities
    "red": "Red",
    "redness": "Redness",
    "raised": "Raised",
    "pruritic": "Pruritic",
    "itching": "Itching",
    "weeping": "Weeping",
    "spreading": "Spreading",
    "shrinking": "Shrinking",
    
    # Trauma qualities
    "bleeding": "Bleeding",
    "cut skin": "Cut skin",
    "puncture": "Puncture",
    "draining pus": "Draining pus",
    "draining clear fluid": "Draining clear fluid",
    
    # Respiratory qualities
    "chest tightness": "Chest tightness",
    "rapid breathing": "Rapid breathing",
    "choking sensation": "Choking sensation",
    "sputum": "Sputum",
    "bloody sputum": "Bloody sputum",
    
    # Other qualities
    "scratchy": "Scratchy",
    "foreign body sensation": "Foreign body sensation",
    "painful": "Painful",
}


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


def _extract_quality_from_description(description: str) -> List[str]:
    """
    Extract quality keywords from complaint description text.
    
    Searches for quality keywords in the description and returns matching
    quality values. Only returns qualities that are explicitly mentioned.
    
    Args:
        description: Complaint description text
        
    Returns:
        List of quality values found in description (empty if none found)
    """
    if not description or not isinstance(description, str):
        return []
    
    description_lower = description.lower()
    found_qualities = []
    
    # Search for quality keywords (longer phrases first to avoid partial matches)
    # Sort by length (longest first) to match "chest tightness" before "tightness"
    sorted_keywords = sorted(QUALITY_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for keyword, quality_value in sorted_keywords:
        # Use word boundary matching to avoid partial matches
        # e.g., "sharp" in "sharp pain" but not in "sharpen"
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, description_lower, re.IGNORECASE):
            if quality_value not in found_qualities:
                found_qualities.append(quality_value)
    
    return found_qualities


def extract_quality(complaint: Dict[str, Any]) -> List[str]:
    """
    Extract quality from complaint data.
    
    Rules (from prompt):
    - Extract from complaint.painQuality (if present)
    - Extract from complaint.quality (if present)
    - Extract from complaint.description text (keyword matching)
    - Match against template quality arrays (future enhancement)
    - **CRITICAL**: Return [] if no quality found (no fabrication)
    - Always return array (never string)
    
    Priority:
    1. painQuality field
    2. quality field
    3. description text keywords
    
    Args:
        complaint: Complaint dictionary from chiefComplaints array
        
    Returns:
        List of quality strings (empty list if no quality found)
        
    Examples:
        >>> extract_quality({"painQuality": "Sharp"})
        ["Sharp"]
        >>> extract_quality({"description": "sharp chest pain"})
        ["Sharp"]
        >>> extract_quality({"description": "chest pain"})
        []
        >>> extract_quality({"quality": ["Sharp", "Dull"]})
        ["Sharp", "Dull"]
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
    
    # Priority 3: Extract from description text (keyword matching)
    # Always check description to find additional quality values
    description = complaint.get("description", "")
    if description:
        desc_qualities = _extract_quality_from_description(description)
        if desc_qualities:
            # Add qualities from description that aren't already found
            for q in desc_qualities:
                if q not in found_qualities:
                    found_qualities.append(q)
            if desc_qualities:
                logger.debug(f"Extracted quality from description: {desc_qualities}")
    
    # CRITICAL: If no quality found, return empty array (no fabrication)
    if not found_qualities:
        logger.debug("No quality found in complaint, returning empty array (no fabrication)")
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
        ...     {"id": "c2", "description": "dull ache"}
        ... ]
        >>> extract_qualities_from_complaints(complaints)
        {"c1": ["Sharp"], "c2": ["Dull", "Aching"]}
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
