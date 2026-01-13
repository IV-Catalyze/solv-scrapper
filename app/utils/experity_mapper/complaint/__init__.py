"""Complaint mapping utilities."""

from .severity_mapper import (
    extract_severity,
    extract_severities_from_complaints,
    DEFAULT_SEVERITY,
    MIN_SEVERITY,
    MAX_SEVERITY,
)

__all__ = [
    "extract_severity",
    "extract_severities_from_complaints",
    "DEFAULT_SEVERITY",
    "MIN_SEVERITY",
    "MAX_SEVERITY",
]
