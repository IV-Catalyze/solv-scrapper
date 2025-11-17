import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


def str_to_bool(value: Optional[str]) -> bool:
    """Convert common truthy/falsey strings to boolean."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clean_str(value: Any) -> Optional[str]:
    """Convert a value to a stripped string, or None if empty."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
    else:
        cleaned = str(value).strip()
    return cleaned or None


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """Normalize phone numbers to digits-only string."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


def names_equal(a: Optional[str], b: Optional[str]) -> bool:
    """Case-insensitive comparison of two names (handles None gracefully)."""
    if a is None or b is None:
        return False
    return a.strip().lower() == b.strip().lower()


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize date string to YYYY-MM-DD format."""
    if not date_str or date_str.strip() == "":
        return None

    date_str = date_str.strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def normalize_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Normalize timestamp string to datetime object."""
    if not timestamp_str or timestamp_str.strip() == "":
        return None

    timestamp_str = timestamp_str.strip()

    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue

    return None


STATUS_ALIAS_MAP = {
    "mark_as_ready": "ready",
    "mark_ready": "ready",
    "ready_for_visit": "ready",
    "ready_to_be_seen": "ready",
    "check_in": "checked_in",
    "checkedin": "checked_in",
    "in_room": "in_exam_room",
    "in_room_exam": "in_exam_room",
    "inroom": "in_exam_room",
}


def normalize_status_value(status: Any) -> Optional[str]:
    """Normalize queue status text to lowercase underscore format with known aliases."""
    if status is None:
        return None

    if isinstance(status, str):
        text = status.strip()
    else:
        text = str(status).strip()

    if not text:
        return None

    normalized = text.lower().replace(" ", "_").replace("-", "_")
    return STATUS_ALIAS_MAP.get(normalized, normalized)


def _sanitize_emr_value(value: Any) -> Optional[str]:
    """Convert a raw EMR value into a cleaned string representation."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if value.is_integer():
            text = str(int(value))
        else:
            text = f"{value}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    text = text.strip()
    return text or None


def extract_emr_id(record: Any) -> Optional[str]:
    """
    Attempt to extract an EMR ID from a nested patient payload.
    Prioritises explicit EMR fields, then integration status details,
    then patient match metadata, finally falling back to any key that
    resembles an EMR identifier.
    """
    if not isinstance(record, (dict, list)):
        return None

    candidates: List[Tuple[int, str]] = []
    visited: Set[int] = set()

    priority_fields = (
        ("emr_id", 0),
        ("emrId", 0),
        ("emrID", 0),
        ("emrid", 0),
    )

    def add_candidate(raw: Any, priority: int) -> None:
        cleaned = _sanitize_emr_value(raw)
        if cleaned:
            candidates.append((priority, cleaned))

    def walk(node: Any, depth: int = 0) -> None:
        node_id = id(node)
        if node_id in visited:
            return
        visited.add(node_id)

        if isinstance(node, dict):
            for field, base_priority in priority_fields:
                if field in node:
                    add_candidate(node.get(field), base_priority + depth)

            integration = node.get("integration_status") or node.get("integrationStatus")
            if isinstance(integration, list):
                for item in integration:
                    if isinstance(item, dict):
                        add_candidate(item.get("emr_id") or item.get("emrId"), 2 + depth)
                        requests = item.get("requests")
                        if isinstance(requests, list):
                            for request in requests:
                                if isinstance(request, dict):
                                    add_candidate(
                                        request.get("patient_number")
                                        or request.get("patientNumber")
                                        or request.get("emr_id")
                                        or request.get("emrId"),
                                        6 + depth,
                                    )

            patient_match = node.get("patient_match_details") or node.get("patientMatchDetails")
            if isinstance(patient_match, dict):
                add_candidate(patient_match.get("external_user_profile_id"), 4 + depth)
                add_candidate(
                    patient_match.get("patient_number") or patient_match.get("patientNumber"),
                    7 + depth,
                )

            raw_payload = node.get("raw_payload")
            if isinstance(raw_payload, (dict, list)):
                walk(raw_payload, depth + 1)

            for key, value in node.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in ("emr_id", "emrid")):
                    add_candidate(value, 3 + depth)
                elif key_lower in {"external_user_profile_id", "patient_number", "patientnumber"}:
                    add_candidate(value, 8 + depth)

                if key not in {
                    "integration_status",
                    "integrationStatus",
                    "patient_match_details",
                    "patientMatchDetails",
                    "raw_payload",
                }:
                    if isinstance(value, (dict, list)):
                        walk(value, depth + 1)

        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(record, 0)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def normalize_patient_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize patient record from JSON to database format."""
    emr_id = extract_emr_id(record)

    from datetime import datetime as _dt  # local import to avoid circulars

    normalized: Dict[str, Any] = {
        "emr_id": emr_id.strip() if isinstance(emr_id, str) else emr_id,
        "booking_id": record.get("booking_id") or record.get("bookingId") or None,
        "booking_number": record.get("booking_number") or record.get("bookingNumber") or None,
        "patient_number": record.get("patient_number") or record.get("patientNumber") or None,
        "location_id": record.get("locationId") or record.get("location_id") or None,
        "location_name": record.get("location_name") or record.get("locationName") or None,
        "legal_first_name": record.get("legalFirstName")
        or record.get("legal_first_name")
        or record.get("firstName")
        or None,
        "legal_last_name": record.get("legalLastName")
        or record.get("legal_last_name")
        or record.get("lastName")
        or None,
        "dob": record.get("dob") or record.get("dateOfBirth") or record.get("date_of_birth") or None,
        "mobile_phone": record.get("mobilePhone")
        or record.get("mobile_phone")
        or record.get("phone")
        or None,
        "sex_at_birth": record.get("sexAtBirth")
        or record.get("sex_at_birth")
        or record.get("gender")
        or None,
        "captured_at": normalize_timestamp(record.get("captured_at") or record.get("capturedAt")) or _dt.now(),
        "reason_for_visit": record.get("reasonForVisit")
        or record.get("reason_for_visit")
        or record.get("reason")
        or None,
        "status": normalize_status_value(
            record.get("status")
            or record.get("patient_status")
            or record.get("status_class")
            or record.get("statusLabel")
            or record.get("status_label")
        ),
    }

    for key, value in list(normalized.items()):
        if isinstance(value, str):
            value = value.strip()
            normalized[key] = value or None

    return normalized


def serialize_patient_payload(patient_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON-serializable copy of the patient payload."""
    try:
        return json.loads(json.dumps(patient_data, default=str))
    except (TypeError, ValueError):
        serializable: Dict[str, Any] = {}
        for key, value in patient_data.items():
            if isinstance(value, datetime):
                serializable[key] = value.isoformat()
            else:
                serializable[key] = value
        return serializable


