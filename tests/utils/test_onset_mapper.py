"""Unit tests for onset mapper."""

import pytest
from app.utils.experity_mapper.complaint.onset_mapper import (
    extract_onset,
    extract_onsets_from_complaints,
)


class TestExtractOnset:
    """Test extract_onset function."""
    
    def test_zero_days(self):
        """Test with durationDays = 0 (should return 'Today')."""
        assert extract_onset({"durationDays": 0}) == "Today"
        assert extract_onset({"durationDays": 0.0}) == "Today"
    
    def test_one_day(self):
        """Test with durationDays = 1 (should return '1 day ago')."""
        assert extract_onset({"durationDays": 1}) == "1 day ago"
        assert extract_onset({"durationDays": 1.0}) == "1 day ago"
    
    def test_multiple_days(self):
        """Test with durationDays > 1 (should return 'N days ago')."""
        assert extract_onset({"durationDays": 2}) == "2 days ago"
        assert extract_onset({"durationDays": 3}) == "3 days ago"
        assert extract_onset({"durationDays": 7}) == "7 days ago"
        assert extract_onset({"durationDays": 30}) == "30 days ago"
    
    def test_float_duration(self):
        """Test with float durationDays (should convert to int)."""
        assert extract_onset({"durationDays": 2.5}) == "2 days ago"
        assert extract_onset({"durationDays": 1.9}) == "1 day ago"
        assert extract_onset({"durationDays": 0.5}) == "Today"
    
    def test_string_duration(self):
        """Test with string durationDays (should convert to int)."""
        assert extract_onset({"durationDays": "1"}) == "1 day ago"
        assert extract_onset({"durationDays": "2"}) == "2 days ago"
        assert extract_onset({"durationDays": "0"}) == "Today"
    
    def test_missing_duration(self):
        """Test with missing durationDays (should return None)."""
        assert extract_onset({}) is None
        assert extract_onset({"description": "pain"}) is None
    
    def test_none_duration(self):
        """Test with durationDays = None (should return None)."""
        assert extract_onset({"durationDays": None}) is None
    
    def test_negative_duration(self):
        """Test with negative durationDays (should return None)."""
        assert extract_onset({"durationDays": -1}) is None
        assert extract_onset({"durationDays": -5}) is None
    
    def test_invalid_duration(self):
        """Test with invalid durationDays (should return None)."""
        assert extract_onset({"durationDays": "invalid"}) is None
        assert extract_onset({"durationDays": []}) is None
        assert extract_onset({"durationDays": {}}) is None
    
    def test_non_dict_complaint(self):
        """Test with non-dict complaint."""
        assert extract_onset(None) is None
        assert extract_onset([]) is None
        assert extract_onset("not a dict") is None


class TestExtractOnsetsFromComplaints:
    """Test extract_onsets_from_complaints function."""
    
    def test_valid_complaints(self):
        """Test with valid complaints."""
        complaints = [
            {"id": "c1", "durationDays": 1},
            {"id": "c2", "durationDays": 0},
            {"id": "c3", "durationDays": 5},
            {"id": "c4"},  # No durationDays
        ]
        result = extract_onsets_from_complaints(complaints)
        assert result["c1"] == "1 day ago"
        assert result["c2"] == "Today"
        assert result["c3"] == "5 days ago"
        assert result["c4"] is None
    
    def test_missing_ids(self):
        """Test with complaints missing IDs (should use index)."""
        complaints = [
            {"durationDays": 1},
            {"durationDays": 2},
            {"durationDays": 0},
        ]
        result = extract_onsets_from_complaints(complaints)
        assert result["0"] == "1 day ago"
        assert result["1"] == "2 days ago"
        assert result["2"] == "Today"
    
    def test_mixed_ids_and_indices(self):
        """Test with mix of IDs and missing IDs."""
        complaints = [
            {"id": "c1", "durationDays": 1},
            {"durationDays": 2},  # No ID, will use index
            {"id": "c3", "durationDays": 0},
        ]
        result = extract_onsets_from_complaints(complaints)
        assert result["c1"] == "1 day ago"
        assert result["1"] == "2 days ago"
        assert result["c3"] == "Today"
    
    def test_all_missing_duration(self):
        """Test with all complaints missing durationDays."""
        complaints = [
            {"id": "c1", "description": "pain"},
            {"id": "c2", "description": "ache"},
        ]
        result = extract_onsets_from_complaints(complaints)
        assert result["c1"] is None
        assert result["c2"] is None
    
    def test_empty_list(self):
        """Test with empty list."""
        result = extract_onsets_from_complaints([])
        assert result == {}
    
    def test_non_list(self):
        """Test with non-list input."""
        result = extract_onsets_from_complaints(None)
        assert result == {}
        result = extract_onsets_from_complaints({})
        assert result == {}
    
    def test_with_encounter_id(self):
        """Test with encounter ID for logging."""
        complaints = [
            {"id": "c1", "durationDays": 1},
        ]
        result = extract_onsets_from_complaints(complaints, encounter_id="enc-123")
        assert result == {"c1": "1 day ago"}
    
    def test_various_durations(self):
        """Test with various duration values."""
        complaints = [
            {"id": "c1", "durationDays": 0},
            {"id": "c2", "durationDays": 1},
            {"id": "c3", "durationDays": 2},
            {"id": "c4", "durationDays": 7},
            {"id": "c5", "durationDays": 30},
            {"id": "c6", "durationDays": None},
            {"id": "c7"},  # Missing
        ]
        result = extract_onsets_from_complaints(complaints)
        assert result["c1"] == "Today"
        assert result["c2"] == "1 day ago"
        assert result["c3"] == "2 days ago"
        assert result["c4"] == "7 days ago"
        assert result["c5"] == "30 days ago"
        assert result["c6"] is None
        assert result["c7"] is None
