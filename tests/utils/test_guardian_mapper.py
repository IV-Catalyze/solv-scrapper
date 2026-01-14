"""Unit tests for guardian mapper."""

import pytest
from app.utils.experity_mapper.guardian_mapper import (
    extract_guardian,
    _create_default_guardian,
)


class TestExtractGuardian:
    """Test extract_guardian function."""
    
    def test_basic_extraction(self):
        """Test basic guardian extraction."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": True,
                    "guardianName": "John Doe",
                    "relationship": "Father",
                    "notes": "Patient is a minor"
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["guardianName"] == "John Doe"
        assert guardian["relationship"] == "Father"
        assert guardian["notes"] == "Patient is a minor"
    
    def test_preserve_additional_fields(self):
        """Test that additional fields are preserved."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": True,
                    "guardianName": "Jane",
                    "newField": "someValue",
                    "anotherField": 123
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["guardianName"] == "Jane"
        assert guardian["newField"] == "someValue"
        assert guardian["anotherField"] == 123
    
    def test_missing_guardian_data(self):
        """Test with missing guardian data."""
        encounter = {}
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
        assert guardian["guardianName"] is None
        assert guardian["relationship"] is None
        assert guardian["notes"] is None
    
    def test_empty_guardian_data(self):
        """Test with empty guardian data."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {}
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
        assert guardian["guardianName"] is None
    
    def test_present_false(self):
        """Test with present=False."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": False
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
    
    def test_partial_data(self):
        """Test with partial guardian data."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": True,
                    "guardianName": "Parent"
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["guardianName"] == "Parent"
        assert guardian["relationship"] is None
        assert guardian["notes"] is None
    
    def test_invalid_encounter(self):
        """Test with invalid encounter data."""
        guardian = extract_guardian(None)
        assert guardian["present"] is False
        
        guardian = extract_guardian("not a dict")
        assert guardian["present"] is False
    
    def test_missing_additional_questions(self):
        """Test with missing additionalQuestions."""
        encounter = {}
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
    
    def test_non_boolean_present(self):
        """Test that present is converted to boolean."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": 1  # Non-boolean
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
