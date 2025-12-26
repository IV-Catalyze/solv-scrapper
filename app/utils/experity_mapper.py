"""
Experity Mapping Utilities - Pre and Post Processing

This module provides deterministic mapping functions to extract and merge
data before/after LLM processing, reducing AI work and ensuring accuracy.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ICD-10 Code Mapping (from prompt specification)
ICD10_MAPPING = {
    "Anxiety": "F41.9",
    "Asthma": "J45.909",
    "Cancer": "C80.1",
    "Cardiac Arrhythmia": "I49.9",
    "Congestive Heart Failure": "I50.9",
    "COPD": "J44.9",
    "Diabetes": "E11.9",
    "GERD": "K21.9",
    "Hypertension": "I10"
}


def _normalize_condition_name(name: str) -> str:
    """
    Normalize condition name for matching.
    
    Removes common prefixes/suffixes and converts to lowercase for case-insensitive matching.
    Examples:
    - "history of anxiety" -> "anxiety"
    - "diabetes mellitus" -> "diabetes"
    - "History of high blood pressure" -> "hypertension" (via keyword mapping)
    
    Args:
        name: Condition name from encounter data
        
    Returns:
        Normalized name for matching
    """
    if not name:
        return ""
    
    normalized = name.lower().strip()
    
    # Remove common prefixes
    prefixes = ["history of", "history", "hx of", "hx"]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    
    # Handle common variations/aliases
    # Map common terms to canonical names (these should match normalized ICD10_MAPPING keys)
    alias_map = {
        "high blood pressure": "hypertension",
        "htn": "hypertension",
        "hypertensive": "hypertension",
        "diabetes mellitus": "diabetes",
        "dm": "diabetes",
        "diabetic": "diabetes",
        "chronic obstructive pulmonary disease": "copd",
        "chronic obstructive pulmonary": "copd",
        "congestive heart failure": "congestive heart failure",  # Keep as is (already matches mapping)
        "chf": "congestive heart failure",
        "cardiac arrhythmias": "cardiac arrhythmia",
        "cardiac arrhythmia": "cardiac arrhythmia",  # Already matches, but keep for clarity
        "arrhythmia": "cardiac arrhythmia",
        "arrhythmias": "cardiac arrhythmia",
        "malignancy": "cancer",
        "cancer": "cancer",  # Already matches, but keep for clarity
        "anxiety/ nerves": "anxiety",
        "anxiety nerves": "anxiety",
        "anxious": "anxiety",
    }
    
    if normalized in alias_map:
        normalized = alias_map[normalized]
    
    return normalized


def _find_matching_icd_code(condition_name: str) -> Optional[Tuple[str, str]]:
    """
    Find matching ICD code for a condition name using case-insensitive matching.
    
    Args:
        condition_name: Condition name from encounter data
        
    Returns:
        Tuple of (canonical_condition_name, icd10_code) if match found, None otherwise
    """
    normalized_input = _normalize_condition_name(condition_name)
    
    if not normalized_input:
        return None
    
    # Build normalized mapping: normalized_key -> (canonical_name, icd_code)
    normalized_mapping = {_normalize_condition_name(k): (k, v) for k, v in ICD10_MAPPING.items()}
    
    # Try exact match first (for canonical names)
    if normalized_input in normalized_mapping:
        return normalized_mapping[normalized_input]
    
    # Try substring match as fallback (e.g., "anxiety disorder" might contain "anxiety")
    # Only match if the normalized key appears as a word in the input (more conservative)
    # This handles cases where the condition name has additional words
    words_in_input = set(normalized_input.split())
    for normalized_key, (canonical_name, code) in normalized_mapping.items():
        key_words = set(normalized_key.split())
        # Match if all words of the key are in the input (handles multi-word keys like "cardiac arrhythmia")
        if key_words.issubset(words_in_input):
            logger.debug(f"Matched '{condition_name}' to '{canonical_name}' (all key words found in input)")
            return (canonical_name, code)
        # Also try simple substring match for single-word keys (e.g., "anxiety" in "anxiety disorder")
        if len(key_words) == 1 and normalized_key in normalized_input:
            logger.debug(f"Matched '{condition_name}' to '{canonical_name}' (single-word key found in input)")
            return (canonical_name, code)
    
    return None


def extract_icd_updates(encounter_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Extract ICD updates from encounter conditions using deterministic mapping.
    
    This function implements the ICD extraction rules from the prompt:
    - Source: `additionalQuestions.conditions` array
    - Filter: ONLY include conditions where `answer: true`
    - Mapping: Use ICD10_MAPPING with case-insensitive matching
    - Output: List of ICD update objects
    
    Args:
        encounter_data: Encounter data dictionary (can be nested in queue_entry.raw_payload
                       or direct encounter object)
        
    Returns:
        List of ICD update dictionaries with structure:
        [
            {
                "conditionName": str,  # Canonical name from mapping
                "icd10Code": str,
                "presentInEncounter": True,
                "source": "conditions"
            },
            ...
        ]
        
    Examples:
        >>> encounter = {
        ...     "additionalQuestions": {
        ...         "conditions": [
        ...             {"name": "history of anxiety", "answer": True},
        ...             {"name": "diabetes mellitus", "answer": False}
        ...         ]
        ...     }
        ... }
        >>> extract_icd_updates(encounter)
        [{"conditionName": "Anxiety", "icd10Code": "F41.9", "presentInEncounter": True, "source": "conditions"}]
    """
    if not encounter_data:
        return []
    
    # Extract conditions from additionalQuestions.conditions
    additional_questions = encounter_data.get("additionalQuestions") or {}
    conditions = additional_questions.get("conditions") or []
    
    if not conditions:
        logger.debug("No conditions found in additionalQuestions.conditions")
        return []
    
    icd_updates = []
    
    for condition in conditions:
        # Skip if not a dictionary
        if not isinstance(condition, dict):
            logger.warning(f"Skipping non-dict condition: {condition}")
            continue
        
        # Get condition name and answer
        condition_name = condition.get("name")
        answer = condition.get("answer")
        
        # CRITICAL: Only include conditions where answer is True
        if answer is not True:
            logger.debug(f"Skipping condition '{condition_name}' because answer is {answer} (not True)")
            continue
        
        # Skip if condition name is missing
        if not condition_name:
            logger.warning("Skipping condition with missing name")
            continue
        
        # Find matching ICD code
        match_result = _find_matching_icd_code(condition_name)
        
        if match_result:
            canonical_name, icd_code = match_result
            icd_updates.append({
                "conditionName": canonical_name,
                "icd10Code": icd_code,
                "presentInEncounter": True,
                "source": "conditions"
            })
            logger.debug(f"Mapped condition '{condition_name}' to {canonical_name} ({icd_code})")
        else:
            logger.debug(f"No ICD mapping found for condition: '{condition_name}'")
    
    logger.info(f"Extracted {len(icd_updates)} ICD updates from {len(conditions)} conditions")
    return icd_updates


def merge_icd_updates_into_response(
    llm_response: Dict[str, Any],
    pre_extracted_icd_updates: List[Dict[str, Any]],
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Merge pre-extracted ICD updates into LLM response.
    
    Args:
        llm_response: The LLM response dictionary (may have nested experityActions)
        pre_extracted_icd_updates: Pre-extracted ICD updates from deterministic logic
        overwrite: If True, always use pre-extracted ICD updates (recommended).
                   If False, only use pre-extracted if LLM didn't provide any.
        
    Returns:
        Modified response dictionary with merged ICD updates
    """
    # Handle nested structure: response may have experityActions nested
    target = llm_response
    if "experityActions" in llm_response:
        target = llm_response["experityActions"]
    elif "data" in llm_response and "experityActions" in llm_response["data"]:
        target = llm_response["data"]["experityActions"]
    
    if overwrite or "icdUpdates" not in target or not target.get("icdUpdates"):
        target["icdUpdates"] = pre_extracted_icd_updates
        logger.info(f"Merged {len(pre_extracted_icd_updates)} ICD updates into response (overwrite={overwrite})")
    else:
        llm_count = len(target.get("icdUpdates", []))
        logger.info(f"Keeping LLM's ICD updates ({llm_count} items) instead of pre-extracted ({len(pre_extracted_icd_updates)} items)")
    
    return llm_response

