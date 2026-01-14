"""Unit tests for vitals mapper."""

import pytest
from app.utils.experity_mapper.vitals_mapper import (
    extract_vitals,
    calculate_bmi,
    calculate_weight_class,
    _create_default_vitals,
)


class TestCalculateBMI:
    """Test calculate_bmi function."""
    
    def test_valid_bmi(self):
        """Test BMI calculation with valid inputs."""
        assert calculate_bmi(75, 175) == pytest.approx(24.49, abs=0.01)
        assert calculate_bmi(70, 170) == pytest.approx(24.22, abs=0.01)
        assert calculate_bmi(100, 180) == pytest.approx(30.86, abs=0.01)
    
    def test_invalid_inputs(self):
        """Test BMI calculation with invalid inputs."""
        assert calculate_bmi(0, 175) is None
        assert calculate_bmi(75, 0) is None
        assert calculate_bmi(-10, 175) is None
        assert calculate_bmi(75, -10) is None
        assert calculate_bmi(None, 175) is None
        assert calculate_bmi(75, None) is None


class TestCalculateWeightClass:
    """Test calculate_weight_class function."""
    
    def test_underweight(self):
        """Test weight class for underweight BMI."""
        assert calculate_weight_class(18.0) == "underweight"
        assert calculate_weight_class(15.5) == "underweight"
    
    def test_normal(self):
        """Test weight class for normal BMI."""
        assert calculate_weight_class(20.0) == "normal"
        assert calculate_weight_class(22.5) == "normal"
        assert calculate_weight_class(24.9) == "normal"
    
    def test_overweight(self):
        """Test weight class for overweight BMI."""
        assert calculate_weight_class(25.0) == "overweight"
        assert calculate_weight_class(27.5) == "overweight"
        assert calculate_weight_class(29.9) == "overweight"
    
    def test_obese(self):
        """Test weight class for obese BMI."""
        assert calculate_weight_class(30.0) == "obese"
        assert calculate_weight_class(35.0) == "obese"
        assert calculate_weight_class(40.0) == "obese"
    
    def test_unknown(self):
        """Test weight class for None BMI."""
        assert calculate_weight_class(None) == "unknown"


class TestExtractVitals:
    """Test extract_vitals function."""
    
    def test_basic_extraction(self):
        """Test basic vitals extraction."""
        encounter = {
            "attributes": {
                "gender": "male",
                "ageYears": 35,
                "heightCm": 175,
                "weightKg": 75
            }
        }
        vitals = extract_vitals(encounter)
        assert vitals["gender"] == "male"
        assert vitals["ageYears"] == 35
        assert vitals["heightCm"] == 175
        assert vitals["weightKg"] == 75
        assert vitals["bodyMassIndex"] == pytest.approx(24.49, abs=0.01)
        assert vitals["weightClass"] == "normal"
    
    def test_bmi_calculation(self):
        """Test BMI is calculated correctly."""
        encounter = {
            "attributes": {
                "heightCm": 180,
                "weightKg": 100
            }
        }
        vitals = extract_vitals(encounter)
        assert vitals["bodyMassIndex"] == pytest.approx(30.86, abs=0.01)
        assert vitals["weightClass"] == "obese"
    
    def test_preserve_additional_fields(self):
        """Test that additional fields are preserved."""
        encounter = {
            "attributes": {
                "gender": "male",
                "ageYears": 35,
                "newField": "someValue",
                "anotherField": 123
            }
        }
        vitals = extract_vitals(encounter)
        assert vitals["gender"] == "male"
        assert vitals["ageYears"] == 35
        assert vitals["newField"] == "someValue"
        assert vitals["anotherField"] == 123
    
    def test_missing_attributes(self):
        """Test with missing attributes."""
        encounter = {}
        vitals = extract_vitals(encounter)
        assert vitals["gender"] == "unknown"
        assert vitals["ageYears"] is None
        assert vitals["bodyMassIndex"] is None
        assert vitals["weightClass"] == "unknown"
    
    def test_empty_attributes(self):
        """Test with empty attributes."""
        encounter = {"attributes": {}}
        vitals = extract_vitals(encounter)
        assert vitals["gender"] == "unknown"
        assert vitals["ageYears"] is None
    
    def test_all_vitals_fields(self):
        """Test all vitals fields are extracted."""
        encounter = {
            "attributes": {
                "gender": "female",
                "ageYears": 28,
                "ageMonths": 6,
                "heightCm": 165,
                "weightKg": 60,
                "pulseRateBpm": 72,
                "respirationBpm": 16,
                "bodyTemperatureCelsius": 37.5,
                "bloodPressureSystolicMm": 120,
                "bloodPressureDiastolicMm": 80,
                "pulseOx": 98
            }
        }
        vitals = extract_vitals(encounter)
        assert vitals["gender"] == "female"
        assert vitals["ageYears"] == 28
        assert vitals["ageMonths"] == 6
        assert vitals["heightCm"] == 165
        assert vitals["weightKg"] == 60
        assert vitals["pulseRateBpm"] == 72
        assert vitals["respirationBpm"] == 16
        assert vitals["bodyTemperatureCelsius"] == 37.5
        assert vitals["bloodPressureSystolicMm"] == 120
        assert vitals["bloodPressureDiastolicMm"] == 80
        assert vitals["pulseOx"] == 98
    
    def test_invalid_encounter(self):
        """Test with invalid encounter data."""
        vitals = extract_vitals(None)
        assert vitals["gender"] == "unknown"
        
        vitals = extract_vitals("not a dict")
        assert vitals["gender"] == "unknown"
    
    def test_missing_bmi_fields(self):
        """Test when BMI cannot be calculated."""
        encounter = {
            "attributes": {
                "gender": "male"
            }
        }
        vitals = extract_vitals(encounter)
        assert vitals["bodyMassIndex"] is None
        assert vitals["weightClass"] == "unknown"
