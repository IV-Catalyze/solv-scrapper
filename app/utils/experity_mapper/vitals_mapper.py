"""
Vitals Mapper - Extract and map vitals from encounter attributes.

This module provides deterministic extraction of vitals from encounter attributes,
with a preserve-all-fields approach to ensure no data is lost.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def calculate_bmi(weight_kg: float, height_cm: float) -> Optional[float]:
    """
    Calculate Body Mass Index (BMI) from weight and height.
    
    Formula: BMI = weight (kg) / (height (m))²
    Height is converted from cm to meters.
    
    Args:
        weight_kg: Weight in kilograms
        height_cm: Height in centimeters
        
    Returns:
        BMI value (rounded to 2 decimal places) or None if invalid
    """
    if not weight_kg or not height_cm or weight_kg <= 0 or height_cm <= 0:
        return None
    
    try:
        height_m = height_cm / 100.0
        bmi = weight_kg / (height_m ** 2)
        return round(bmi, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_weight_class(bmi: Optional[float]) -> str:
    """
    Calculate weight class from BMI.
    
    Classification:
    - BMI < 18.5: "underweight"
    - 18.5 <= BMI < 25: "normal"
    - 25 <= BMI < 30: "overweight"
    - BMI >= 30: "obese"
    - BMI is None: "unknown"
    
    Args:
        bmi: Body Mass Index value
        
    Returns:
        Weight class string
    """
    if bmi is None:
        return "unknown"
    
    if bmi < 18.5:
        return "underweight"
    elif bmi < 25:
        return "normal"
    elif bmi < 30:
        return "overweight"
    else:
        return "obese"


def extract_vitals(encounter_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract vitals from encounter attributes.
    
    Strategy (preserve-all-fields):
    1. Start with source attributes (preserves ALL fields including unknown ones)
    2. Map known fields explicitly (overwrites with mapped/calculated values)
    3. Additional fields are automatically preserved
    
    Known fields mapped:
    - gender, ageYears, ageMonths, heightCm, weightKg
    - pulseRateBpm, respirationBpm, bodyTemperatureCelsius
    - bloodPressureSystolicMm, bloodPressureDiastolicMm, pulseOx
    
    Calculated fields:
    - bodyMassIndex: Calculated from weightKg and heightCm
    - weightClass: Calculated from bodyMassIndex
    
    Args:
        encounter_data: Encounter dictionary with attributes field
        
    Returns:
        Vitals dictionary with all fields from source plus calculated fields
        
    Examples:
        >>> extract_vitals({"attributes": {"gender": "male", "ageYears": 35}})
        {"gender": "male", "ageYears": 35, "bodyMassIndex": None, ...}
        
        >>> extract_vitals({"attributes": {"gender": "male", "heightCm": 175, "weightKg": 75, "newField": "value"}})
        {"gender": "male", "heightCm": 175, "weightKg": 75, "bodyMassIndex": 24.49, 
         "weightClass": "normal", "newField": "value", ...}
    """
    if not isinstance(encounter_data, dict):
        logger.warning("Encounter data is not a dict, returning default vitals")
        return _create_default_vitals()
    
    attributes = encounter_data.get("attributes", {})
    if not isinstance(attributes, dict):
        logger.warning("Attributes is not a dict, returning default vitals")
        return _create_default_vitals()
    
    if not attributes:
        logger.debug("No attributes found, returning default vitals")
        return _create_default_vitals()
    
    # Start with source attributes (preserves ALL fields including unknown ones)
    vitals = dict(attributes)
    
    # Map known fields explicitly (ensures correct field names and types)
    known_field_mappings = {
        "gender": attributes.get("gender"),
        "ageYears": attributes.get("ageYears"),
        "ageMonths": attributes.get("ageMonths"),
        "heightCm": attributes.get("heightCm"),
        "weightKg": attributes.get("weightKg"),
        "pulseRateBpm": attributes.get("pulseRateBpm"),
        "respirationBpm": attributes.get("respirationBpm"),
        "bodyTemperatureCelsius": attributes.get("bodyTemperatureCelsius"),
        "bloodPressureSystolicMm": attributes.get("bloodPressureSystolicMm"),
        "bloodPressureDiastolicMm": attributes.get("bloodPressureDiastolicMm"),
        "pulseOx": attributes.get("pulseOx"),
    }
    
    # Update with mapped values (preserves additional fields)
    vitals.update(known_field_mappings)
    
    # Calculate derived fields (BMI and weight class)
    weight_kg = vitals.get("weightKg")
    height_cm = vitals.get("heightCm")
    
    if weight_kg is not None and height_cm is not None:
        try:
            weight_float = float(weight_kg)
            height_float = float(height_cm)
            bmi = calculate_bmi(weight_float, height_float)
            if bmi is not None:
                vitals["bodyMassIndex"] = bmi
                vitals["weightClass"] = calculate_weight_class(bmi)
                logger.debug(f"Calculated BMI: {bmi}, weight class: {vitals['weightClass']}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to calculate BMI: {e}")
            vitals["bodyMassIndex"] = None
            vitals["weightClass"] = "unknown"
    else:
        vitals["bodyMassIndex"] = None
        vitals["weightClass"] = "unknown"
    
    # Ensure gender has a default if missing
    if not vitals.get("gender"):
        vitals["gender"] = "unknown"
    
    # Log preserved additional fields
    known_fields = set(known_field_mappings.keys()) | {"bodyMassIndex", "weightClass"}
    additional_fields = set(vitals.keys()) - known_fields
    if additional_fields:
        logger.debug(f"Preserved additional fields from attributes: {additional_fields}")
    
    return vitals


def _create_default_vitals() -> Dict[str, Any]:
    """
    Create default vitals structure.
    
    Returns:
        Dictionary with default vitals values
    """
    return {
        "gender": "unknown",
        "ageYears": None,
        "ageMonths": None,
        "heightCm": None,
        "weightKg": None,
        "bodyMassIndex": None,
        "weightClass": "unknown",
        "pulseRateBpm": None,
        "respirationBpm": None,
        "bodyTemperatureCelsius": None,
        "bloodPressureSystolicMm": None,
        "bloodPressureDiastolicMm": None,
        "pulseOx": None,
    }
