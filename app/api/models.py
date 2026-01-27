#!/usr/bin/env python3
"""
Pydantic models for API request and response validation.

This module contains all Pydantic BaseModel classes used for:
- Request body validation (e.g., PatientCreateRequest, EncounterCreateRequest)
- Response model definitions (e.g., PatientPayload, EncounterResponse)
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator


class PatientPayload(BaseModel):
    """Schema describing the normalized patient payload returned by the API."""

    emrId: Optional[str] = Field(None, description="EMR identifier for the patient.", alias="emr_id")
    bookingId: Optional[str] = Field(None, description="Internal booking identifier.", alias="booking_id")
    locationId: Optional[str] = Field(None, description="Unique identifier for the clinic location.", alias="location_id")
    locationName: Optional[str] = Field(None, description="Display name of the clinic location.", alias="location_name")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.")
    dob: Optional[str] = Field(None, description="Date of birth in ISO 8601 format.")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.")
    capturedAt: Optional[str] = Field(None, description="Timestamp indicating when the record was captured.", alias="captured_at")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.")
    createdAt: Optional[str] = Field(None, description="Record creation timestamp.", alias="created_at")
    updatedAt: Optional[str] = Field(None, description="Record last update timestamp.", alias="updated_at")
    status: Optional[str] = Field(None, description="Current queue status for the patient.")

    class Config:
        extra = "allow"
        populate_by_name = True


# Patient data submission models
class PatientCreateRequest(BaseModel):
    """Request model for creating a single patient record."""
    emrId: str = Field(..., description="EMR identifier for the patient (required).", example="EMR12345", alias="emr_id")
    bookingId: Optional[str] = Field(None, description="Internal booking identifier.", example="0Pa1Z6", alias="booking_id")
    locationId: Optional[str] = Field(None, description="Unique identifier for the clinic location (required for new patients).", example="AXjwbE", alias="location_id")
    locationName: Optional[str] = Field(None, description="Display name of the clinic location.", example="Demo Clinic", alias="location_name")
    legalFirstName: Optional[str] = Field(None, description="Patient legal first name.", example="John")
    legalLastName: Optional[str] = Field(None, description="Patient legal last name.", example="Doe")
    dob: Optional[str] = Field(None, description="Date of birth in ISO 8601 format.", example="1990-01-15")
    mobilePhone: Optional[str] = Field(None, description="Primary phone number on file.", example="+1234567890")
    sexAtBirth: Optional[str] = Field(None, description="Sex at birth or recorded gender marker.", example="M")
    reasonForVisit: Optional[str] = Field(None, description="Reason provided for the visit.", example="Annual checkup")
    status: Optional[str] = Field(None, description="Current queue status for the patient.", example="confirmed")
    capturedAt: Optional[str] = Field(None, description="Timestamp indicating when the record was captured in ISO 8601 format.", example="2025-11-21T10:30:00Z", alias="captured_at")
    createdAt: Optional[str] = Field(None, description="Record creation timestamp in ISO 8601 format.", example="2025-11-21T10:30:00Z", alias="created_at")
    updatedAt: Optional[str] = Field(None, description="Record last update timestamp in ISO 8601 format.", example="2025-11-21T10:30:00Z", alias="updated_at")
    
    class Config:
        populate_by_name = True
        extra = "allow"
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "locationId": "AXjwbE",
                "locationName": "Demo Clinic",
                "legalFirstName": "John",
                "legalLastName": "Doe",
                "dob": "1990-01-15",
                "mobilePhone": "+1234567890",
                "sexAtBirth": "M",
                "capturedAt": "2025-11-21T10:30:00Z",
                "reasonForVisit": "Annual checkup",
                "createdAt": "2025-11-21T10:30:00Z",
                "updatedAt": "2025-11-21T10:30:00Z",
                "status": "confirmed"
            }
        }
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        # Generate schema with by_alias=False to use field names (camelCase)
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class PatientBatchRequest(BaseModel):
    """Request model for creating multiple patient records."""
    patients: List[PatientCreateRequest] = Field(..., description="List of patient records to create.")


class StatusUpdateRequest(BaseModel):
    """Request model for updating patient status."""
    status: str = Field(..., description="New queue status for the patient. Common values: confirmed, checked_in, pending, completed, cancelled.", example="checked_in")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "checked_in"
            }
        }


# Encounter data submission models
class EncounterCreateRequest(BaseModel):
    """Request model for creating an encounter record."""
    emrId: str = Field(
        ..., 
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    encounterPayload: Dict[str, Any] = Field(
        ..., 
        description="Full encounter JSON payload. Must contain 'id' or 'encounterId' field to identify the encounter.",
        example={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
            "attributes": {"gender": "male", "ageYears": 69},
            "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
            "status": "COMPLETE"
        },
        alias="encounter_payload"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "encounterPayload": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                    "attributes": {"gender": "male", "ageYears": 69},
                    "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
                    "status": "COMPLETE"
                }
            }
        }


class EncounterResponse(BaseModel):
    """Response model for encounter records."""
    emrId: str = Field(
        ..., 
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    encounterPayload: Dict[str, Any] = Field(
        ..., 
        description="Full encounter JSON payload as stored",
        alias="encounter_payload"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "encounterPayload": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                    "attributes": {"gender": "male", "ageYears": 69},
                    "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
                    "status": "COMPLETE"
                }
            }
        }


# Queue data submission models
class QueueUpdateRequest(BaseModel):
    """Request model for updating queue entry."""
    queue_id: Optional[str] = Field(None, description="Queue identifier (UUID). Either queue_id or encounter_id must be provided.", example="660e8400-e29b-41d4-a716-446655440000")
    encounter_id: Optional[str] = Field(None, description="Encounter identifier (UUID). Either queue_id or encounter_id must be provided.", example="550e8400-e29b-41d4-a716-446655440000")
    experityAction: Optional[List[Dict[str, Any]]] = Field(None, description="Array of Experity action objects to store in parsed_payload.")
    
    @model_validator(mode='after')
    def validate_at_least_one_identifier(self):
        """Ensure at least one identifier is provided."""
        if not self.queue_id and not self.encounter_id:
            raise ValueError('Either queue_id or encounter_id must be provided.')
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "encounter_id": "550e8400-e29b-41d4-a716-446655440000",
                "experityAction": [
                    {
                        "action": "UPDATE_VITALS",
                        "data": {
                            "temperature": 98.6,
                            "bloodPressure": "120/80"
                        }
                    }
                ]
            }
        }
        extra = "forbid"


class QueueStatusUpdateRequest(BaseModel):
    """Request model for updating queue entry status."""
    status: str = Field(..., description="New queue status: PENDING, PROCESSING, DONE, or ERROR", example="DONE")
    errorMessage: Optional[str] = Field(None, description="Error message to store (for ERROR status)", example="Processing failed", alias="error_message")
    incrementAttempts: Optional[bool] = Field(False, description="Whether to increment the attempts counter", example=False, alias="increment_attempts")
    experityActions: Optional[Dict[str, Any]] = Field(None, description="Experity actions to store in parsed_payload (for DONE status)", alias="experity_actions")
    dlq: Optional[bool] = Field(None, description="Mark for Dead Letter Queue (for ERROR status)", example=False)
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "status": "DONE",
                "experityActions": {
                    "vitals": {},
                    "complaints": []
                }
            }
        }
        extra = "forbid"


class QueueRequeueRequest(BaseModel):
    """Request model for requeuing a queue entry."""
    status: Optional[str] = Field("PENDING", description="New queue status (default: PENDING)", example="PENDING")
    priority: Optional[str] = Field("HIGH", description="Priority level: HIGH, NORMAL, or LOW", example="HIGH")
    errorMessage: Optional[str] = Field(None, description="Optional error message", example="Requeued for retry", alias="error_message")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "status": "PENDING",
                "priority": "HIGH",
                "errorMessage": "Requeued for retry"
            }
        }
        extra = "forbid"


class QueueResponse(BaseModel):
    """Response model for queue records."""
    queueId: Optional[str] = Field(
        None,
        description="Queue identifier (UUID)",
        example="660e8400-e29b-41d4-a716-446655440000",
        alias="queue_id"
    )
    emrId: Optional[str] = Field(
        None,
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id"
    )
    status: str = Field(..., description="Queue status: PENDING, PROCESSING, DONE, or ERROR.")
    attempts: int = Field(default=0, description="Number of processing attempts.")
    encounterPayload: Dict[str, Any] = Field(
        ..., 
        description="Full encounter JSON payload (raw_payload from queue)",
        alias="encounter_payload"
    )
    parsedPayload: Optional[Dict[str, Any]] = Field(
        None,
        description="Parsed payload containing experityAction/experityActions (internal use)",
        alias="parsed_payload"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "queueId": "660e8400-e29b-41d4-a716-446655440000",
                "emrId": "EMR12345",
                "status": "PENDING",
                "attempts": 0,
                "encounterPayload": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "clientId": "fb5f549a-11e5-4e2d-9347-9fc41bc59424",
                    "traumaType": "BURN",
                    "chiefComplaints": [{"id": "00f9612e-f37d-451b-9172-25cbddee58a9", "description": "cough"}],
                    "status": "COMPLETE"
                },
                "parsedPayload": {
                    "experityAction": []
                }
            }
        }
        extra = "allow"


# Experity mapping endpoint models
class ExperityMapRequest(BaseModel):
    """Request model for mapping queue entry to Experity actions via Azure AI.
    
    Supports two input formats:
    1. Queue entry wrapper: 
       - snake_case: {"queue_entry": {"encounter_id": "...", "queue_id": "...", "raw_payload": {...}}}
       - camelCase: {"queue_entry": {"encounterId": "...", "queueId": "...", "encounterPayload": {...}}}
       - Mixed: {"queue_entry": {"queueId": "...", "encounterPayload": {"id": "..."}}}
    2. Direct encounter object: {"id": "...", "clientId": "...", "attributes": {...}, ...}
    
    Field name variants supported:
    - queue_id / queueId
    - encounter_id / encounterId / encounterPayload.id
    - raw_payload / rawPayload / encounterPayload
    """
    queue_entry: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Queue entry wrapper. Supports both snake_case and camelCase field names. "
                   "Must contain either encounter_id/encounterId/encounterPayload.id or queue_id/queueId. "
                   "Optionally includes raw_payload/rawPayload/encounterPayload (will be fetched from database if not provided)."
    )
    
    # Allow root-level fields for direct encounter format
    class Config:
        extra = "allow"
    
    @field_validator("queue_entry")
    @classmethod
    def validate_queue_entry(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate queue entry has required fields if provided.
        
        Either encounter_id/encounterId or queue_id/queueId must be provided in queue_entry.
        Also supports encounterPayload.id as a source for encounter_id.
        raw_payload/rawPayload/encounterPayload is optional - if not provided, will be fetched from database.
        """
        if v is None:
            return v
        
        if not isinstance(v, dict):
            raise ValueError("queue_entry must be a dictionary")
        
        # Check for queue_id or queueId (snake_case or camelCase)
        has_queue_id = v.get("queue_id") or v.get("queueId")
        
        # Check for encounter_id or encounterId (snake_case or camelCase)
        has_encounter_id = v.get("encounter_id") or v.get("encounterId")
        
        # Also check if encounterPayload.id exists (common from GET /queue responses)
        if not has_encounter_id:
            encounter_payload = v.get("encounterPayload") or v.get("encounter_payload")
            if encounter_payload and isinstance(encounter_payload, dict):
                has_encounter_id = (
                    encounter_payload.get("id") or 
                    encounter_payload.get("encounterId") or 
                    encounter_payload.get("encounter_id")
                )
        
        # Either encounter_id or queue_id must be provided (in any supported format)
        if not has_encounter_id and not has_queue_id:
            raise ValueError(
                "queue_entry must contain either 'encounter_id'/'encounterId' or 'queue_id'/'queueId' "
                "(or 'encounterPayload.id' for encounter identifier)"
            )
        
        # raw_payload is optional - will be fetched from DB if not provided
        # This allows the endpoint to work with GET /queue responses (encounterPayload)
        
        return v


class ExperityAction(BaseModel):
    """Model for a single Experity action."""
    template: str = Field(..., description="Template name.")
    bodyAreaKey: str = Field(..., description="Body area key.")
    coordKey: Optional[str] = Field(None, description="Coordinate key.")
    bodyMapSide: Optional[str] = Field(None, description="Body map side (front/back).")
    ui: Optional[Dict[str, Any]] = Field(None, description="UI data including bodyMapClick coordinates.")
    mainProblem: str = Field(..., description="Main problem description.")
    notesTemplateKey: Optional[str] = Field(None, description="Notes template key.")
    notesPayload: Optional[Dict[str, Any]] = Field(None, description="Notes payload data.")
    reasoning: Optional[str] = Field(None, description="Reasoning for the mapping.")
    
    class Config:
        extra = "allow"


class ExperityMapResponse(BaseModel):
    """Response model for Experity mapping endpoint."""
    success: bool = Field(..., description="Whether the mapping was successful.")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data containing experityActions.")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if success is false.")
    
    class Config:
        extra = "allow"


# Summary data submission models
class SummaryRequest(BaseModel):
    """Request model for creating or updating a summary record.

    At least one of emrId or encounterId must be provided.
    """
    emrId: Optional[str] = Field(
        None,
        description="EMR identifier for the patient",
        example="EMR12345",
        alias="emr_id",
    )
    encounterId: Optional[str] = Field(
        None,
        description="Encounter identifier (UUID) for the encounter",
        example="550e8400-e29b-41d4-a716-446655440000",
        alias="encounter_id",
    )
    note: str = Field(
        ...,
        description="Summary note text containing clinical information",
        example="Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
    )

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "emrId": "EMR12345",
                "encounterId": "550e8400-e29b-41d4-a716-446655440000",
                "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
            }
        }

    @model_validator(mode="after")
    def validate_ids(self) -> "SummaryRequest":
        """Ensure at least one of emrId or encounterId is provided."""
        if not self.emrId and not self.encounterId:
            raise ValueError("Either emrId or encounterId must be provided.")
        return self

    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        # Generate schema with by_alias=False to use field names (camelCase)
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class SummaryResponse(BaseModel):
    """Response model for summary records."""
    id: int = Field(..., description="Unique identifier for the summary record", example=123)
    emrId: str = Field(..., description="EMR identifier for the patient", example="EMR12345", alias="emr_id")
    encounterId: str = Field(..., description="Encounter identifier (UUID) for the encounter", example="550e8400-e29b-41d4-a716-446655440000", alias="encounter_id")
    note: str = Field(..., description="Summary note text", example="Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.")
    createdAt: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was created", example="2025-11-21T10:30:00Z", alias="created_at")
    updatedAt: Optional[str] = Field(None, description="ISO 8601 timestamp when the record was last updated", example="2025-11-21T10:30:00Z", alias="updated_at")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "emrId": "EMR12345",
                "encounterId": "550e8400-e29b-41d4-a716-446655440000",
                "note": "Patient is a 69 year old male presenting with fever and cough. Vital signs stable. Recommended follow-up in 3 days.",
                "createdAt": "2025-11-21T10:30:00Z",
                "updatedAt": "2025-11-21T10:30:00Z"
            }
        }
        extra = "allow"
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        # Generate schema with by_alias=False to use field names (camelCase) matching model_dump(by_alias=False)
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class VmHeartbeatRequest(BaseModel):
    """Request model for VM heartbeat."""
    vmId: str = Field(
        ..., 
        description="VM identifier",
        example="server1-vm1",
        alias="vm_id"
    )
    serverId: Optional[str] = Field(
        None,
        description="Server identifier",
        example="server1",
        alias="server_id"
    )
    status: str = Field(
        ..., 
        description="VM status: healthy, unhealthy, or idle",
        example="healthy",
    )
    processingQueueId: Optional[str] = Field(
        None,
        description="Optional queue ID that the VM is currently processing",
        example="660e8400-e29b-41d4-a716-446655440000",
        alias="processing_queue_id"
    )
    uiPathStatus: Optional[str] = Field(
        None,
        description="UiPath status: running, stopped, error, etc.",
        example="running",
        alias="uipath_status"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional metadata object with system metrics",
        example={
            "cpuUsage": 45.2,
            "memoryUsage": 62.8,
            "diskUsage": 30.1
        }
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "vmId": "server1-vm1",
                "serverId": "server1",
                "status": "healthy",
                "processingQueueId": "660e8400-e29b-41d4-a716-446655440000",
                "uiPathStatus": "running",
                "metadata": {
                    "cpuUsage": 45.2,
                    "memoryUsage": 62.8,
                    "diskUsage": 30.1
                }
            }
        }
        extra = "forbid"


class VmHeartbeatResponse(BaseModel):
    """Response model for VM heartbeat."""
    success: bool = Field(..., description="Whether the heartbeat was processed successfully", example=True)
    vmId: str = Field(..., description="VM identifier", example="server1-vm1", alias="vm_id")
    serverId: Optional[str] = Field(None, description="Server identifier", example="server1", alias="server_id")
    lastHeartbeat: str = Field(..., description="ISO 8601 timestamp of the last heartbeat", example="2025-01-22T10:30:00Z", alias="last_heartbeat")
    status: str = Field(..., description="Current VM status", example="healthy")
    uiPathStatus: Optional[str] = Field(None, description="UiPath status", example="running", alias="uipath_status")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "success": True,
                "vmId": "server1-vm1",
                "serverId": "server1",
                "lastHeartbeat": "2025-01-22T10:30:00Z",
                "status": "healthy",
                "uiPathStatus": "running"
            }
        }
        extra = "allow"


class VmHealthStatusResponse(BaseModel):
    """Response model for VM health status."""
    systemStatus: str = Field(..., description="Overall system status: 'up' or 'down'", example="up")
    vmId: Optional[str] = Field(None, description="VM identifier", example="vm-worker-1", alias="vm_id")
    lastHeartbeat: Optional[str] = Field(None, description="ISO 8601 timestamp of the last heartbeat", example="2025-01-21T10:30:00Z", alias="last_heartbeat")
    status: Optional[str] = Field(None, description="Current VM status: healthy, unhealthy, or idle", example="healthy")
    processingQueueId: Optional[str] = Field(None, description="Queue ID that the VM is currently processing", example="660e8400-e29b-41d4-a716-446655440000", alias="processing_queue_id")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "systemStatus": "up",
                "vmId": "vm-worker-1",
                "lastHeartbeat": "2025-01-21T10:30:00Z",
                "status": "healthy",
                "processingQueueId": "660e8400-e29b-41d4-a716-446655440000"
            }
        }
        extra = "allow"


class ImageUploadResponse(BaseModel):
    """Response model for image upload."""
    success: bool
    image_url: Optional[str] = None
    blob_name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None


# Alert models
class AlertRequest(BaseModel):
    """Request model for creating an alert."""
    source: str = Field(..., description="Source of the alert: vm, server, uipath, or monitor", example="vm")
    sourceId: str = Field(..., description="Identifier of the source (e.g., VM ID, Server ID)", example="server1-vm1", alias="source_id")
    severity: str = Field(..., description="Severity level: critical, warning, or info", example="critical")
    message: str = Field(..., description="Alert message", example="UiPath process stopped unexpectedly")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional alert details as JSON object", example={"errorCode": "PROCESS_NOT_FOUND"})
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp (defaults to current time if not provided)", example="2025-01-22T10:30:00Z")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "source": "vm",
                "sourceId": "server1-vm1",
                "severity": "critical",
                "message": "UiPath process stopped unexpectedly",
                "details": {
                    "errorCode": "PROCESS_NOT_FOUND",
                    "lastKnownStatus": "running",
                    "timestamp": "2025-01-22T10:30:00Z"
                }
            }
        }
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        valid_sources = ['vm', 'server', 'uipath', 'monitor']
        if v not in valid_sources:
            raise ValueError(f"source must be one of: {', '.join(valid_sources)}")
        return v
    
    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v):
        valid_severities = ['critical', 'warning', 'info']
        if v not in valid_severities:
            raise ValueError(f"severity must be one of: {', '.join(valid_severities)}")
        return v
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class AlertResponse(BaseModel):
    """Response model for alert creation."""
    alertId: str = Field(..., description="Unique alert identifier (UUID)", example="550e8400-e29b-41d4-a716-446655440000", alias="alert_id")
    success: bool = Field(..., description="Whether the alert was created successfully", example=True)
    notificationSent: bool = Field(..., description="Whether notification was sent", example=True, alias="notification_sent")
    createdAt: str = Field(..., description="ISO 8601 timestamp when alert was created", example="2025-01-22T10:30:00Z", alias="created_at")
    
    class Config:
        populate_by_name = True
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class AlertItem(BaseModel):
    """Model for a single alert item in list responses."""
    alertId: str = Field(..., description="Unique alert identifier (UUID)", example="550e8400-e29b-41d4-a716-446655440000", alias="alert_id")
    source: str = Field(..., description="Source of the alert", example="vm")
    sourceId: str = Field(..., description="Identifier of the source", example="server1-vm1", alias="source_id")
    severity: str = Field(..., description="Severity level", example="critical")
    message: str = Field(..., description="Alert message", example="UiPath process stopped unexpectedly")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional alert details")
    resolved: bool = Field(..., description="Whether the alert is resolved", example=False)
    resolvedAt: Optional[str] = Field(None, description="ISO 8601 timestamp when alert was resolved", example=None, alias="resolved_at")
    createdAt: str = Field(..., description="ISO 8601 timestamp when alert was created", example="2025-01-22T10:30:00Z", alias="created_at")
    
    class Config:
        populate_by_name = True
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema


class AlertListResponse(BaseModel):
    """Response model for alert list with pagination."""
    alerts: List[AlertItem] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total number of alerts matching filters", example=15)
    limit: int = Field(..., description="Number of alerts per page", example=50)
    offset: int = Field(..., description="Pagination offset", example=0)
    
    class Config:
        populate_by_name = True


class AlertResolveResponse(BaseModel):
    """Response model for alert resolution."""
    alertId: str = Field(..., description="Unique alert identifier (UUID)", example="550e8400-e29b-41d4-a716-446655440000", alias="alert_id")
    success: bool = Field(..., description="Whether the alert was resolved successfully", example=True)
    resolvedAt: str = Field(..., description="ISO 8601 timestamp when alert was resolved", example="2025-01-22T10:35:00Z", alias="resolved_at")
    
    class Config:
        populate_by_name = True
    
    @classmethod
    def model_json_schema(cls, **kwargs):
        """Override to use field names (camelCase) instead of aliases in OpenAPI schema."""
        schema = super().model_json_schema(by_alias=False, **kwargs)
        return schema

