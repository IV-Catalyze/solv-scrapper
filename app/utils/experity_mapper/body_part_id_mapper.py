"""
Body Part ID Mapper - Assign gender-specific body part IDs based on coordKey and gender.

This module provides deterministic mapping of coordKeys to body part IDs,
with different mappings for male and female patients.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Male body part ID mappings (from user's specification)
MALE_BODY_PART_IDS = {
    # FRONT
    "HEAD_PARENT": 1,
    "NECK_PARENT": 2,
    "CHEST_PARENT": 3,
    "ABD_PARENT": 4,
    "GU_PARENT": 5,
    "R_ELBOW_PARENT": 18,
    "L_ELBOW_PARENT": 19,
    "L_SHOULDER_PARENT": 14,
    "R_SHOULDER_PARENT": 15,
    "L_HAND_PARENT": 22,
    "R_HAND_PARENT": 23,
    "R_FOOT_PARENT": 12,
    "L_FOOT_PARENT": 13,
    "L_UPPER_ARM_PARENT": 16,
    "R_UPPER_ARM_PARENT": 17,
    "L_FOREARM_PARENT": 20,
    "R_FOREARM_PARENT": 21,
    "R_KNEE_PARENT": 9,
    "R_HIP_THIGH_PARENT": 7,
    "L_HIP_THIGH_PARENT": 6,
    "L_KNEE_PARENT": 8,
    "R_LOWER_LEG_PARENT": 11,
    "L_LOWER_LEG_PARENT": 10,
    # BACK
    "BACK_UPPER_PARENT": 24,
    "BACK_R_SCAP_PARENT": 26,
    "BACK_L_SCAP_PARENT": 25,
    "BACK_MID_PARENT": 27,
    "BACK_LOWER_PARENT": 28,
    "BACK_BUTTOCKS_PARENT": 29,
    # Special
    "TOGGLE_FRONT_BACK": None,
}

# Female body part ID mappings
# NOTE: Currently using same as male. Update this if female IDs differ.
FEMALE_BODY_PART_IDS = {
    # FRONT
    "HEAD_PARENT": 1,
    "NECK_PARENT": 2,
    "CHEST_PARENT": 3,
    "ABD_PARENT": 4,
    "GU_PARENT": 5,
    "R_ELBOW_PARENT": 18,
    "L_ELBOW_PARENT": 19,
    "L_SHOULDER_PARENT": 14,
    "R_SHOULDER_PARENT": 15,
    "L_HAND_PARENT": 22,
    "R_HAND_PARENT": 23,
    "R_FOOT_PARENT": 12,
    "L_FOOT_PARENT": 13,
    "L_UPPER_ARM_PARENT": 16,
    "R_UPPER_ARM_PARENT": 17,
    "L_FOREARM_PARENT": 20,
    "R_FOREARM_PARENT": 21,
    "R_KNEE_PARENT": 9,
    "R_HIP_THIGH_PARENT": 7,
    "L_HIP_THIGH_PARENT": 6,
    "L_KNEE_PARENT": 8,
    "R_LOWER_LEG_PARENT": 11,
    "L_LOWER_LEG_PARENT": 10,
    # BACK
    "BACK_UPPER_PARENT": 24,
    "BACK_R_SCAP_PARENT": 26,
    "BACK_L_SCAP_PARENT": 25,
    "BACK_MID_PARENT": 27,
    "BACK_LOWER_PARENT": 28,
    "BACK_BUTTOCKS_PARENT": 29,
    # Special
    "TOGGLE_FRONT_BACK": None,
}

# Child coordKeys that map to parent IDs (for specific body parts like HEAD_SCALP, etc.)
# These use the parent's body part ID
CHILD_TO_PARENT_MAPPING = {
    # Head children -> HEAD_PARENT
    "HEAD_SCALP": "HEAD_PARENT",
    "HEAD_FOREHEAD": "HEAD_PARENT",
    "HEAD_NOSE": "HEAD_PARENT",
    "HEAD_SINUSES": "HEAD_PARENT",
    "HEAD_LEFT_EYE": "HEAD_PARENT",
    "HEAD_RIGHT_EYE": "HEAD_PARENT",
    "HEAD_LEFT_EAR": "HEAD_PARENT",
    "HEAD_RIGHT_EAR": "HEAD_PARENT",
    "HEAD_CHEEK": "HEAD_PARENT",
    "HEAD_LIP": "HEAD_PARENT",
    "HEAD_MOUTH": "HEAD_PARENT",
    "HEAD_TOOTH": "HEAD_PARENT",
    "HEAD_TONGUE": "HEAD_PARENT",
    "HEAD_CHIN": "HEAD_PARENT",
    "HEAD_THROAT": "HEAD_PARENT",
    "HEAD_JAW": "HEAD_PARENT",
    # Neck children -> NECK_PARENT
    "NECK_ANT": "NECK_PARENT",
    "NECK_POST": "NECK_PARENT",
    "NECK_LEFT": "NECK_PARENT",
    "NECK_RIGHT": "NECK_PARENT",
    # Chest children -> CHEST_PARENT
    "CHEST_RIGHT": "CHEST_PARENT",
    "CHEST_CENTER": "CHEST_PARENT",
    "CHEST_LEFT": "CHEST_PARENT",
    "CHEST_R_BREAST": "CHEST_PARENT",
    "CHEST_L_BREAST": "CHEST_PARENT",
    "CHEST_R_NIPPLE": "CHEST_PARENT",
    "CHEST_L_NIPPLE": "CHEST_PARENT",
    # Abdomen children -> ABD_PARENT
    "ABD_EPIGASTRIC": "ABD_PARENT",
    "ABD_WALL": "ABD_PARENT",
    "ABD_LUQ": "ABD_PARENT",
    "ABD_LLQ": "ABD_PARENT",
    "ABD_RUQ": "ABD_PARENT",
    "ABD_RLQ": "ABD_PARENT",
    "ABD_PERIUMB": "ABD_PARENT",
    # Genito-Urinary children -> GU_PARENT (same for both genders)
    "GU_M_PENIS": "GU_PARENT",
    "GU_M_URETHRA": "GU_PARENT",
    "GU_M_SCROTUM": "GU_PARENT",
    "GU_M_R_TESTICLE": "GU_PARENT",
    "GU_M_L_TESTICLE": "GU_PARENT",
    "GU_M_PERINEUM": "GU_PARENT",
    "GU_M_ANUS": "GU_PARENT",
    "GU_M_RECTUM": "GU_PARENT",
    "GU_F_VULVA": "GU_PARENT",
    "GU_F_CLITORIS": "GU_PARENT",
    "GU_F_VAGINA": "GU_PARENT",
    "GU_F_URETHRA": "GU_PARENT",
    "GU_F_PERINEUM": "GU_PARENT",
    "GU_F_ANUS": "GU_PARENT",
    "GU_F_RECTUM": "GU_PARENT",
}


def get_body_part_id(coord_key: Optional[str], gender: Optional[str]) -> Optional[int]:
    """
    Get body part ID for a given coordKey and gender.
    
    Args:
        coord_key: Coordinate key (e.g., "HEAD_PARENT", "CHEST_PARENT")
        gender: Patient gender ("male", "female", or None/unknown)
        
    Returns:
        Body part ID (integer) or None if not found
        
    Examples:
        >>> get_body_part_id("HEAD_PARENT", "male")
        1
        >>> get_body_part_id("CHEST_PARENT", "female")
        3
        >>> get_body_part_id("HEAD_SCALP", "male")
        1
        >>> get_body_part_id("UNKNOWN_KEY", "male")
        None
        >>> get_body_part_id("HEAD_PARENT", None)
        1  # Defaults to female
    """
    if not coord_key:
        return None
    
    # Normalize gender
    gender_lower = (gender or "").lower() if gender else "unknown"
    
    # Map child coordKeys to parent
    actual_coord_key = CHILD_TO_PARENT_MAPPING.get(coord_key, coord_key)
    
    # Select mapping based on gender
    if gender_lower == "male":
        body_part_ids = MALE_BODY_PART_IDS
    elif gender_lower == "female":
        body_part_ids = FEMALE_BODY_PART_IDS
    else:
        # Default to female if gender is unknown (as per user's note)
        logger.debug(f"Unknown gender '{gender}', defaulting to female body part IDs")
        body_part_ids = FEMALE_BODY_PART_IDS
    
    return body_part_ids.get(actual_coord_key)


def merge_body_part_ids_into_complaints(
    llm_response: Dict[str, Any],
    gender: Optional[str] = None,
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Merge gender-specific body part IDs into LLM response complaints.
    
    This function:
    1. Extracts gender from vitals (if not provided)
    2. Updates bodyPartId in each complaint's ui field based on coordKey and gender
    
    Args:
        llm_response: The LLM response dictionary (may have nested experityActions)
        gender: Patient gender (if None, will be extracted from vitals)
        overwrite: If True, always use code-based body part IDs (recommended)
        
    Returns:
        Modified response dictionary with updated body part IDs
        
    Examples:
        >>> response = {
        ...     "experityActions": {
        ...         "vitals": {"gender": "male"},
        ...         "complaints": [{
        ...             "coordKey": "HEAD_PARENT",
        ...             "ui": {"bodyMapClick": {"x": 175, "y": 508}}
        ...         }]
        ...     }
        ... }
        >>> result = merge_body_part_ids_into_complaints(response)
        >>> result["experityActions"]["complaints"][0]["ui"]["bodyPartId"]
        1
    """
    # Handle nested structure
    target = llm_response
    if "experityActions" in llm_response:
        target = llm_response["experityActions"]
    elif "data" in llm_response and "experityActions" in llm_response["data"]:
        target = llm_response["data"]["experityActions"]
    
    # Extract gender from vitals if not provided
    if not gender:
        vitals = target.get("vitals", {})
        if isinstance(vitals, dict):
            gender = vitals.get("gender")
    
    # Update complaints
    complaints = target.get("complaints", [])
    if not isinstance(complaints, list):
        logger.warning("Complaints is not a list, skipping body part ID update")
        return llm_response
    
    updated_count = 0
    for complaint in complaints:
        if not isinstance(complaint, dict):
            continue
        
        coord_key = complaint.get("coordKey")
        ui = complaint.get("ui")
        
        # Always ensure ui is a dict
        if not isinstance(ui, dict):
            ui = {}
            complaint["ui"] = ui
        
        # Get body part ID based on coordKey and gender
        body_part_id = get_body_part_id(coord_key, gender)
        
        if body_part_id is not None:
            if overwrite or "bodyPartId" not in ui:
                ui["bodyPartId"] = body_part_id
                updated_count += 1
                logger.debug(
                    f"Updated bodyPartId: coordKey={coord_key}, gender={gender}, "
                    f"bodyPartId={body_part_id}"
                )
        else:
            # Keep existing bodyPartId if coordKey not found, or set to None
            if overwrite and coord_key:
                ui["bodyPartId"] = None
                logger.debug(f"Could not map coordKey '{coord_key}' to body part ID")
    
    logger.info(
        f"Merged body part IDs into {updated_count} complaints "
        f"(gender={gender}, overwrite={overwrite})"
    )
    
    return llm_response
