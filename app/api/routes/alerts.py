"""
Alert routes for monitoring and alerting system.

This module contains all routes related to alert management and notifications.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
import psycopg2
import uuid

from app.api.routes.dependencies import (
    logger,
    get_auth_dependency,
    require_auth,
    TokenData,
    get_db_connection,
    save_alert,
    get_alerts,
    resolve_alert,
    AlertRequest,
    AlertResponse,
    AlertItem,
    AlertListResponse,
    AlertResolveResponse,
)

router = APIRouter()


@router.post(
    "/alerts",
    tags=["Alerts"],
    summary="Submit an alert",
    description="Submit an alert from VM, server, or monitoring system. Stores the alert in the database and optionally sends notifications.",
    response_model=AlertResponse,
    status_code=200,
    responses={
        200: {
            "description": "Alert created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "alertId": "550e8400-e29b-41d4-a716-446655440000",
                        "success": True,
                        "notificationSent": True,
                        "createdAt": "2025-01-22T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid request data"},
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def create_alert(
    alert_data: AlertRequest,
    current_client: TokenData = get_auth_dependency()
) -> AlertResponse:
    """
    Submit an alert from VM, server, or monitoring system.
    
    **Request Body:**
    - `source` (required): Source of the alert - 'vm', 'server', 'uipath', or 'monitor'
    - `sourceId` (required): Identifier of the source (e.g., VM ID, Server ID)
    - `severity` (required): Severity level - 'critical', 'warning', or 'info'
    - `message` (required): Alert message
    - `details` (optional): Additional alert details as JSON object
    - `timestamp` (optional): ISO 8601 timestamp (defaults to current time)
    
    **Response:**
    Returns the created alert with `alertId`, `success`, `notificationSent`, and `createdAt`.
    
    **Example Request:**
    ```json
    {
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
    ```
    """
    conn = None
    
    try:
        # Validate required fields (Pydantic already validates, but double-check)
        if not alert_data.source:
            raise HTTPException(
                status_code=400,
                detail="source is required. Must be one of: vm, server, uipath, monitor"
            )
        
        if not alert_data.sourceId:
            raise HTTPException(
                status_code=400,
                detail="sourceId is required. Please provide a source identifier."
            )
        
        if not alert_data.severity:
            raise HTTPException(
                status_code=400,
                detail="severity is required. Must be one of: critical, warning, info"
            )
        
        if not alert_data.message:
            raise HTTPException(
                status_code=400,
                detail="message is required. Please provide an alert message."
            )
        
        # Prepare alert data for database
        alert_dict = {
            'source': alert_data.source,
            'source_id': alert_data.sourceId,
            'severity': alert_data.severity,
            'message': alert_data.message,
            'details': alert_data.details,
            'timestamp': alert_data.timestamp,
        }
        
        # Get database connection
        conn = get_db_connection()
        
        # Save the alert
        saved_alert = save_alert(conn, alert_dict)
        
        # Try to send notification (non-blocking, don't fail if it fails)
        notification_sent = False
        try:
            # Import notification function if available
            try:
                from app.utils.notifications import send_alert_notification
                notification_sent = send_alert_notification(saved_alert)
            except ImportError:
                # Notification service not available, skip
                logger.debug("Notification service not available, skipping notification")
                notification_sent = False
            except Exception as e:
                # Log but don't fail
                logger.warning(f"Failed to send notification: {str(e)}")
                notification_sent = False
        except Exception as e:
            logger.warning(f"Error in notification sending: {str(e)}")
            notification_sent = False
        
        # Format created_at timestamp
        created_at = saved_alert.get('created_at')
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat() + 'Z'
        elif isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
        
        # Format the response
        response_data = {
            'alertId': str(saved_alert['alert_id']),
            'success': True,
            'notificationSent': notification_sent,
            'createdAt': created_at_str,
        }
        
        # Create response model and serialize
        alert_response = AlertResponse(**response_data)
        response_dict = alert_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
        return JSONResponse(content=response_dict)
        
    except HTTPException:
        raise
    except ValueError as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get(
    "/alerts",
    tags=["Alerts"],
    summary="Retrieve alerts",
    description="Retrieve alerts with filtering and pagination. Supports filtering by source, sourceId, severity, and resolved status.",
    response_model=AlertListResponse,
    status_code=200,
    responses={
        200: {
            "description": "Alerts retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "alerts": [
                            {
                                "alertId": "550e8400-e29b-41d4-a716-446655440000",
                                "source": "vm",
                                "sourceId": "server1-vm1",
                                "severity": "critical",
                                "message": "UiPath process stopped unexpectedly",
                                "details": {
                                    "errorCode": "PROCESS_NOT_FOUND"
                                },
                                "resolved": False,
                                "resolvedAt": None,
                                "createdAt": "2025-01-22T10:30:00Z"
                            }
                        ],
                        "total": 15,
                        "limit": 50,
                        "offset": 0
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_alerts_list(
    source: Optional[str] = Query(None, description="Filter by source (vm, server, uipath, monitor)"),
    sourceId: Optional[str] = Query(None, description="Filter by specific source ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, warning, info)"),
    resolved: Optional[bool] = Query(False, description="Include resolved alerts (default: false, only unresolved)"),
    limit: int = Query(50, ge=1, le=100, description="Number of alerts to return (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(require_auth)
) -> AlertListResponse:
    """
    Retrieve alerts with filtering and pagination.
    
    **Query Parameters:**
    - `source` (optional): Filter by source - 'vm', 'server', 'uipath', or 'monitor'
    - `sourceId` (optional): Filter by specific source ID
    - `severity` (optional): Filter by severity - 'critical', 'warning', or 'info'
    - `resolved` (optional): Include resolved alerts (default: false, only shows unresolved)
    - `limit` (optional): Number of alerts to return (default: 50, max: 100)
    - `offset` (optional): Pagination offset (default: 0)
    
    **Response:**
    Returns a list of alerts with `alerts`, `total`, `limit`, and `offset`.
    """
    conn = None
    
    try:
        # Validate query parameters
        if source and source not in ['vm', 'server', 'uipath', 'monitor']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source: {source}. Must be one of: vm, server, uipath, monitor"
            )
        
        if severity and severity not in ['critical', 'warning', 'info']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {severity}. Must be one of: critical, warning, info"
            )
        
        # Build filters
        filters = {}
        if source:
            filters['source'] = source
        if sourceId:
            filters['source_id'] = sourceId
        if severity:
            filters['severity'] = severity
        if resolved is not None:
            filters['resolved'] = resolved
        
        # Get database connection
        conn = get_db_connection()
        
        # Get alerts
        alerts_list, total = get_alerts(conn, filters=filters, limit=limit, offset=offset)
        
        # Format alerts for response
        formatted_alerts = []
        for alert in alerts_list:
            # Format timestamps
            created_at = alert.get('created_at')
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat() + 'Z'
            elif isinstance(created_at, str):
                created_at_str = created_at
            else:
                created_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
            
            resolved_at = alert.get('resolved_at')
            resolved_at_str = None
            if resolved_at:
                if isinstance(resolved_at, datetime):
                    resolved_at_str = resolved_at.isoformat() + 'Z'
                elif isinstance(resolved_at, str):
                    resolved_at_str = resolved_at
            
            formatted_alert = {
                'alertId': str(alert['alert_id']),
                'source': alert['source'],
                'sourceId': alert['source_id'],
                'severity': alert['severity'],
                'message': alert['message'],
                'details': alert.get('details'),
                'resolved': alert.get('resolved', False),
                'resolvedAt': resolved_at_str,
                'createdAt': created_at_str,
            }
            formatted_alerts.append(AlertItem(**formatted_alert))
        
        # Create response
        response_data = {
            'alerts': formatted_alerts,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
        
        alert_list_response = AlertListResponse(**response_data)
        response_dict = alert_list_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
        return JSONResponse(content=response_dict)
        
    except HTTPException:
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.patch(
    "/alerts/{alertId}/resolve",
    tags=["Alerts"],
    summary="Resolve an alert",
    description="Mark an alert as resolved. Updates the alert with resolved status and timestamp.",
    response_model=AlertResolveResponse,
    status_code=200,
    responses={
        200: {
            "description": "Alert resolved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "alertId": "550e8400-e29b-41d4-a716-446655440000",
                        "success": True,
                        "resolvedAt": "2025-01-22T10:35:00Z"
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        404: {"description": "Alert not found"},
        500: {"description": "Server error"},
    },
)
async def resolve_alert_endpoint(
    alertId: str,
    current_user: dict = Depends(require_auth)
) -> AlertResolveResponse:
    """
    Mark an alert as resolved.
    
    **Path Parameters:**
    - `alertId` (required): Alert UUID to resolve
    
    **Response:**
    Returns the resolved alert with `alertId`, `success`, and `resolvedAt`.
    
    **Example:**
    PATCH /alerts/550e8400-e29b-41d4-a716-446655440000/resolve
    """
    conn = None
    
    try:
        # Validate UUID format
        try:
            uuid.UUID(alertId)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert ID format: {alertId}. Must be a valid UUID."
            )
        
        # Get database connection
        conn = get_db_connection()
        
        # Resolve the alert
        resolved_alert = resolve_alert(conn, alertId)
        
        # Format resolved_at timestamp
        resolved_at = resolved_alert.get('resolved_at')
        if isinstance(resolved_at, datetime):
            resolved_at_str = resolved_at.isoformat() + 'Z'
        elif isinstance(resolved_at, str):
            resolved_at_str = resolved_at
        else:
            resolved_at_str = datetime.now(timezone.utc).isoformat() + 'Z'
        
        # Format the response
        response_data = {
            'alertId': str(resolved_alert['alert_id']),
            'success': True,
            'resolvedAt': resolved_at_str,
        }
        
        # Create response model and serialize
        alert_resolve_response = AlertResolveResponse(**response_data)
        response_dict = alert_resolve_response.model_dump(exclude_none=True, exclude_unset=True, by_alias=False)
        
        return JSONResponse(content=response_dict)
        
    except HTTPException:
        raise
    except ValueError as e:
        if conn:
            conn.rollback()
        # Check if it's a "not found" error
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e)
            )
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()
