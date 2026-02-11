#!/usr/bin/env python3
"""
Business logic and service layer functions.

This module contains business logic functions that orchestrate operations:
- Data formatting functions (format_patient_payload, format_encounter_response, etc.)
- Data transformation functions (build_patient_payload, decorate_patient_payload, etc.)
- Business rule implementations (prepare_dashboard_patients, filter_patients_by_search, etc.)
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

# Import utility functions
from app.api.utils import normalize_status, parse_datetime, expand_status_shortcuts
# Import database functions
from app.api.database import fetch_confirmed_records, fetch_pending_records


def format_encounter_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format encounter record for JSON response."""
    formatted = {
        'emr_id': record.get('emr_id', ''),
        'encounter_payload': record.get('encounter_payload', {}),
    }
    
    # Handle encounter_payload JSONB - convert from string if needed
    if formatted.get('encounter_payload'):
        if isinstance(formatted['encounter_payload'], str):
            try:
                formatted['encounter_payload'] = json.loads(formatted['encounter_payload'])
            except json.JSONDecodeError:
                formatted['encounter_payload'] = {}
    
    return formatted


def format_queue_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format queue record for JSON response.
    
    Returns: queue_id, emr_id, status, attempts, encounter_payload (snake_case)
    Similar to format_encounter_response structure.
    FastAPI will serialize using field names (camelCase: queueId, emrId, encounterPayload).
    """
    # Get raw_payload (encounter data) - this becomes encounter_payload
    raw_payload = record.get('raw_payload')
    
    # Handle JSONB field - convert from string if needed
    if raw_payload:
        if isinstance(raw_payload, str):
            try:
                raw_payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                raw_payload = {}
        elif not isinstance(raw_payload, dict):
            raw_payload = {}
    else:
        raw_payload = {}
    
    # Get queue_id - convert UUID to string if needed
    queue_id = record.get('queue_id')
    if queue_id:
        queue_id = str(queue_id)
    
    # Get parsed_payload (internal use - includes experityAction/experityActions)
    parsed_payload = record.get('parsed_payload')
    
    # Handle JSONB field - convert from string if needed
    if parsed_payload:
        if isinstance(parsed_payload, str):
            try:
                parsed_payload = json.loads(parsed_payload)
            except json.JSONDecodeError:
                parsed_payload = None
        elif not isinstance(parsed_payload, dict):
            parsed_payload = None
    else:
        parsed_payload = None
    
    # Format response using snake_case keys (matching format_encounter_response pattern)
    # FastAPI will serialize using field names (camelCase) via response_model
    # Handle emr_id - convert to string if present, otherwise keep as None
    emr_id = record.get('emr_id')
    if emr_id is not None:
        emr_id = str(emr_id)
    
    # Handle timestamps - convert to ISO format strings if present
    created_at = record.get('created_at')
    if created_at:
        if isinstance(created_at, str):
            # Already a string, keep as-is
            created_at_str = created_at
        else:
            # datetime object - convert to ISO format
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = None
    else:
        created_at_str = None
    
    updated_at = record.get('updated_at')
    if updated_at:
        if isinstance(updated_at, str):
            # Already a string, keep as-is
            updated_at_str = updated_at
        else:
            # datetime object - convert to ISO format
            if isinstance(updated_at, datetime):
                updated_at_str = updated_at.isoformat()
            else:
                updated_at_str = None
    else:
        updated_at_str = None
    
    formatted = {
        'queue_id': queue_id,
        'emr_id': emr_id,
        'status': record.get('status', 'PENDING'),
        'attempts': record.get('attempts', 0),
        'encounter_payload': raw_payload,
        'parsed_payload': parsed_payload,  # Include parsed_payload for internal use
        'created_at': created_at_str,  # Add created_at timestamp
        'updated_at': updated_at_str,  # Add updated_at timestamp
    }
    
    return formatted


def format_summary_response(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format summary record for JSON response with camelCase field names."""
    formatted = {
        'id': record.get('id'),
        'emrId': record.get('emr_id', ''),
        'encounterId': record.get('encounter_id', ''),
        'note': record.get('note', ''),
        'createdAt': None,
        'updatedAt': None,
    }
    
    # Convert datetime objects to ISO format strings
    if record.get('created_at'):
        created_at = record['created_at']
        if isinstance(created_at, datetime):
            formatted['createdAt'] = created_at.isoformat()
        elif isinstance(created_at, str):
            formatted['createdAt'] = created_at
    
    if record.get('updated_at'):
        updated_at = record['updated_at']
        if isinstance(updated_at, datetime):
            formatted['updatedAt'] = updated_at.isoformat()
        elif isinstance(updated_at, str):
            formatted['updatedAt'] = updated_at
    
    return formatted


def build_patient_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build patient response payload in normalized structure with camelCase field names."""
    captured = record.get("captured_at")
    if isinstance(captured, datetime):
        captured = captured.isoformat()
    created = record.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    updated = record.get("updated_at")
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    raw_payload = record.get("raw_payload")

    payload = {
        "emrId": record.get("emr_id"),
        "bookingId": record.get("booking_id"),
        "locationId": record.get("location_id"),
        "locationName": record.get("location_name"),
        "legalFirstName": record.get("legal_first_name"),
        "legalLastName": record.get("legal_last_name"),
        "dob": record.get("dob"),
        "mobilePhone": record.get("mobile_phone"),
        "sexAtBirth": record.get("sex_at_birth"),
        "capturedAt": captured,
        "reasonForVisit": record.get("reason_for_visit"),
        "createdAt": created,
        "updatedAt": updated,
    }

    status = record.get("patient_status") or record.get("status")
    if not status and isinstance(raw_payload, dict):
        status = raw_payload.get("status")
    if status:
        payload["status"] = status

    return payload


def decorate_patient_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add presentation-friendly fields to the patient payload."""
    # Note: status_class, status_label, and captured_display are only added
    # for dashboard/list endpoints, not for single patient retrieval
    # This function is kept for backward compatibility with list endpoints
    status_class = normalize_status(payload.get("status")) or "unknown"
    payload["status_class"] = status_class
    payload["status_label"] = status_class.replace("_", " ").title()

    captured_display = None
    captured_raw = payload.get("capturedAt") or payload.get("captured_at")
    captured_dt = parse_datetime(captured_raw)
    if captured_dt > datetime.min:
        captured_display = captured_dt.strftime("%b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")
    payload["captured_display"] = captured_display

    return payload


def prepare_dashboard_patients(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    selected = [normalize_status(status) for status in statuses if normalize_status(status)]
    selected_set = set(selected)
    results: List[Dict[str, Any]] = []

    confirmed_records = fetch_confirmed_records(
        cursor,
        location_id,
        limit,
    )
    for record in confirmed_records:
        payload = build_patient_payload(record)
        status = normalize_status(payload.get("status")) or "confirmed"
        payload["status"] = status
        if selected_set and status not in selected_set:
            continue
        payload["source"] = "confirmed"
        results.append(decorate_patient_payload(payload))

    # Sort by capturedAt descending then updatedAt
    def sort_key(item: Dict[str, Any]):
        captured = parse_datetime(item.get("capturedAt") or item.get("captured_at"))
        updated = parse_datetime(item.get("updatedAt") or item.get("updated_at"))
        return (captured, updated)

    results.sort(key=sort_key, reverse=True)

    if limit is not None:
        results = results[:limit]

    return results


def fetch_pending_payloads(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    selected = [normalize_status(status) for status in statuses if normalize_status(status)]
    selected_set = set(selected)
    records = fetch_pending_records(cursor, location_id, None)
    payloads: List[Dict[str, Any]] = []

    for record in records:
        payload = build_patient_payload(record)
        status = normalize_status(payload.get("status")) or normalize_status(record.get("status")) or "checked_in"
        if selected_set and status not in selected_set:
            continue
        payload["status"] = status
        payload["source"] = "pending"
        payloads.append(decorate_patient_payload(payload))
        if limit is not None and len(payloads) >= limit:
            break

    return payloads


def filter_patients_by_search(
    patients: List[Dict[str, Any]],
    search_query: str,
) -> List[Dict[str, Any]]:
    """
    Filter patients by search query (searches name, EMR ID, and phone number).
    
    Args:
        patients: List of patient dictionaries
        search_query: Search term to match against patient data
        
    Returns:
        Filtered list of patients matching the search query
    """
    if not search_query:
        return patients
    
    search_lower = search_query.lower().strip()
    filtered = []
    
    for patient in patients:
        # Search in name fields
        first_name = (patient.get("legalFirstName") or "").lower()
        last_name = (patient.get("legalLastName") or "").lower()
        full_name = f"{first_name} {last_name}".strip()
        
        # Search in EMR ID (support both camelCase and snake_case for backward compatibility)
        emr_id = (patient.get("emrId") or patient.get("emr_id") or "").lower()
        
        # Search in phone number
        phone = (patient.get("mobilePhone") or "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        
        # Check if search query matches any field
        if (search_lower in first_name or 
            search_lower in last_name or 
            search_lower in full_name or
            search_lower in emr_id or
            search_lower in phone):
            filtered.append(patient)
    
    return filtered


def get_local_patients(
    cursor,
    location_id: Optional[str],
    statuses: List[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Gather patient payloads from the local database (confirmed + pending) to
    mirror the remote API shape.
    """
    confirmed = prepare_dashboard_patients(cursor, location_id, statuses, None)
    pending = fetch_pending_payloads(cursor, location_id, statuses, None)

    combined = confirmed + pending

    def sort_key(item: Dict[str, Any]):
        captured = parse_datetime(item.get("capturedAt") or item.get("captured_at"))
        updated = parse_datetime(item.get("updatedAt") or item.get("updated_at"))
        return (captured, updated)

    combined.sort(key=sort_key, reverse=True)

    if limit is not None:
        combined = combined[:limit]

    return combined


def filter_within_24h(patients: list) -> list:
    """Filter patients to only include those captured within the last 24 hours."""
    cutoff = datetime.now() - timedelta(hours=24)
    
    filtered = []
    for patient in patients:
        captured_at = patient.get("captured_at") or patient.get("capturedAt")
        if captured_at:
            if isinstance(captured_at, str):
                # Parse ISO format timestamp
                try:
                    ts = captured_at.replace("Z", "+00:00")
                    captured_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                except ValueError:
                    captured_dt = None
            elif isinstance(captured_at, datetime):
                captured_dt = captured_at.replace(tzinfo=None) if captured_at.tzinfo else captured_at
            else:
                captured_dt = None
            
            if captured_dt and captured_dt >= cutoff:
                filtered.append(patient)
        # If no captured_at, check created_at as fallback
        else:
            created_at = patient.get("created_at") or patient.get("createdAt")
            if created_at:
                if isinstance(created_at, str):
                    try:
                        ts = created_at.replace("Z", "+00:00")
                        created_dt = datetime.fromisoformat(ts).replace(tzinfo=None)
                    except ValueError:
                        created_dt = None
                elif isinstance(created_at, datetime):
                    created_dt = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
                else:
                    created_dt = None
                
                if created_dt and created_dt >= cutoff:
                    filtered.append(patient)
    return filtered
