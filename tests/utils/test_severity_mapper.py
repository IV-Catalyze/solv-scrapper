"""Unit tests for severity mapper."""

import pytest
from app.utils.experity_mapper.complaint.severity_mapper import (
    extract_severity,
    extract_severities_from_complaints,
    MIN_SEVERITY,
    MAX_SEVERITY,
)


class TestExtractSeverity:
    """Test extract_severity function."""
    
    def test_valid_pain_scale(self):
        """Test with valid painScale values."""
        assert extract_severity({"painScale": 0}) == 0
        assert extract_severity({"painScale": 5}) == 5
        assert extract_severity({"painScale": 10}) == 10
        assert extract_severity({"painScale": 7}) == 7
    
    def test_missing_pain_scale(self):
        """Test with missing painScale (should return None)."""
        assert extract_severity({}) is None
        assert extract_severity({"painScale": None}) is None
        assert extract_severity({"description": "pain"}) is None
    
    def test_string_pain_scale(self):
        """Test with string painScale (should convert to int)."""
        assert extract_severity({"painScale": "5"}) == 5
        assert extract_severity({"painScale": "7"}) == 7
        assert extract_severity({"painScale": "0"}) == 0
        assert extract_severity({"painScale": "10"}) == 10
    
    def test_float_pain_scale(self):
        """Test with float painScale (should convert to int)."""
        assert extract_severity({"painScale": 5.0}) == 5
        assert extract_severity({"painScale": 7.5}) == 7  # Truncate
        assert extract_severity({"painScale": 8.9}) == 8  # Truncate
    
    def test_out_of_range_pain_scale(self):
        """Test with out-of-range painScale (should clamp)."""
        assert extract_severity({"painScale": -1}) == MIN_SEVERITY
        assert extract_severity({"painScale": -5}) == MIN_SEVERITY
        assert extract_severity({"painScale": 11}) == MAX_SEVERITY
        assert extract_severity({"painScale": 15}) == MAX_SEVERITY
        assert extract_severity({"painScale": 100}) == MAX_SEVERITY
    
    def test_invalid_pain_scale(self):
        """Test with invalid painScale (should return None)."""
        assert extract_severity({"painScale": "invalid"}) is None
        assert extract_severity({"painScale": []}) is None
        assert extract_severity({"painScale": {}}) is None
    
    def test_non_dict_complaint(self):
        """Test with non-dict complaint (should return None)."""
        assert extract_severity(None) is None
        assert extract_severity([]) is None
        assert extract_severity("not a dict") is None


class TestExtractSeveritiesFromComplaints:
    """Test extract_severities_from_complaints function."""
    
    def test_valid_complaints(self):
        """Test with valid complaints."""
        complaints = [
            {"id": "c1", "painScale": 7},
            {"id": "c2", "painScale": 3},
            {"complaintId": "c3", "painScale": 5},
        ]
        result = extract_severities_from_complaints(complaints)
        assert result == {"c1": 7, "c2": 3, "c3": 5}
    
    def test_missing_ids(self):
        """Test with complaints missing IDs (should use index)."""
        complaints = [
            {"painScale": 7},
            {"painScale": 3},
        ]
        result = extract_severities_from_complaints(complaints)
        assert result == {"0": 7, "1": 3}
    
    def test_mixed_ids_and_indices(self):
        """Test with mix of IDs and missing IDs."""
        complaints = [
            {"id": "c1", "painScale": 7},
            {"painScale": 3},  # No ID, will use index
            {"id": "c3", "painScale": 5},
        ]
        result = extract_severities_from_complaints(complaints)
        assert result == {"c1": 7, "1": 3, "c3": 5}
    
    def test_missing_pain_scale(self):
        """Test with missing painScale (should return None)."""
        complaints = [
            {"id": "c1", "painScale": 7},
            {"id": "c2"},  # Missing painScale
            {"id": "c3", "painScale": None},
        ]
        result = extract_severities_from_complaints(complaints)
        assert result == {"c1": 7, "c2": None, "c3": None}
    
    def test_empty_list(self):
        """Test with empty list."""
        result = extract_severities_from_complaints([])
        assert result == {}
    
    def test_non_list(self):
        """Test with non-list input."""
        result = extract_severities_from_complaints(None)
        assert result == {}
        result = extract_severities_from_complaints({})
        assert result == {}
    
    def test_with_encounter_id(self):
        """Test with encounter ID for logging."""
        complaints = [
            {"id": "c1", "painScale": 7},
        ]
        result = extract_severities_from_complaints(complaints, encounter_id="enc-123")
        assert result == {"c1": 7}
