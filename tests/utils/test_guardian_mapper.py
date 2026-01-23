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
    
    # New string-based format tests
    def test_string_format_no(self):
        """Test string format: guardianAssistedInterview = 'No' → relationship = 'Self'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "No",
                "guardianAssistedInterviewBy": []
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
        assert guardian["relationship"] == "Self"
        assert guardian["guardianName"] is None
        assert guardian["notes"] is None
    
    def test_string_format_no_case_insensitive(self):
        """Test string format: case-insensitive 'no'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "no",
                "guardianAssistedInterviewBy": []
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is False
        assert guardian["relationship"] == "Self"
    
    def test_string_format_yes_empty_array(self):
        """Test string format: 'Yes' with empty array → relationship = 'Other'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": []
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Other"
        assert guardian["guardianName"] is None
        assert guardian["notes"] is None
    
    def test_string_format_yes_mother(self):
        """Test string format: 'Yes' with 'Mother' → relationship = 'Mother'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["Mother"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Mother"
        assert guardian["guardianName"] is None
        assert guardian["notes"] is None
    
    def test_string_format_yes_father(self):
        """Test string format: 'Yes' with 'Father' → relationship = 'Father'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["Father"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Father"
        assert guardian["guardianName"] is None
        assert guardian["notes"] is None
    
    def test_string_format_yes_mother_case_insensitive(self):
        """Test string format: case-insensitive 'mother'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["mother"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Mother"
    
    def test_string_format_yes_father_case_insensitive(self):
        """Test string format: case-insensitive 'father'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["FATHER"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Father"
    
    def test_string_format_yes_other_value(self):
        """Test string format: 'Yes' with other value → relationship = 'Other', guardianName = value."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["Grandmother"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Other"
        assert guardian["guardianName"] == "Grandmother"
        assert guardian["notes"] is None
    
    def test_string_format_yes_other_value_uncle(self):
        """Test string format: 'Yes' with 'Uncle' → relationship = 'Other', guardianName = 'Uncle'."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["Uncle"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Other"
        assert guardian["guardianName"] == "Uncle"
    
    def test_string_format_yes_multiple_values(self):
        """Test string format: 'Yes' with multiple values → uses first value."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": ["Mother", "Father"]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Mother"  # First value
        assert guardian["guardianName"] is None
    
    def test_string_format_yes_missing_array(self):
        """Test string format: 'Yes' with missing guardianAssistedInterviewBy → treated as empty."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes"
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Other"
        assert guardian["guardianName"] is None
    
    def test_string_format_yes_non_list_array(self):
        """Test string format: 'Yes' with non-list guardianAssistedInterviewBy → treated as empty."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "Yes",
                "guardianAssistedInterviewBy": "not a list"
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Other"
        assert guardian["guardianName"] is None
    
    def test_string_format_yes_whitespace_trimming(self):
        """Test string format: whitespace trimming in values."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": "  Yes  ",
                "guardianAssistedInterviewBy": ["  Mother  "]
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["relationship"] == "Mother"
    
    def test_backward_compatibility_object_format(self):
        """Test that object format still works (backward compatibility)."""
        encounter = {
            "additionalQuestions": {
                "guardianAssistedInterview": {
                    "present": True,
                    "guardianName": "John Doe",
                    "relationship": "Father",
                    "notes": "Test notes"
                }
            }
        }
        guardian = extract_guardian(encounter)
        assert guardian["present"] is True
        assert guardian["guardianName"] == "John Doe"
        assert guardian["relationship"] == "Father"
        assert guardian["notes"] == "Test notes"