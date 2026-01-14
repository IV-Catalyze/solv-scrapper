"""Experity mapping utilities - code-based mapping components.

This package provides code-based mapping utilities. The main module functions
are in the parent experity_mapper.py file. This package contains sub-modules
for specific mapping components.
"""

# Import from parent module file to re-export (using importlib to avoid circular import)
import importlib.util
import sys
from pathlib import Path

# Get the parent module file path
_parent_module_path = Path(__file__).parent.parent / "experity_mapper.py"

if _parent_module_path.exists():
    # Load the parent module
    spec = importlib.util.spec_from_file_location("experity_mapper_module", _parent_module_path)
    if spec and spec.loader:
        _parent_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_parent_module)
        
        # Re-export ICD functions from parent module
        extract_icd_updates = _parent_module.extract_icd_updates
        merge_icd_updates_into_response = _parent_module.merge_icd_updates_into_response
        merge_severity_into_complaints = _parent_module.merge_severity_into_complaints
        merge_quality_into_complaints = _parent_module.merge_quality_into_complaints
        merge_onset_into_complaints = _parent_module.merge_onset_into_complaints
        merge_vitals_into_response = _parent_module.merge_vitals_into_response
        merge_guardian_into_response = _parent_module.merge_guardian_into_response
        merge_lab_orders_into_response = _parent_module.merge_lab_orders_into_response

# Export new complaint mappers from this package
from .complaint.severity_mapper import (
    extract_severity,
    extract_severities_from_complaints,
)

from .complaint.quality_mapper import (
    extract_quality,
    extract_qualities_from_complaints,
)

from .complaint.onset_mapper import (
    extract_onset,
    extract_onsets_from_complaints,
)

from .vitals_mapper import (
    extract_vitals,
    calculate_bmi,
    calculate_weight_class,
)

from .guardian_mapper import (
    extract_guardian,
)

from .lab_orders_mapper import (
    extract_lab_orders,
)

__all__ = [
    # ICD functions (re-exported from parent module)
    "extract_icd_updates",
    "merge_icd_updates_into_response",
    "merge_severity_into_complaints",
    "merge_quality_into_complaints",
    "merge_onset_into_complaints",
    "merge_vitals_into_response",
    "merge_guardian_into_response",
    "merge_lab_orders_into_response",
    # Severity mapper
    "extract_severity",
    "extract_severities_from_complaints",
    # Quality mapper
    "extract_quality",
    "extract_qualities_from_complaints",
    # Onset mapper
    "extract_onset",
    "extract_onsets_from_complaints",
    # Vitals mapper
    "extract_vitals",
    "calculate_bmi",
    "calculate_weight_class",
    # Guardian mapper
    "extract_guardian",
    # Lab orders mapper
    "extract_lab_orders",
]
