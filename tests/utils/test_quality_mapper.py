"""Unit tests for quality mapper."""

import pytest
from app.utils.experity_mapper.complaint.quality_mapper import (
    extract_quality,
    extract_qualities_from_complaints,
    _normalize_quality_value,
)


class TestNormalizeQualityValue:
    """Test _normalize_quality_value function."""
    
    def test_valid_string(self):
        """Test with valid string values."""
        assert _normalize_quality_value("Sharp") == "Sharp"
        assert _normalize_quality_value("sharp") == "Sharp"
        assert _normalize_quality_value("DULL") == "Dull"
        assert _normalize_quality_value("  Pressure  ") == "Pressure"
    
    def test_invalid_values(self):
        """Test with invalid values."""
        assert _normalize_quality_value(None) is None
        assert _normalize_quality_value("") is None
        assert _normalize_quality_value(123) is None  # Numbers not valid
        assert _normalize_quality_value([]) is None


class TestExtractQuality:
    """Test extract_quality function."""
    
    def test_from_pain_quality(self):
        """Test extraction from painQuality field."""
        assert extract_quality({"painQuality": "Sharp"}) == ["Sharp"]
        assert extract_quality({"painQuality": "dull"}) == ["Dull"]
        assert extract_quality({"painQuality": "Pressure"}) == ["Pressure"]
    
    def test_from_quality_field_list(self):
        """Test extraction from quality field (list)."""
        assert extract_quality({"quality": ["Sharp", "Dull"]}) == ["Sharp", "Dull"]
        assert extract_quality({"quality": ["Sharp"]}) == ["Sharp"]
    
    def test_from_quality_field_string(self):
        """Test extraction from quality field (string)."""
        assert extract_quality({"quality": "Sharp"}) == ["Sharp"]
        assert extract_quality({"quality": "dull"}) == ["Dull"]
    
    def test_from_description_returns_empty(self):
        """Test that description is NOT used for extraction."""
        # Description should be ignored - only explicit fields are used
        assert extract_quality({"description": "sharp chest pain"}) == []
        assert extract_quality({"description": "dull ache"}) == []
        assert extract_quality({"description": "chest pressure"}) == []
    
    def test_priority_order(self):
        """Test that painQuality and quality are both extracted."""
        result = extract_quality({
            "painQuality": "Sharp",
            "quality": "Dull"
        })
        # Should include both painQuality and quality
        assert "Sharp" in result
        assert "Dull" in result
    
    def test_no_quality_found(self):
        """Test with no quality (should return empty array)."""
        assert extract_quality({"description": "chest pain"}) == []
        assert extract_quality({}) == []
        assert extract_quality({"description": "headache"}) == []
    
    def test_multiple_sources(self):
        """Test combining quality from painQuality and quality field."""
        result = extract_quality({
            "painQuality": "Sharp",
            "quality": "Burning"
        })
        # Should include both
        assert "Sharp" in result
        assert "Burning" in result
    
    def test_non_dict_complaint(self):
        """Test with non-dict complaint."""
        assert extract_quality(None) == []
        assert extract_quality([]) == []
        assert extract_quality("not a dict") == []
    
    def test_duplicate_removal(self):
        """Test that duplicates are removed."""
        result = extract_quality({
            "painQuality": "Sharp",
            "quality": "Sharp"
        })
        assert result == ["Sharp"]  # Should only appear once


class TestExtractQualitiesFromComplaints:
    """Test extract_qualities_from_complaints function."""
    
    def test_valid_complaints(self):
        """Test with valid complaints."""
        complaints = [
            {"id": "c1", "painQuality": "Sharp"},
            {"id": "c2", "quality": "Dull"},
            {"id": "c3", "description": "burning pain"},  # No quality field
        ]
        result = extract_qualities_from_complaints(complaints)
        assert result["c1"] == ["Sharp"]
        assert result["c2"] == ["Dull"]
        assert result["c3"] == []  # No quality field, returns empty
    
    def test_missing_ids(self):
        """Test with complaints missing IDs (should use index)."""
        complaints = [
            {"painQuality": "Sharp"},
            {"quality": "Dull"},
        ]
        result = extract_qualities_from_complaints(complaints)
        assert result["0"] == ["Sharp"]
        assert result["1"] == ["Dull"]
    
    def test_mixed_ids_and_indices(self):
        """Test with mix of IDs and missing IDs."""
        complaints = [
            {"id": "c1", "painQuality": "Sharp"},
            {"quality": "Dull"},  # No ID, will use index
            {"id": "c3", "quality": "Pressure"},
        ]
        result = extract_qualities_from_complaints(complaints)
        assert result["c1"] == ["Sharp"]
        assert result["1"] == ["Dull"]
        assert result["c3"] == ["Pressure"]
    
    def test_no_quality_found(self):
        """Test with complaints that have no quality."""
        complaints = [
            {"id": "c1", "description": "chest pain"},
            {"id": "c2", "description": "headache"},
        ]
        result = extract_qualities_from_complaints(complaints)
        assert result["c1"] == []
        assert result["c2"] == []
    
    def test_empty_list(self):
        """Test with empty list."""
        result = extract_qualities_from_complaints([])
        assert result == {}
    
    def test_non_list(self):
        """Test with non-list input."""
        result = extract_qualities_from_complaints(None)
        assert result == {}
        result = extract_qualities_from_complaints({})
        assert result == {}
    
    def test_with_encounter_id(self):
        """Test with encounter ID for logging."""
        complaints = [
            {"id": "c1", "painQuality": "Sharp"},
        ]
        result = extract_qualities_from_complaints(complaints, encounter_id="enc-123")
        assert result == {"c1": ["Sharp"]}
